# The bench: limits, delays, failures, time

How to build the bench around a prototype, in docker compose. Each
part ends with the check that proves it works on this machine, because a limit that
is written down and not enforced is the most common way a bench lies.

Marked **(checked)**: tried on this repository's machine on 2026-11-19 (Docker 29,
compose 5.8, cgroup v2, ext4 on NVMe, kernel 7.3). Re-check anything when the
machine or a version changes; `scripts/preflight.py` shows what the machine has.

## Layout

One compose project per bench (`bench-<slug>`), from `templates/compose.yaml`. Four
groups of containers, each on its own CPUs (`bench.env`):

| Group | What | CPUs |
|---|---|---|
| Measured services | The prototype's own processes | `CPUS_SUT` |
| Datastores | The stores and brokers the design names | `CPUS_DATA` |
| Stand-ins and proxies | The sink (every outside dependency), Toxiproxy | `CPUS_AUX` |
| Load | k6 or another generator | `CPUS_LOAD` |

Every hop that crosses a machine in the design goes through Toxiproxy, so a delay or
a cut can be put on it. In-process calls stay direct.

Other containers may be running on the machine. Never stop, restart or reconfigure
anything outside the bench's own compose project. Take the bench down when the work
is done: `docker compose --env-file bench.env --profile load --profile calibration down -v`.

## Why compose, and what that leaves out

The bench runs in docker compose only. Performance and failure behaviour are
decided by what compose reproduces in full: the processes, their CPU, memory and
disk limits, the network between them, the stores, and the faults. A container
under a CPU quota in compose is throttled by the same kernel mechanism as a pod
with a CPU limit, so per-unit rates and latencies carry over.

What compose does not have is an orchestrator. Claims about what a platform does
*for* the system cannot be tested here and are marked untestable in the plan:
rescheduling work after a machine is lost, readiness checks gating traffic, a
rolling update under load, autoscaling. Two things stay testable without one:

- **What the design itself does when a process or machine disappears** (leases
  expire, another node takes over, a reaper returns the work). That is the design's
  own logic, and `crash` and `freeze` exercise it fully.
- **A fixed restart delay.** If the page says "a replacement starts within 30 s",
  crash the container, wait 30 s, start it (`docker compose up -d <service>`), and
  state the delay as an input taken from the page, not as something measured.

## CPU

```yaml
cpus: 1.0            # the quota: at most one CPU's worth of time per 100 ms period
cpuset: ${CPUS_SUT}  # which CPUs it may run on
```

- A quota is enforced by throttling: when the container has used its share of a
  100 ms period it is stopped until the next one. Short bursts of work therefore see
  latency spikes of up to a period well before average use reaches the limit. That is
  what a container platform does in production too, so keep it, and read
  `throttled_share` when a tail is unexplained.
- Give the unit the design's size (`cpus: 0.5` for a half-CPU task). Do not leave a
  measured service unlimited "to see what it can do": the result then depends on the
  machine.
- **Hybrid CPUs.** This machine has 16 fast CPUs (0-15, 8 cores with two threads
  each) and 16 slow ones (16-31). Pin everything measured to one kind. An unpinned
  half-CPU limit means a different speed on each run. `preflight.py` prints a split.
- One CPU here is not one cloud vCPU. State the CPU model in the report and treat
  absolute rates as "on this machine"; ratios and what gives way first carry over,
  absolute numbers roughly.

**Check (checked):** calibration K6. A busy loop limited to 0.5 measured 0.50 CPUs
with every period throttled.

## Memory

```yaml
mem_limit: 4g
memswap_limit: 4g    # equal to mem_limit: swap off
```

- The page cache a container fills counts against its limit (cgroup v2), so the
  limit also caps how much of a store's data stays cached. This is what makes the
  data-to-memory ratio reproducible: a store limited to 6.4 GB holding 10 GB of data
  behaves like a 64 GB node holding 100 GB. **(checked: a container limited to
  200 MB that read a 1 GB file held 198 MB of cache and was not killed)**
