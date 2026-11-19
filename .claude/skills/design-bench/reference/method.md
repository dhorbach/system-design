# Method: how a run becomes evidence

No published framework takes a design document to a prototype to a verdict. This
method is assembled from parts that are each established; the source of each is
named where it is used and listed at the end. Read this file before writing a plan.

## What a bench can and cannot say

A bench tries to disprove a claim and reports whether it managed to. A claim that
survives is **not disproved under the conditions tested**; it is never proved.
Jepsen states the same limit for its own tests: they "can only prove the existence
of errors". So every verdict carries its conditions (load, data, faults, machine),
and the report says "holds" or "verified", never "proven" or "guaranteed".

Three consequences shape everything below:

1. **A check must be able to fail.** A duplicate counter that reads 0 means nothing
   until it has been seen to read 1. Every correctness check gets a control: a run
   with the fault planted (the guard removed, the lease check skipped) that the check
   must catch.
2. **The bench is a suspect too.** "You benchmark A, but actually measure B, and
   conclude you've measured C" (Gregg). Before any claim is judged, the bench proves
   its own limits, delays, load generator and ledger (calibration), and every run is
   checked for a sound bench (gates).
3. **The interesting result is a contradiction.** The page's arithmetic said 2,000
   per second and the prototype stops at 300: that gap, and its cause, is the finding.
   Look for what gives way first, not for a green table.

## From the page to claims

A claim is one sentence of the page that a measurement could contradict. Sources, in
the order to mine them:

| Source on the page (or in the ledger) | Becomes a claim such as |
|---|---|
| A requirement with a number (`NFR2`) | 99% of runs start within 1 s of their due time at 40 runs/s |
| A derived number in the estimates | One run row with its indexes takes about 1 kB |
| A capacity statement in a component section | One store node accepts 2,400 writes/s |
| A failure path | A worker killed mid-run loses no run and repeats at most the runs it held |
| A recovery time | Matching resumes within 10 s of losing a node |
| A statement about a product, with its setting | A commit with a synchronous standby costs about 10 ms |
| A threshold where the design changes | Below 2,000 runs/s the database alone can coordinate |

Write each claim with five parts. A claim missing one is not ready to test.

- **Quote**: the exact sentence of the page. The report shows it, and a claim whose
  quote is no longer in the page is stale.
- **Metric, measured where the client would observe it.** "Starts on time" is measured
  at the receiving end (the sink), against the due time, not from a `started_at`
  column the system writes about itself. "Accepted" is measured by the caller.
- **Target**: the page's number and comparison.
- **Conditions**: the load (rate and shape), the data present (how many days), the
  fault injected. A latency target with no load condition is not a claim; take the
  condition from the page, and if the page gives none, that is a finding for the page.
- **Evidence class** (next part).

Split a requirement that holds in one condition and may fail in another into two
claims ("on ordinary seconds", "at the 09:00 burst"). One verdict per condition.

## Evidence classes

| Class | Meaning | When it applies |
|---|---|---|
| `measured` | The bench reproduced the design's own value | Anything stated per node, per request or per row: one node's rate, one commit's latency, a row's size, a recovery time, a correctness invariant |
| `scaled` | Measured on a reduced copy that keeps the design's ratios | A cluster shrunk to fewer nodes at the design's per-node load and data |
| `extrapolated` | Computed by a named model from measured points | A cluster-level rate at a node count the machine cannot hold; storage after N days from measured bytes per row |
| `analytic` | The page's arithmetic re-run by a script, with measured inputs where the page assumed them | A derived number whose inputs were measured |
| `untestable` | One machine cannot produce the condition | See the list below |

Rules:

- Prefer `measured`. Most designs state their hard numbers per node or per request,
  and those can be reproduced at full value on one machine.
- `scaled` must name what was kept and what was shrunk (the scale statement in
  `claims.json`). The report repeats it on every scaled claim.
- `extrapolated` must name the model, its inputs and its error range, and judge the
  claim against the **unfavourable end** of the range.
