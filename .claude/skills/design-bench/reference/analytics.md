# Run analytics

The verdict report uses the claim rules. The local dashboard reads archived
observations and lets you inspect a scenario, run, load phase, region and mode.
It presents per-attempt mean, p95 and p99, accepted throughput, drops, ticket
outcomes and sampled container resource pressure. Earlier summary-only runs
remain selectable. Their raw observations cannot be reconstructed.

## Capture and isolation

- Fill `CPUS_MON` from preflight's monitoring suggestion. Reserve a physical
  core, including its SMT siblings if applicable. The sampler rejects logical
  CPU overlap with the prototype, stores, generator and auxiliaries when
  `CPUS_MON` is set. If omitted, the sampler uses `CPUS_AUX`. Its actual
  affinity is stored in the host samples and resource summary.
- The runner enables raw capture by default. Use `RAW_CAPTURE=0` for a baseline.
  Set `RAW_STAGE_ROOT` to an existing, writable directory on a dedicated
  device or a size-limited tmpfs. Budget its space and memory at the peak rate
  and full scenario duration. With no scratch root, k6 stages on the results
  filesystem. Measure the bytes per request in the smoke run before sizing a soak.
- Run paired capture-off and capture-on passes at the highest planned load with
  the same snapshot, workload and limits. Compare delivered arrivals, drops,
  latency, generator headroom and store I/O against the plan's tolerances and
  repeatability. The k6 writer shares the generator's CPU set. CPU affinity
  leaves the machine's memory bandwidth and storage shared. Use the
  capture-off pass for performance verdicts if capture measurably changes them.
- The run holds k6 data in scratch through the measured window and drain, then
  archives it. The sink export also runs after the drain. Run Parquet conversion
  and dashboard generation after the bench scenarios finish. The raw archive
  retains all k6 points, resource snapshots and sink arrivals. Set retention
  for them explicitly. Raw files and Parquet stay outside Git.
- Check capture coverage before using a chart. For the stock driver, the raw
  attempts must equal completed measured iterations and their IDs must be
  unique. A workload with multiple requests per iteration should set
  `expected_attempts` in its k6 summary. Keep partial files for diagnosis.

## Matchmaking

In the design-specific k6 script import `recordAttempt` from `./capture.js`.
Call it exactly once per join attempt, including an HTTP failure or timeout,
using the attempt's unique synthetic `request_id`, `sent_ms`, `observed_ms`
and HTTP `status` (0 for a timeout or transport error). Supply `scheduled_ms`
from the workload schedule when available. On acceptance add the API's
`ticket_id`. Pass `region`, `mode`, `party_size` and `attempt_no` when supplied
by the workload. IDs are output metadata. The default driver records generic
HTTP attempts. The prototype's adapted driver supplies the ticket ID and cohorts.
Use synthetic test identities and a stable route label when a URL contains a
ticket ID. Leave credentials and real player data out of captured attributes.

After draining, have the client-side outcome observer export
`results/<scenario>/<run>/raw/tickets.csv` with the header
`ticket_id,outcome,observed_ms`. Write one terminal row per synthetic ticket
using `matched`, `expired`, `cancelled` or `unresolved`. Use the same Unix
millisecond clock as the client, and capture when that client observed the
outcome. Leave missing outcomes absent. The dashboard joins from unique
accepted ticket IDs, so unresolved and expired tickets stay in the
denominator for the 10 s and 60 s match targets. Matched-ticket latency
percentiles use only tickets with a valid observed match time.

## Build the dashboard

Use the DuckDB Python package (`duckdb>=1.4,<2`) in an isolated analytics
environment. It is only required for this offline step. If it needs
installation, include that in the plan. From the repository root:

```sh
python3 .claude/skills/design-bench/scripts/analytics.py bench/<slug>/results drafts/<slug>/bench-analytics.html
```

Open the generated HTML from disk. It contains chart aggregates, so it can be
opened independently of the archive. The archive in `bench/<slug>/analytics/`
contains Parquet tables per run. Use `attempts.parquet` or `tickets.parquet`
to compute exact percentiles over any chosen pool of observations. For charts
that compare runs, keep the load conditions and evidence class visible. A
p95 computed across individual observations can differ from the p95 of
per-run p95s.

Commit the per-design source inputs and each run's `source.json` and summaries.
Retain raw observations and Parquet in the per-run archive outside Git for
later analysis of the same measured results.