- A process that exceeds the limit with its own memory is killed. `cgsample.py`
  reports `oom_kills` and `restarts`; either one invalidates a run unless the run is
  about that.
- Set the store's own memory settings (buffer pool, heap) to fit inside the limit the
  way the design sizes them, not to the product's default.

## Disk

```yaml
volumes: ["store-data:/var/lib/postgresql/data"]     # a named volume: a real filesystem
blkio_config:
  device_write_iops: [{ path: "${DATA_DEVICE}", rate: 3000 }]
  device_read_iops:  [{ path: "${DATA_DEVICE}", rate: 3000 }]
  device_write_bps:  [{ path: "${DATA_DEVICE}", rate: "125mb" }]
```

- A limit can only slow the disk down. Measure what the disk gives before deciding
  what the limit means. **(checked)** This machine's disk does about 550 `fdatasync`
  a second unlimited, which is *slower* than many cloud volumes: a design that assumes
  3,000 durable commits a second on one volume cannot be shown here without group
  commit, and the report must say so.
- Limits apply to synchronous and direct writes. **(checked)** A limit of 40 write
  IOPS gave exactly 40 synchronous writes a second; `fdatasync` got 20, because each
  costs two writes (data and journal). A throughput limit of 10 MB/s held direct
  writes to 10.8 MB/s. Plain buffered writes followed by one `fsync` were **not**
  slowed by the throughput limit, so do not rely on it for bulk loads.
- Never put a store on tmpfs or in the container's own layer, and never turn off
  `fsync` or synchronous commit unless the page does.
- On WSL and on cgroup v1 disk limits do not work; report the disk as uncapped and
  every write-bound result as an upper bound.

**Check:** add a calibration scenario per store that measures the write rate inside
the store's own limits and records it as `calib.fsync_per_s`:

```sh
docker run --rm --device-write-iops "$DATA_DEVICE:3000" -v bench-x_store-data:/data \
  --entrypoint /usr/lib/postgresql/17/bin/pg_test_fsync postgres:17 -s 2 -f /data/fsync.tmp
```

Compare the `fdatasync` line with the commit rate the design needs.

## Delays

**Toxiproxy** (TCP, no privileges, works everywhere). Declare one proxy per hop in
`toxiproxy.json`; point the caller at `toxiproxy:<port>`. `run.sh` has the verbs:

```sh
delay_on store 1 0.2      # 1 ms on every reply, 0.2 ms jitter
delay_off store
```

Typical values: 0.5 to 1 ms between machines in one zone, 1 to 2 ms between zones of
a region, tens of ms between regions. Take the value from the page if it gives one.
The delay is added to replies only (downstream); add a second toxic with
`"stream":"upstream"` for the request side. A connection pool hides nothing: the
delay is per reply, on every connection.

**netem** (packet level: jitter distributions, loss, reordering, also UDP). Needs the
kernel module and `NET_ADMIN` inside one container's network namespace:

```yaml
store-netem:
  image: alpine:3.22
  network_mode: "service:store"
  cap_add: ["NET_ADMIN"]
  command: ["sh", "-c", "apk add -q iproute2-tc && sleep infinity"]
```
```sh
docker compose exec store-netem tc qdisc replace dev eth0 root netem delay 10ms 2ms distribution normal loss 0.1%
docker compose exec store-netem tc qdisc del dev eth0 root     # REQUIRED to remove it
```

- **(checked)** 10 ms asked gave a median of 10.3 ms. The rule stays in the store's
  network namespace after the sidecar is removed; it goes only when deleted or when
  the store container is recreated. Always delete it, and verify with a calibration
  request.
- netem delays what the container *sends*. A new connection pays twice (handshake
  and reply). To delay both directions, put a rule on both ends.
- Not available on WSL.