- Never upgrade a class in the report. A scaled pass is "verified at bench scale".

**Not testable on one machine.** Say so in the plan instead of approximating
silently: real cross-zone or WAN failure modes (an added delay shows the latency
cost, not the failure behaviour); disk, firmware and correlated hardware failures;
the cost of coordination at the true node count (it cannot be read off fewer than
about 8 nodes); kernel, NIC and connection limits at the full aggregate rate; clock
skew between machines (containers share the host's clock); slowdowns that only
emerge at scale, such as retry storms; what an orchestrator does for the system
(rescheduling after a machine is lost, readiness gating, rolling updates,
autoscaling: the bench is compose only, see `bench.md`); and a protocol's
correctness over all interleavings, which is a job for a model checker (TLA+, P) and belongs in the
report as "model-checked", a separate rung from measurement.

## Shrinking the design to one machine

The rule comes from TPC-C, which fixes the ratio between load, data and storage and
requires all three to scale together.

**Keep at the design's value:** the load per node; the data per node; the ratio of
data to memory on a store node; partitions per consumer; the replication factor and
the durability settings (synchronous commit, fsync, acks); fan-out per request; the
timeouts, tick intervals and batch sizes of the design.

**Reduce:** the number of nodes, and with it the total rate and total data, by the
same factor.

**Never** shrink the data alone (everything then fits in memory and every read is
fast), turn durability off to "save time", or run a store on a memory filesystem.

Worked example: the page has 8 store nodes, each 64 GB of memory, holding 100 GB of
hot data and taking 300 writes/s. The bench runs 1 store node limited to 6.4 GB,
seeded with 10 GB, at 300 writes/s. Per-node rate: kept. Data to memory: 1.56, kept.
Scale factor 1/8 on node count, and 1/10 on the node's size, both stated.

If the machine is too small even for one node at design size, shrink the node and
its data and rate together, and mark every affected claim `scaled`.

## Load

**Open loop, always.** The page's rates ("40 runs per second") describe arrivals that
do not wait for the system. A generator that sends the next request only when the
last one answered (closed loop) slows down exactly when the system does, and hides
the queue. Schroeder et al. measured response times an order of magnitude apart
between the two models at the same load. Use an arrival rate, and measure latency
from the moment a request was *due* to be sent. A request the generator could not
send on time is a dropped request, and a run with drops is invalid (coordinated
omission: the slow moments are the ones that go unmeasured).

Where the load comes from depends on what creates work in the design:

| Work is created by | Load source |
|---|---|
| Clients calling an API | k6 with `constant-arrival-rate` (`templates/k6/load.js`) |
| Time (schedules, timers, TTLs) | Seeded rows that fall due during the run; the system creates its own load |
| An upstream stream | A producer at a fixed rate into the broker |
| A database workload | `pgbench --rate` or the store's own rate-limited driver |

**Shape matters more than volume.** Take the shape from the page: the burst at the
top of the minute, the skew between tenants, the share of slow and failing
dependencies. A uniform load at the average rate tests the easy case.

Which test answers which claim:

| Test | Load | Evidence for |
|---|---|---|
| Smoke | A trickle, a minute | The prototype and the bench work end to end |
| Steady | The design's rate, on aged data | Latency and loss targets "at normal load" |
| Ramp (breakpoint) | Steps upward until the target is missed | One node's capacity; the points for extrapolation; what gives way first |
| Spike | The design's worst second | Backlog bounds, priority, time to return to target |
| Overload and recovery | Above capacity, then back | It degrades as the page says and recovers without help |
| Fault | Steady load plus one fault | A failure path's end state and recovery time |
| Soak | Steady load for hours, compressed time | Nothing grows without bound; retention and cleanup keep up |
| Scale-out | The ramp repeated at 1, 2, 3… nodes | The points for the scalability fit |

## Is the bench sound

**Calibration** runs first and again whenever the bench changes
(`./run.sh calibration`). The standard checks, K1 to K8 in `templates/claims.json`:
the ledger counts every key once; it reports a planted duplicate; the load generator
delivers the highest planned rate with no drops and CPU to spare; the path through
the bench adds little compared with the tightest latency target; an injected delay
measures as asked; a CPU limit bites; every expected measured replica is sampled
with its configured CPU and memory limits and CPU set; the
host has room. Add one per datastore: the write rate the disk gives under its limit
(see `bench.md`, "Disk"). While any calibration check fails, `verdict.py` decides no
measured claim.

**Gates** are checked on every run: no dropped requests, the planned load delivered,
the host not saturated, no CPU pressure from outside the bench. A run that fails a
gate is not a failed claim; it is not a run.

The default G1/G2 gates require the k6 drop count, completed iterations and planned
arrivals (`load.offered`). For a timer- or stream-driven scenario, replace those
gates for that scenario with equivalent source metrics and expected arrivals.
Use the gate's `scenarios` list to scope each set. For a ramp, check delivery and
drops per step. Timed controls use the same gates as timed claims. A static check
can use `no_gates` to skip per-run gates while still requiring calibration.
Use `calibration_exemption` with a reason only for a measurement independent of
the calibrated bench.

**Controls** show a check can fail. For each guard the page relies on (a fencing
check in a write, a lease, an idempotency key), run once with the guard switched off
by a flag and confirm the check reports the fault. A claim guarded by a control that
has not been detected stays inconclusive.

Before reporting any number, answer Gregg's questions about it: Why not double? Was
it tuned? Did it break limits? Did it error? Does it reproduce? Does it matter? Did
it even happen?

## Statistics

- **Warm-up is discarded.** The load script runs a warm-up part and judges only the
  part after it. For anything with a cache, a pool or a compiler, check the first
  judged minute against the last; if they differ by more than the run-to-run spread,
  the warm-up was too short.
- **Steady state is checked, not assumed.** Split the judged window into five parts;
  the rate and the 99th percentile of each should stay within 20% of the window's
  value with no trend. TPC-C says it plainly: steady state "is easy to define but
  difficult to prove", so the report says how it was checked.
- **The window covers the system's longest period several times**: three or more
  ticks, checkpoint intervals, lease terms, compaction cycles. A 60 s window cannot
  judge a system with a 5-minute checkpoint.
- **Percentiles come from all the samples of the window.** Never average the
  percentiles of several windows or several nodes; merge the samples (or the
  histograms) and take the percentile once.
- **At least three runs per claim**, five when the result is within 20% of the
  target. Each run starts from the same state. Report the median and the range.
- **A claim holds only if every valid run passes.** Runs that disagree make it
  inconclusive: the margin is inside the noise, and the page's number is too close to
  the edge to promise.
- **Enough samples for the percentile.** A 99.9th percentile needs tens of thousands
  of samples in the window; with fewer, report the 99th.

## What gave way first

A failed latency target is a symptom. For every unit, `cgsample.py summarize` gives
the three things the USE method asks of each resource: utilization (CPU and memory
against the limit), saturation (share of periods throttled, pressure), errors (OOM
kills, restarts). Read them in this order:

1. A unit with `throttled_share` well above zero or `cpu_util_max` near 1: CPU-bound
   at its limit. More of that unit helps, if the design allows more.
2. Disk pressure (`psi_io`) or write IOPS at the calibrated ceiling on a store.
3. Nothing saturated, yet the rate stops rising: the limit is in the software. A
   lock, a serial loop, one round trip per item, a pool too small. Take a CPU profile
   and count round trips per unit of work. This is the most valuable case.

Cross-check with Little's law (`queueing.py little`): in-flight count = rate × time
in system. If the three measured numbers disagree by more than 10%, the run was not
steady or a number is wrong. The same law sizes pools on paper: 50 workers that each
hold a job for 10 s start at most 5 jobs a second, whatever else is tuned.

## Extrapolating

Use `usl.py` to fit the Universal Scalability Law to ramp results at several node
(or partition, or worker) counts.

- Each point is the highest rate **that still met the latency target** at that count.
- At least 6 points for a prediction worth quoting; fewer than 4 cannot be fitted.
- Judge the claim against `predicted_low` (the bottom of the leave-one-out range).
- Do not quote a prediction beyond 4 times the largest measured count as anything
  but an upper bound. Limits that appear only beyond the measured range are invisible
  to the fit. Gunther: it "is not a crystal ball".
- The fit can firmly show that a design will **not** scale (a peak before the
  design's node count). It can only say that nothing measured prevents scaling.

Storage after N days is `bytes per row measured on aged data × rows per day × days`,
re-run by script with the measured row size in place of the page's assumption.

## Failures

Each failure path of the page becomes an experiment in the form the chaos-engineering
principles give: state the steady state as a measurable output, inject the fault
under load, and try to disprove that the steady state returns.

1. Start steady load; wait for the window to be steady.
2. Inject one fault at a recorded moment (`bench.md` lists them).
3. Keep the load on. Remove the fault if it is a temporary one.
4. Stop the load and **drain**: wait longer than the design's longest retry, lease or
   timeout, so every in-flight item reaches a final state.
5. Check the invariants on the ledger and in the store.

The invariants, with where the numbers come from:

| Promise | Check |
|---|---|
| Nothing accepted is lost | Every key the caller got an acknowledgement for (or every due row in the store) appears in the sink's ledger as done, or ends in the named final state (`dead`, `expired`) |
| At-least-once, duplicates bounded | `duplicate_effects` ≤ the number in flight when the fault hit; zero in runs without a fault |
| Duplicates are harmless | With the sink as an idempotent receiver (`idem=1`), `duplicate_effects` = 0 and `deduped` > 0 |
| Every item ends in a named state | A query on the store: no row left in a non-final state after the drain |
| One owner at a time | No two units acted on the same key in overlapping intervals (from the ledger's arrivals) |
| Recovery time | Time from the fault to the first second in which the delay is back under target |

Choose the fault by what the failure path names. The **freeze** (a process paused,
then resumed, still believing it holds its lease) is the test for fencing, leases
and heartbeats; a crash does not test them, because a dead process writes nothing.
Time the fault to land mid-burst, not between bursts, and repeat it at several
moments: a kill that lands in a quiet second tests nothing.

## Long uptime in a short run

A system that has run for 30 days differs from a fresh one in three ways: the
amount of data, the wear in the data (dead rows, fragmented indexes, tombstones,
compaction levels), and slow growth (leaks, logs, queues that never quite drain).
Each needs its own treatment.

1. **Amount: seed to the steady-state size.** Size = rate × retention, at the bench's
   scale. Load it in bulk before the run (`bench.md`, "Ageing data"), with the
   design's distributions: tenant skew, state mix (mostly final rows, a few open),
   time spread across the retention window.
2. **Wear: churn it.** Freshly loaded data is the best case; results on un-aged
   storage have been measured up to 75% too optimistic on SSDs. After the bulk load,
   run the write path (updates, deletes, expiry) until the store's own wear measures
   are steady: dead-row share, table size against live size, compaction backlog. Then
   snapshot the volume so every run starts from the same aged state.
3. **Slow growth: compress time and watch slopes.** Run the prototype with a clock
   scale (`CLOCK_SCALE=60`: one bench minute stands for one design hour) so that many
   retention, cleanup and lease cycles pass in an hour or two. Fit a line to memory,
   table size, backlog and the per-window 99th percentile; a slope that does not
   include zero is growth. Extrapolate it to the design's horizon and compare with
   the limit.

Rules for compressed time:

- **Compress waiting, never work.** Intervals between events shrink (schedules,
  retention periods, cleanup intervals, lease terms that exist to bound waiting).
  Service times, timeouts on real calls and the rate per second do not.
- Compression multiplies the *event* rate of anything driven by the clock. Keep the
  per-second load at the design's value by thinning the population, or the run turns
  into a stress test.
- At least three full cycles of the slowest periodic process (retention, compaction)
  must pass inside the judged window.
- The prototype reads time from one injectable clock. Do not fake the clock from
  outside: `libfaketime` does not work on statically linked or Go binaries, and
  shifting a container's clock tests clock jumps, which is a fault, not ageing.

What this supports: the cleanup mechanisms run and keep up at the design's write
rate; nothing measured grows without bound over the cycles observed; latency on
30-day-sized, worn data meets the target. What it does not: effects that need real
elapsed time (certificate expiry, counters that wrap, the hardware's own wear).
State both in the report.

## What the report must state

Borrowed from TPC's full-disclosure rule: a reader must be able to repeat the run
and to see what was not covered.

- The machine (CPU model and which cores, memory, disk model), kernel, Docker
  version, and the limits of every unit.
- The scale statement: what was kept, what was reduced, by how much.
- Product versions and every setting that differs from the product's default.
- For each scenario: rate and shape, duration, warm-up, data present, fault and its
  moment, number of runs.
- The calibration results and any control.
- Every claim with its verdict, class, measured median and range, and conditions.
- Every claim not tested, with the reason.
- What gave way first, with the evidence.
- The commands to run it again.

## Sources

- Schroeder, Wierman, Harchol-Balter, "Open Versus Closed: A Cautionary Tale", NSDI 2006. https://www.usenix.org/legacy/event/nsdi06/tech/full_papers/schroeder/schroeder.pdf
- Gil Tene, wrk2 (constant rate, latency from the intended send time). https://github.com/giltene/wrk2
- k6, open and closed models; thresholds; test types. https://grafana.com/docs/k6/latest/using-k6/scenarios/concepts/open-vs-closed/ , https://grafana.com/docs/k6/latest/using-k6/thresholds/ , https://grafana.com/docs/k6/latest/testing-guides/test-types/
- Neil Gunther, the Universal Scalability Law. http://www.perfdynamics.com/Manifesto/USLscalability.html
- Brendan Gregg, the USE method; active benchmarking; benchmarking checklist. https://www.brendangregg.com/usemethod.html , https://www.brendangregg.com/activebenchmarking.html , https://www.brendangregg.com/blog/2018-06-30/benchmarking-checklist.html
- Georges, Buytaert, Eeckhout, "Statistically Rigorous Java Performance Evaluation", OOPSLA 2007 (independent runs, steady state by variation). https://dri.es/files/oopsla07-georges.pdf
- Gil Tene, "You can't average percentiles". https://latencytipoftheday.blogspot.com/2014/06/latencytipoftheday-you-cant-average.html
- Raasveldt et al., "Fair Benchmarking Considered Difficult", DBTest 2018. https://mytherin.github.io/papers/2018-dbtest.pdf
- TPC-C specification (proportional scaling, steady state, measurement interval, full disclosure). https://www.tpc.org/tpc_documents_current_versions/pdf/tpc-c_v5.11.0.pdf
- Jepsen (generator, nemesis, history, checker; what a test can show). https://github.com/jepsen-io/jepsen , https://jepsen.io/ethics
- Principles of Chaos Engineering. https://principlesofchaos.org/
- Google SRE book, "Addressing Cascading Failures" (test until it breaks; recovery without help). https://sre.google/sre-book/addressing-cascading-failures/
- Kadekodi et al., "Geriatrix: Aging what you see and what you don't see", USENIX ATC 2018 (un-aged storage flatters results). https://www.usenix.org/conference/atc18/presentation/kadekodi
- Newcombe et al., "How Amazon Web Services Uses Formal Methods" (what model checking covers and does not). https://lamport.azurewebsites.net/tla/formal-methods-amazon.pdf
- Joel Teodoro, "Load-testing a distributed job scheduler on an AWS-shaped bench" (calibration first; measure at the receiver; cloud shapes on one machine). https://runtimerants.dev/posts/distributed-job-scheduler-benchmarks
