#!/usr/bin/env bash
# One run of one scenario. Copy to bench/<slug>/run.sh.
#
#   ./run.sh calibration            # first, and again whenever the bench changes
#   ./run.sh steady r1              # results land in results/steady/r1/metrics.json
#
# Every scenario follows the same order: reset the ledger, start the sampler,
# mark the window, offer the load (and inject the fault), let the system drain,
# then collect everything for the window into one metrics.json.
set -euo pipefail
cd "$(dirname "$0")"
set -a; . ./bench.env; set +a
export UID_GID="$(id -u):$(id -g)"
SKILL="$(git rev-parse --show-toplevel)/.claude/skills/design-bench/scripts"
PROJECT="bench-$SLUG"
DC="docker compose --project-name $PROJECT --env-file bench.env"

scenario="${1:?usage: run.sh <scenario> [run-name]}"
run="${2:-$(date +%Y%m%d-%H%M%S)}"
OUT="results/$scenario/$run"
mkdir -p "results/$scenario"
mkdir "$OUT"  # Refuse to overwrite a previous run, even if it failed.
python3 "$SKILL/provenance.py" "$PWD" "$SLUG" "$OUT/source.json" \
  --capture "${RAW_CAPTURE:-1}" --sampler-cpus "${CPUS_MON:-$CPUS_AUX}"
RAW_STAGE=""
if [[ "${RAW_CAPTURE:-1}" == 1 ]]; then
  mkdir "$OUT/raw"
  RAW_STAGE=$(mktemp -d "$(realpath "${RAW_STAGE_ROOT:-$OUT/raw}")/k6.XXXXXXXX")
fi

# ---- the bench's verbs -------------------------------------------------------
now_ms()   { date +%s%3N; }
say()      { printf '\n== %s\n' "$*"; }
sink()     { curl -fsS "localhost:$SINK_PORT$1"; }
sink_reset() { curl -fsS -X POST "localhost:$SINK_PORT/reset" >/dev/null; }
toxi()     { curl -fsS -X "$1" "localhost:$TOXI_PORT$2" ${3:+-d "$3"} >/dev/null; }

# Delay on a hop: fixed part and jitter, in ms. Applies to replies (downstream).
delay_on()  { toxi POST "/proxies/$1/toxics" "{\"name\":\"delay\",\"type\":\"latency\",\"attributes\":{\"latency\":$2,\"jitter\":${3:-0}}}"; }
delay_off() { toxi DELETE "/proxies/$1/toxics/delay"; }
# Cut a hop (connections refused and existing ones closed) and mend it.
cut()       { toxi POST "/proxies/$1" '{"enabled":false}'; }
mend()      { toxi POST "/proxies/$1" '{"enabled":true}'; }
# Black hole: connections stay open, nothing gets through (what a silent partition looks like).
blackhole_on()  { toxi POST "/proxies/$1/toxics" '{"name":"hole","type":"timeout","attributes":{"timeout":0}}'; }
blackhole_off() { toxi DELETE "/proxies/$1/toxics/hole"; }
# A process that dies without warning, and one that stops answering but is not dead
# (a long pause: the case fencing and leases exist for).
crash()     { $DC kill -s KILL "$1" >/dev/null; }
freeze()    { $DC pause "$1"; }
thaw()      { $DC unpause "$1"; }

sampler_start() {
  local exclude="$CPUS_SUT,$CPUS_DATA,$CPUS_LOAD"
  [[ -z "${CPUS_MON:-}" ]] || exclude="$exclude,$CPUS_AUX"
  python3 "$SKILL/cgsample.py" run --project "$PROJECT" --out "$OUT/samples.jsonl" \
    --interval "${1:-2}" --cpus "${CPUS_MON:-$CPUS_AUX}" --exclude-cpus "$exclude" &
  SAMPLER=$!
}
SAMPLER=""
sampler_stop()  { [ -n "$SAMPLER" ] || return 0; kill "$SAMPLER" 2>/dev/null; wait "$SAMPLER" 2>/dev/null || true; SAMPLER=""; }
archive_raw() {
  [[ -n "$RAW_STAGE" ]] || return 0
  local file
  for file in "$RAW_STAGE"/*; do
    [[ -f "$file" ]] || continue
    mv "$file" "$OUT/raw/${file##*/}.tmp"
    mv "$OUT/raw/${file##*/}.tmp" "$OUT/raw/${file##*/}"
  done
  rmdir "$RAW_STAGE"
  RAW_STAGE=""
}
trap 'sampler_stop; archive_raw' EXIT