**Check (checked):** calibration K5. 20 ms asked through Toxiproxy measured 20.3 ms.

## Slow and failing dependencies

The sink (`templates/sink`) plays every outside dependency. Behaviour is chosen per
request, so the mix belongs to the seeded data, as on a real platform where each
customer's endpoint behaves its own way:

| Query | Behaviour |
|---|---|
| `ms=150&p99=900` | Service time: median 150 ms, 99% within 900 ms |
| `fail=0.3&status=503` | 30% of calls refused before the work is done |
| `drop=0.01` | 1% of calls do the work, then the connection closes with no reply (the case that makes exactly-once impossible) |
| `hang=0.01` | 1% never reply |
| `idem=1` | A repeated key is acknowledged and not done again |

Give each request `key` (the id the design promises to run once) and `due` (Unix ms)
as query fields or `X-Bench-Key` / `X-Bench-Due` headers. `GET /stats?from=&to=`
returns counts, duplicates and the delay percentiles for a window; `GET /dump` the
raw arrivals.

A typical mix, when the page gives none: 80% answer in about 150 ms with a long tail,
12% take 1 to 10 s, 5% take 10 to 30 s, 2% refuse a third of calls, 1% always fail.

## Failures

All **(checked)** on the bench's own containers. The verbs are in `run.sh`.

| Fault | Command | What it tests |
|---|---|---|
| Process dies | `crash worker` (`docker compose kill -s KILL`) | Detection by a missed heartbeat; the reaper; nothing lost |
| Process freezes, then resumes | `freeze worker`; `thaw worker` | Fencing, leases, stale owners: the resumed process still thinks it owns its work |
| Hop cut | `cut store`; `mend store` | Errors handled; retry and backoff; state after reconnect |
| Hop silent | `blackhole_on store`; `blackhole_off store` | Timeouts: connections stay open and nothing arrives |
| Hop slow | `delay_on store 500` | Timeouts shorter than the delay; queues behind a slow dependency |
| Dependency flaky or dead | Sink `fail=`, `hang=`, `drop=` | Retries, dead-lettering, isolation between tenants |
| Store restarts | `docker compose restart store` | Reconnect; recovery of in-flight writes |
| Store fails over | Kill the primary of a replicated pair | The page's failover time; no acknowledged write lost |
| Disk full | A small volume, or `fallocate` a filler file inside it | The write path's behaviour when the store refuses |
| Out of memory | Lower `mem_limit` below the working set | Restart behaviour; `oom_kills` |
| Machine lost | `crash` every container the page puts on that machine, in one command | What the page says happens to that machine's work |

Record the moment of every fault (`now_ms`) in the run's metrics, land it mid-burst,
and drain before reading the ledger (`method.md`, "Failures").

Clock skew between machines cannot be produced: containers share the host's clock.
Mark those failure paths untestable, or test the design's defence directly by giving
one process an offset through its injectable clock.

## Ageing data

Seed in bulk, then churn, then snapshot (`method.md`, "Long uptime").

**Seed.** Generate inside the store where possible; it is the fastest path and needs
no files.

```sql
-- PostgreSQL: 86 million rows spread over 30 days, 1,000 tenants with skew, mostly final states
INSERT INTO runs (id, tenant_id, due_at, state, payload)
SELECT g, (random() ^ 3 * 1000)::int,                       -- cube: a few tenants hold most rows
       now() - (random() * interval '30 days'),
       CASE WHEN random() < 0.97 THEN 'succeeded' WHEN random() < 0.5 THEN 'dead' ELSE 'pending' END,
       repeat('x', 200)
FROM generate_series(1, 86000000) g;
```

- Drop secondary indexes before a large load and build them after, or the load takes
  many times longer. Then `ANALYZE`.
- MySQL: a recursive CTE or `LOAD DATA INFILE` from a generated CSV. Cassandra:
  `sstableloader` or a parallel writer. Redis: `redis-cli --pipe`. Kafka: the
  producer performance tool, to the retention size.
