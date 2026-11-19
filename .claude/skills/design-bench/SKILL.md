---
name: design-bench
description: Build a working prototype of a system design page and load-test it against the page's own numbers, on this machine in docker compose, with resource limits, injected delays and failures, and data aged to the design's retention; then publish a bench report with a verdict per claim (verified, failed, extrapolated, not testable) and bring the results back to the page. Use when the user asks to prototype, benchmark, load-test, stress-test or prove a design page or its numbers (for example "bench the job scheduler page", "does the matchmaker design hold its numbers", "build a prototype for pages/x.html and load-test it", "prove NFR2"), to re-run a bench after the design or the prototype changed, or to continue one in progress ("continue the bench", "I decided on the bench board").
---

# Design bench

Takes one design page and answers one question: **does a system built as the page
says meet the numbers the page states?** It builds the smallest prototype that can
answer, runs it inside a bench that limits resources, adds delays, injects failures
and ages the data, and judges every claim by rule.

The bench runs in docker compose. Compose reproduces everything that decides
performance and failure behaviour; what an orchestrator does for a system
(rescheduling, readiness gating, rolling updates, autoscaling) is out of reach and
is marked untestable.

The result is evidence, not proof: a claim that survives was not disproved under the
conditions tested. The most useful result is a contradiction: a number the page
derives that the prototype does not reach, and why.

Files in this skill:

- `reference/method.md`: how a page becomes claims, the evidence classes, how to
  shrink a design to one machine, load, calibration, statistics, failures, long
  uptime, and the sources. **Read it before writing a plan.**
- `reference/bench.md`: the recipes for limits, delays, failures, ageing and time,
  each with the check that proves it on this machine. **Read it before building.**
- `scripts/preflight.py`: what this machine offers and what would spoil a measurement.
- `scripts/cgsample.py`: samples CPU, throttling, memory, disk and pressure of every
  container from the kernel's cgroup files; summarizes a window.
- `scripts/verdict.py`: `flatten` merges a run's outputs into named numbers; `judge`
  turns claims and runs into verdicts by fixed rules.
- `scripts/usl.py`: fits the scalability law to measured points and extrapolates with
  its error range. `scripts/queueing.py`: Little's law and the M/M/c queue.