# k6 exits 99 when a threshold is missed. That is a result for verdict.py.
load() {
  local out="$1" status=0 raw_file="${1%.json}.k6.jsonl"; shift
  local -a mount=() capture=()
  if [[ -n "$RAW_STAGE" ]]; then
    mount=(--volume "$RAW_STAGE:/bench-raw")
    capture=(--out "json=/bench-raw/$raw_file.partial" -e BENCH_CAPTURE=1)
  fi
  $DC --profile load run --rm -T --name "$PROJECT-k6" "${mount[@]}" k6 run --quiet \
    -e OUT="$scenario/$run/$out" "${capture[@]}" "$@" /scripts/load.js || status=$?
  if [[ -n "$RAW_STAGE" ]]; then
    if [[ "$status" != 0 && "$status" != 99 ]]; then
      return "$status"
    elif [[ -s "$RAW_STAGE/$raw_file.partial" ]]; then
      mv "$RAW_STAGE/$raw_file.partial" "$RAW_STAGE/$raw_file"
    else
      echo "Missing k6 raw capture for $out" >&2
      status=1
    fi
  fi
  [[ "$status" == 0 || "$status" == 99 ]]
}

# collect <from_ms> <to_ms> [flatten args…]: ledger and resources for the window, merged into metrics.json
collect() {
  local from="$1" to="$2"; shift 2
  sink "/stats?from=$from&to=$to" > "$OUT/sink.json"
  if [[ "${RAW_CAPTURE:-1}" == 1 ]]; then
    sink /dump > "$OUT/raw/sink.csv.tmp"
    mv "$OUT/raw/sink.csv.tmp" "$OUT/raw/sink.csv"
    archive_raw
  fi
  jq -n --argjson from "$from" --argjson to "$to" '{from_ms: $from, to_ms: $to}' > "$OUT/window.json"
  python3 "$SKILL/cgsample.py" summarize "$OUT/samples.jsonl" --from "$from" --to "$to" > "$OUT/resources.json"
  python3 "$SKILL/verdict.py" flatten sink="$OUT/sink.json" res="$OUT/resources.json" "$@" \
    --set window.seconds="$(( (to - from) / 1000 ))" > "$OUT/metrics.tmp"
  mv "$OUT/metrics.tmp" "$OUT/metrics.json"
  echo "wrote $OUT/metrics.json"
}

# ---- scenarios ---------------------------------------------------------------