- Size check after the load: bytes per row with indexes against the page's estimate.
  That number is itself a claim.

**Churn.** Run the prototype's own write path at the design's rate (or faster, with
the clock scaled) until wear is steady: for PostgreSQL the dead-tuple share in
`pg_stat_user_tables` and the table's size against its live size stop rising across
three autovacuum cycles; for an LSM store the number of files per level and the
pending-compaction bytes stop rising.

**Snapshot.** Stop the store, copy the volume, and restore it before every run so
runs start from the same state:

```sh
docker compose stop store
docker run --rm -v bench-x_store-data:/from -v bench-x_store-aged:/to alpine:3.22 cp -a /from/. /to/
```

## Time

The prototype reads time from one clock that can be scaled, and every interval that
is a *wait* goes through it:

```go
// clock.go: the only place the prototype may ask for the time.
var scale = envFloat("CLOCK_SCALE", 1)
var start = time.Now()
func Now() time.Time               { return start.Add(time.Duration(float64(time.Since(start)) * scale)) }
func Wait(d time.Duration)         { time.Sleep(time.Duration(float64(d) / scale)) }      // schedules, retention, cleanup
func Work(d time.Duration)         { time.Sleep(d) }                                      // service time: never scaled
```

- `CLOCK_SCALE=60`: a minute of the run is an hour of the design. A 30-day retention
  passes in 12 hours; at 720 (a day in two minutes) in one hour.
- Due times stored in the database are in scaled time, so seeded schedules and the
  sink's `due` use the same clock (pass `due` already converted to real Unix ms, or
  the delay is meaningless).
- Timeouts on real calls, heartbeat intervals that guard real work and service times
  stay in real time. See the rules in `method.md`.
- Shorten the store's own maintenance to match (autovacuum naptime, compaction
  throughput, TTL sweep interval) and list each changed setting in the report.

For a soak, sample every 10 s (`sampler_start 10`) and read `anon_slope_mb_per_h`
per unit, plus the store's size and backlog at intervals.

## Load generators

| The design's interface | Generator | Open loop |
|---|---|---|
| HTTP | k6 (`templates/k6/load.js`), image `grafana/k6` | `constant-arrival-rate`, `ramping-arrival-rate` |
| gRPC | k6 (`k6/net/grpc`) | the same executors |
| SQL straight at a store | `pgbench --rate` (latency is counted from the scheduled start) | yes |
| A broker | The broker's own producer tool at a fixed rate, or a small Go producer | set the rate, record the send schedule |
| Time-driven work | Seeded rows; no generator | by construction |

- Size the virtual users for the worst case: `rate × the longest a request may take`
  (`MAX_LATENCY_S`). Too few and requests are dropped, which invalidates the run.
- k6 exits with code 99 when a threshold is missed. `run.sh` treats that as a result.
- Read a scenario's `count`, not its `rate`: k6 averages the rate over the whole run,
  warm-up included. Delivered rate = count ÷ the scenario's duration.
- Keep the URL the same for every request and send the key in headers. A unique URL
  per request makes k6 keep one series per request and run out of memory.
- k6 reports its own view; the sink reports the receiver's. Judge "on time" and
  "exactly once" from the sink, and the caller's latency and errors from k6.

## Pitfalls seen in practice

- A limit configured but not enforced (cgroup v1, WSL).
- The load generator sharing CPUs with the system, or itself saturated.
- A dataset small enough to live in memory.
- A local disk faster, or slower, than the storage the design assumes.
- One fast plain-HTTP destination where production has thousands of hosts with TLS.
- A fault that landed in a quiet moment and so tested nothing.
- Default settings of the prototype capping throughput (pool sizes, batch sizes,
  poll intervals): tune to what the page states, and say what was tuned.
- A leftover netem rule or disabled proxy from the previous run.
- Another bench or project using the same host ports or CPUs.