- `scripts/report.py`: fills the report page from the verdicts and your notes.
- `templates/`: `plan.md`, `claims.json`, `compose.yaml`, `bench.env`,
  `toxiproxy.json`, `run.sh` (the bench's verbs and the calibration scenario),
  `k6/load.js` (open-loop load), `sink/` (the stand-in for outside dependencies, with
  the ledger of arrivals), `report.html`.

The board is the one from `design-page` (`.claude/skills/design-page/templates/board.html`);
its item kinds, decisions and gate steps are described in that skill's "The design
board" and "Running a stage", and apply here unchanged.

## Where things live

| Path | Holds | In git |
|---|---|---|
| `bench/<slug>/` | `plan.md`, `claims.json`, the prototype's source, `compose.yaml`, `bench.env`, `run.sh`, seed scripts, `scale.py` | yes |
| `bench/<slug>/results/<scenario>/<run>/` | `metrics.json` and the files it was built from | yes, except `samples.jsonl` |
| `bench/<slug>/verdicts.json`, `notes.json` | The judged results and what you wrote about them | yes |
| `drafts/<slug>/bench-board.html`, `bench-board.url` | The bench board and its artifact URL | no |
| `drafts/<slug>/bench-report.html`, `bench-report.url` | The report and its artifact URL | no |

`<slug>` is the page's file name without `.html`.

## Stages

| # | Stage | What you do | Ends with |
|---|---|---|---|
| 1 | `plan` | Claims, scale, prototype scope, bench, data, scenarios | **Gate** on the board |
| 2 | `build` | Prototype, bench, calibration, smoke run | A line in the terminal; go on |
| 3 | `run` | Age the data, run every scenario and control, judge, find what gave way | The report |
| 4 | `results` | Report published; decisions on what each failed claim means for the page | **Gate** on the board |
| 5 | `apply` | Results into the ledger and the page; re-run if the design changed | A report in the terminal |

Two gates only. Building and running are yours to do without stopping, once the plan
is approved. Stop early only if calibration cannot be made to pass, a claim in the
plan turns out untestable, or a run would need something the plan did not get
approved (more time, more disk, installing software).

If the user says to skip the gates ("just run it"), take your recommended options,
say so in one line, and still publish the board and the report.

### 1. `plan`

1. Run `python3 .claude/skills/design-bench/scripts/preflight.py`. Resolve every
   PROBLEM line before going on; carry every note into the plan.
2. Read the page in full (`python3 .claude/skills/design-review/scripts/levels.py pages/<slug>.html --level 3`
   shows all of it), and `drafts/<slug>/ledger.md` if it exists: its Requirements,
   Numbers, Failure paths and Claims parts are the inventory to mine.
3. Copy `templates/plan.md` to `bench/<slug>/plan.md` and `templates/claims.json` to
   `bench/<slug>/claims.json`. Fill both:
   - **Claims.** Every sentence a measurement could contradict, with the five parts
     `method.md` asks for. Aim to cover every numbered requirement, every derived
     number that drives the design, and every failure path. Mark what one machine
     cannot show as untestable, with the reason; do not approximate it silently.
   - **Scale.** What is kept at the design's value and what is reduced. Compute it
     with a script (`bench/<slug>/scale.py`), as the page's numbers are.
   - **Prototype.** Which components are built and which are left out, and every
     setting taken from the page.
   - **Bench.** The units with their limits, the delays and where each number comes
     from.
   - **Data.** Size at steady state, how it is seeded, aged and snapshotted; the
     clock scale for the soak.
   - **Scenarios**, with runs and the claims each one judges, the controls, and the
     time for one full pass.
4. Put the plan on the board. First time: copy the board template to
   `drafts/<slug>/bench-board.html`. Board data: `"design": {"title": "<short title> bench", "board": "Bench board", "slug": …, "source": …, "updated": …}`,
   `"order": [["plan", "Plan"], ["results", "Results"]]`, `"stage": "plan"`, and one
   stage with:
   - questions (three real options each, yours first) for the forks that are the
     user's: how far to shrink (and what that moves from measured to scaled); which failure paths to test when time is
     short; the time budget, especially the soak; anything that needs installing.
   - one section card per plan part: the claims table, what is not testable and why,
     the scale table, the prototype scope, the bench, the data, the scenarios.
   Publish it as `design-page` describes (`icon: "checklist"`,
   `capabilities: {"db": {}, "user": {"scopes": ["profile"]}}`), save the URL to
   `drafts/<slug>/bench-board.url`, and stop at the gate.
5. When the user returns, read and take in the decisions as `design-page` describes
   ("Running a stage", steps 5 to 8), recording them in the plan's Decisions table.

### 2. `build`

Read `reference/bench.md` first.

**The prototype tests the page's design, not a better one.**

- Build only the path a claim needs. A component the page makes a separate process is
  a separate process here, because the boundaries are what is being tested. Leave out
  authentication, admin endpoints and anything no claim touches; list what was left
  out in the plan.
- Write each write the way the page writes it: the same statement, the same guard,
  the same transaction boundaries, the same order. If the design does not work as
  written, that is a finding. Do not repair it quietly; record it and ask at the
  results gate.
- Where the page is silent and the choice matters (batch or row by row, pool size,
  poll interval), take the plainest reading, write it in the plan, and expect it to
  come back as a finding if it decides a result.
- Use the stores and brokers the page names, at the version it names, with its
  durability settings. Every outside dependency is the sink.
- Go by default: one static binary per component, each in its own directory with a
  Dockerfile shaped like `templates/sink/Dockerfile`.
- Every component reads time from one scalable clock (`bench.md`, "Time"), exposes
  `/healthz`, and passes the unit of work's id and due time on to the sink.
- Every guard the page relies on (a fencing check, a lease check, an idempotency key)
  gets an environment switch that turns it off, used only by controls.
- A prototype is usually a few hundred to a couple of thousand lines. If it grows past
  that, the scope is wider than the claims need.

**The bench.** Copy `compose.yaml`, `bench.env`, `toxiproxy.json`, `run.sh`, `k6/`
and `sink/` from `templates/` into `bench/<slug>/`. Fill `bench.env` from preflight.
Add one block per component and store, each with its limits, each hop through the
proxy. Write the scenarios of the plan as `scenario_<name>` functions in `run.sh`,
following the two shapes shown there.

**Calibrate, then smoke.**

```sh
cd bench/<slug>
MAX_RATE=<highest planned rate> ./run.sh calibration
python3 ../../.claude/skills/design-bench/scripts/verdict.py judge claims.json results
./run.sh smoke
```

Every calibration line must read "Holds" (set K4's target to a tenth of the tightest
latency target; add a disk check per store). Calibration starts the default Compose
services after testing the harness in isolation. Configure measured services in
the default profile with `cpus`, `mem_limit` and `cpuset`, and make them start
against an empty or already initialized store. K7 checks each replica against those
settings. If a check fails, fix the bench before judging measured claims.

### 3. `run`

1. **Age the data** as the plan says (seed, churn, snapshot). Check the seeded size
   and the bytes per row against the page: these are claims too.
2. **Run the scenarios**, one at a time, never two at once. Before each run: restore
   the snapshot, reset the sink, remove every delay and cut. Order: steady, ramp,
   spike, each fault (at several moments, mid-burst), each control, soak, scale-out.
   A long run goes in the background; wait for it to finish instead of polling.
3. **Judge**: `verdict.py judge claims.json results --out verdicts.json`. Runs that
   failed a gate are not results: find out why and run again.
4. **Explain every claim that did not hold, before reporting it.** Read the resources
   of the window (`resources.json`): which unit was at its limit, throttled or under
   pressure. If none was, the limit is in the software: profile, count round trips
   per unit of work, check pool and batch sizes. Check the result with Little's law
   (`queueing.py little`). Then decide whose limit it is:
   - **the prototype's** (your bug, or a choice the page did not make and that you
     made badly): fix it, note it in the plan's results log, re-run what it touched;
   - **the design's** (it follows from what the page states, or the page is silent
     where the choice decides the result): it is a finding. Measure the fix in
     isolation if one is obvious, so the board can offer it with a number.