# Proves the bench before any number counts: the ledger counts right and can
# report a duplicate, the load generator delivers the highest planned rate with
# room to spare, the path itself adds little, an injected delay is the delay
# asked for, a CPU limit bites, and every measured service has limits.
scenario_calibration() {
  local max_rate="${MAX_RATE:-500}" delay_ms="${CALIB_DELAY_MS:-20}"
  $DC stop
  $DC up -d --build --wait toxiproxy sink
  sink_reset; delay_off sink 2>/dev/null || true
  sampler_start 1

  say "ledger: 50 keyed calls, then one repeated"
  for i in $(seq 50); do sink "/do?key=calib-$i" >/dev/null; done
  local keys dups0 dups1
  keys=$(sink /stats | jq .keys); dups0=$(sink /stats | jq .duplicate_effects)
  sink "/do?key=calib-1" >/dev/null; dups1=$(sink /stats | jq .duplicate_effects)

  say "floor: $max_rate requests/s through the proxy to an instant sink"
  local f0; f0=$(now_ms)
  load floor.json -e RATE="$max_rate" -e DURATION=20s -e WARMUP=5s -e TARGET="http://toxiproxy:9001/do?ms=0"
  local f1; f1=$(now_ms)

  say "delay: the same path with ${delay_ms} ms added"
  delay_on sink "$delay_ms"
  load delay.json -e RATE=50 -e DURATION=15s -e WARMUP=3s -e TARGET="http://toxiproxy:9001/do?ms=0"
  delay_off sink
  load nodelay.json -e RATE=50 -e DURATION=15s -e WARMUP=3s -e TARGET="http://toxiproxy:9001/do?ms=0"

  say "limit: a busy loop held to half a CPU"
  $DC --profile calibration up -d burn; sleep 12
  local b1; b1=$(now_ms)
  $DC --profile calibration rm -sf burn >/dev/null
  # Sample the actual prototype after the isolated floor and CPU-limit checks.
  $DC config --format json | jq '{services: (.services | map_values(
    {cpus, mem_limit, cpuset, profiles, scale: (.scale // .deploy.replicas // 1)}))}' > "$OUT/compose-limits.json"
  local limits_from; limits_from=$(now_ms)
  $DC up -d --build --wait
  sleep 3
  sampler_stop
  python3 "$SKILL/cgsample.py" summarize "$OUT/samples.jsonl" --from "$limits_from" > "$OUT/limits-res.json"
  local limit_problems
  limit_problems=$(python3 "$SKILL/cgsample.py" check-limits "$OUT/compose-limits.json" "$OUT/limits-res.json")

  python3 "$SKILL/cgsample.py" summarize "$OUT/samples.jsonl" --from "$f0" --to "$f1" > "$OUT/floor-res.json"
  python3 "$SKILL/cgsample.py" summarize "$OUT/samples.jsonl" --from "$((b1 - 10000))" --to "$b1" > "$OUT/burn-res.json"
  python3 "$SKILL/verdict.py" flatten floor="$OUT/floor.json" delay="$OUT/delay.json" nodelay="$OUT/nodelay.json" \
    floorres="$OUT/floor-res.json" burnres="$OUT/burn-res.json" \
    --set calib.ledger_keys="$keys" --set calib.ledger_dups_before="$dups0" --set calib.ledger_dups_after="$dups1" \
    --set calib.delay_asked_ms="$delay_ms" --set calib.max_rate="$max_rate" --set calib.limit_problems="$limit_problems" \
    > "$OUT/raw.json"
  # Derived: the delay actually added, and the share of its CPUs the load generator used.
  jq '. + {"calib.delay_added_ms": (."delay.http_req_duration.med" - ."nodelay.http_req_duration.med"),
           "calib.delay_error": (((."delay.http_req_duration.med" - ."nodelay.http_req_duration.med") - ."calib.delay_asked_ms") / ."calib.delay_asked_ms" | fabs),
           "calib.rate_delivered": (."floor.iterations.count" / (."calib.max_rate" * 20))}' "$OUT/raw.json" > "$OUT/metrics.tmp"
  rm "$OUT/raw.json"
  jq '{ledger_keys: ."calib.ledger_keys", dups_before: ."calib.ledger_dups_before", dups_after: ."calib.ledger_dups_after",
       floor_p99_ms: ."floor.http_req_duration.p99", dropped: ."floor.dropped_iterations.count", rate_delivered: ."calib.rate_delivered",
       loadgen_share_of_its_cpus: ."floorres.k6.cpu_of_set_max", delay_added_ms: ."calib.delay_added_ms",
       burn_cores: ."burnres.burn-1.cpu_cores_avg", burn_throttled_share: ."burnres.burn-1.throttled_share",
       host_busy_max: ."floorres.host.cpu_busy_max", limit_problems: ."calib.limit_problems"}' "$OUT/metrics.tmp"
  archive_raw
  mv "$OUT/metrics.tmp" "$OUT/metrics.json"
}

# TODO: the design's scenarios. Each is a function named scenario_<name>; plan.md lists them.
# Shape of a steady run at the design's rate:
#
# scenario_steady() {
#   $DC up -d --build --wait; sink_reset; sampler_start
#   local t0; t0=$(( $(now_ms) + 30000 ))          # the window starts after the warm-up
#   load k6.json -e RATE=200 -e DURATION=300s -e WARMUP=30s -e P99_MS=200 -e TARGET="http://api:8080/v1/things"
#   local t1; t1=$(now_ms)
#   sleep 10; sampler_stop                          # drain
#   collect "$t0" "$t1" load="$OUT/k6.json" --set load.offered="$((200 * 300))"
# }
#
# Shape of a fault run: the same load, a fault at a known moment, and the ledger read after the drain:
#
# scenario_crash_worker() {
#   $DC up -d --build --wait; sink_reset; sampler_start
#   local t0; t0=$(now_ms)
#   load k6.json -e RATE=200 -e DURATION=120s -e WARMUP=0s & local lg=$!
#   sleep 45; local tf; tf=$(now_ms); crash worker; sleep 20; $DC up -d worker
#   wait "$lg"; sleep 60; sampler_stop              # drain: longer than the design's recovery time
#   collect "$t0" "$(now_ms)" load="$OUT/k6.json" --set load.offered="$((200 * 120))" \
#     --set fault.at_ms="$tf" --set expected.keys="$(expected_keys)"
# }

fn="scenario_${scenario//-/_}"
declare -F "$fn" >/dev/null || { echo "no scenario '$scenario' in run.sh"; exit 2; }
"$fn"
