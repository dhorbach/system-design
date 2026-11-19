# Bench plan: TODO short title

Page: `pages/TODO.html`. Ledger: `drafts/TODO/ledger.md` (if there is one).
Bench: `bench/TODO/`. Board: see `board.url`. Report: see `report.url`.
Machine: TODO one line from `preflight.py`.

## Decisions

| Item | Choice | What it fixes |
|---|---|---|

## Claims

Every sentence of the page a measurement could contradict. `claims.json` holds the
same list in the form `verdict.py` reads; change both together.

| ID | Quote from the page | Metric, measured where | Target | Conditions: load, data, fault | Class | Scenario |
|---|---|---|---|---|---|---|
| TODO | | | | | measured | |

Not testable on this machine:

| ID | Quote | Why not | What would test it |
|---|---|---|---|

## Scale

What is kept at the design's value and what is reduced (see `reference/method.md`,
"Shrinking the design to one machine"). Computed by `scale.py`, not by hand.

| Quantity | Design | Bench | Kept or reduced |
|---|---|---|---|
| Nodes of TODO | | | reduced, 1 of N |
| Rate per node | | | kept |
| Data per node | | | kept |
| Data to memory on a store node | | | kept |

Scale statement for the report: TODO one sentence.

## Prototype

What is built, and what is left out. Only the parts a claim needs.

| Component of the page | In the prototype | Why, or why left out |
|---|---|---|

Outside dependencies played by the sink: TODO. Mix of fast, slow and failing: TODO.

Settings taken from the page (timeouts, ticks, batch sizes, pool sizes, durability):

| Setting | Value | Where the page states it |
|---|---|---|

## Critical-path tests

Record the paths and case names in `tests/contract.json`. Give each path unit
cases for its local decisions and integration cases that exercise the real
storage boundary. Name the test stores and how the suite checks committed state.

| Code path or invariant | Unit cases | Real storage integration cases |
|---|---|---|

Run `./run.sh test` for the current sources before calibration.

## Bench

| Unit | CPUs (limit, set) | Memory | Disk limit | Reached through |
|---|---|---|---|---|

Delays: TODO which hops, how many ms, and where the number comes from.

## Data

| Store | Rows and size at steady state | How seeded | How aged | Snapshot |
|---|---|---|---|---|

Clock scale for the soak: TODO, and which intervals it shortens.

## Scenarios

| Scenario | Load: rate and shape | Duration, warm-up | Data | Fault and moment | Runs | Claims |
|---|---|---|---|---|---|---|
| calibration | bench's own checks | 2 min | none | none | 1 | K1–K8 |
| smoke | | | | | 1 | |
| steady | | | aged | none | 3 | |
| ramp | | | aged | none | 3 | |

Controls (a planted fault each check must catch):

| ID | Guard switched off | Scenario | Check that must report it | Guards claims |
|---|---|---|---|---|

Time budget: TODO total minutes for one full pass.

## Results log

One line per pass: date, what changed in the prototype or bench since the last pass,
the verdict counts, what gave way first.