5. **Extrapolate** the cluster-level claims with `usl.py` from the scale-out points;
   put its JSON through `verdict.py flatten usl=…` into `results/model-usl/fit/metrics.json`.
6. **Controls**: every correctness claim that passed must have a control that was
   detected. An undetected control means the check is blind; fix the check.

### 4. `results`

1. Write `bench/<slug>/notes.json` (shape in `scripts/report.py`): a two-sentence
   lead (what held, what gave way first), one finding per contradiction with its
   evidence, the curves worth showing (delay against offered rate; throughput against
   node count with the fit), the scenarios, and the commands to run it again.
2. Build and publish the report:
   ```sh
   python3 .claude/skills/design-bench/scripts/report.py bench/<slug>/verdicts.json bench/<slug>/notes.json drafts/<slug>/bench-report.html
   ```
   Publish with the Artifact tool (`icon: "gauge"`, a one-sentence `description`, no
   capabilities). Save the URL to `drafts/<slug>/bench-report.url`.
3. Add the `results` stage to the board, with the report URL in `report` and
   `"report_label": "Open the bench report"`:
   - one **question** per claim that failed, is inconclusive because runs disagree,
     or whose extrapolation does not hold. Three options, the one you recommend
     first, each with what it costs. They are usually of these kinds: change the
     design (name the change and what it does to the other numbers); change the
     promise on the page to what was measured; keep the promise and state the
     condition under which it holds.
   - one **section** with the measurements to add to the page and the ledger, in the
     page's own words.
   - one **section** listing what was not tested and why.
   Republish the board and stop at the gate, with: both links, the verdict counts,
   what gave way first in one line, and each question in one line with your
   recommendation.
4. Take the bench down and say what was left behind (volumes, images):
   `docker compose --env-file bench.env --profile load --profile calibration down -v`.
   Keep an aged snapshot volume only if a re-run is likely, and say how large it is.

### 5. `apply`

After the user's decisions, ledger first, as `design-page` requires:

- Measurements go into the ledger's **Measurements** part and then into the page,
  each with its conditions ("on one node limited to 2 CPUs and 4 GB"). A measured
  number replaces an assumed one only together with the formula that used it; run
  the page's `numbers.py` and `check_page.py … --numbers` afterwards.
- A changed design changes the ledger, the page, the plan, `claims.json` and the
  prototype, in that order, and the affected scenarios run again. A second pass adds
  a line to the plan's results log, republishes the report (same file path), and
  returns to the results gate if a verdict changed.
- A changed promise is edited on the page where the quote is; update the claim's
  quote and target in `claims.json` to match.
- Run `python3 scripts/build.py` and `make test`. Do not commit unless asked.
- Report: the files, both links, the verdict counts before and after, what changed
  on the page, and every claim still failed, inconclusive or untested, with the reason.

## Re-running

"Re-run the bench" after a change: read `bench/<slug>/plan.md` and `claims.json`,
check every claim's quote is still in the page (a missing quote is a stale claim: fix
it before running), run calibration again, then stages 3 to 5. Keep earlier runs;
name new ones by date so `verdict.py` judges the set you mean (move superseded runs
to `results-<date>/`).

For a bench copied from an older template, bring over the current calibration
function and K7 metric (`calib.limit_problems`). Update G1/G2 to require load
evidence for each timed scenario and control. Preserve the bench's custom
scenarios and targets, then collect fresh calibration and run evidence.

## Rules that are easy to break

- **Never judge by eye.** A claim's verdict is what `verdict.py` prints. If the rule
  gives the wrong answer, the claim or its check is written wrong: fix that.
- **Never loosen a target, a gate or a calibration check to get a pass.** Targets come
  from the page; changing one is a decision for the results gate.
- **Open loop only**, and a run with dropped requests is not a run.
- **Measure where the client observes**: at the sink and at the caller, not in the
  system's own bookkeeping.
- **Everything measured has limits and is pinned**; the load generator and the
  stand-ins never share its CPUs.
- **Never shrink the data alone**, switch off durability, or use a memory filesystem
  for a store.
- **A check that has never failed proves nothing**: every correctness claim has a
  control.
- **Say "holds" or "verified under these conditions", never "proven".** Never report a
  scaled or extrapolated result as measured.
- **A failed claim is reported with its cause**, and the cause is assigned to the
  prototype or to the design before it reaches the board.
- **Touch only the bench's own containers, volumes and ports.** Other projects run on
  this machine. Ask before installing anything or before using more
  disk or time than the plan had approved.
- **Calibrate again whenever the bench changes**: a new limit, a new hop, a Docker
  or kernel upgrade.
