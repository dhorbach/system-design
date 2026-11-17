# Regression set

Issues a human reviewer flagged in an annotation session on 2026-11-17. The
reviewer should find each of them in the listed revision. Quotes are exact
visible text from that revision.

Source: `pages/distributed-job-scheduler.html` at revision `79bbdcc`.

| # | Pass | Section | Quote | Expected finding |
|---|---|---|---|---|
| R1 | framing | Problem | "The features fit in one sentence. The hard part is the guarantees around them, which the non-functional requirements spell out." | Low-value framing in the Problem section; remove it. |
| R2 | requirements | Requirements (NFR2, Fire on time) | "Runs are loaded about 30 seconds ahead and fired from memory" | Mechanism in a requirement; state the bound on lateness instead. |
| R3 | requirements | Requirements (NFR3, at least once) | "Writes are fenced on epoch and attempt, and every run carries an idempotency key" | Mechanism in a requirement. The same pass should also catch the outbox and sweeper (NFR1), lazy cancellation (FR2), copying policies onto runs (FR3) and per-tenant queues (NFR5), and the design choice "Partitions and leases at small scale" listed as out of scope. |
| R4 | framing | Back-of-the-envelope estimates | "The averages are small. The worst second is 750 times the average, and that one second drives the design." | The section opens with a result before saying what is being estimated or how the two tables relate. |
| R5 | data-model | API service / Job store | "stops the job from creating new runs and deletes its pending ones" | Cancel leaves no record on the job: no status column, and cancel only works because the cron chain breaks. `jobs` and `runs` also lack `created_at`/`updated_at`, and `runs` has no start/finish times or last error. |
| R6 | data-model | Job store (indexes) | "(tenant_id, state)" | Index on a column that the `runs` schema does not list. |
| R7 | assumptions | Job store (example rows) | "The request column holds what to call:" | A job is modelled only as an HTTP request; a job could be a container task or another kind. Generalise to kind plus spec. |

## Cases added with later passes

Same source and revision. R8 to R10 were raised in a terminology session on 2026-11-17 and the author accepted the fix. R11 and R12 were written together with the simplicity rubric and have not been confirmed by a human reviewer: confirm or delete them after the first calibration run.

| # | Pass | Section | Quote | Expected finding |
|---|---|---|---|---|
| R8 | terminology | Requirements (FR4) | "Failed runs retry with backoff; runs that use up their attempts are kept for inspection and manual retry." | Job, run and attempt are used from Requirements onward but never defined. The only description is a table in Job store, visible from level 2. Define them before Requirements, at level 1. |
| R9 | terminology | Job store | "runs: one row per execution." | A run is described as one execution, but runs are retried, so one run can execute several times. A run is one scheduled occurrence of a job; an attempt is one execution of it. |
| R10 | terminology | Timing wheel | "so a former owner stops firing jobs it no longer owns" | "Job" used where a run is meant. One finding should also list "a job ten laps out is visited ten times before it fires" and "fires 120 executions back to back" (Behaviour under load). |
| R11 | simplicity | Behaviour under load | "Most real-world failures of schedulers are failures of peak behaviour, so design for these cases explicitly." | Level 1 states the problem and stops. The ideas that answer it (a misfire policy per job, priority applied when runs are created, fairness between tenants) appear only at level 2. |
| R12 | simplicity | Scheduler | "Twelve partitions are shown, each with its owner and epoch" | A level-1 caption rests on "epoch", which is explained only at level 2 (Leases). |

## How the fixes looked

These are the edits the human accepted, useful as worked examples of the `fix` field:

- R2: "When a scheduler node crashes, the runs it owned may start late, but by a bounded amount: typically 10–30 s."
- R3: "A run may execute more than once, but the receiver can always recognise a repeat, and a late result from an old attempt never overwrites a newer one."
- R4: Open with "Before choosing components, size the system: how many runs it executes, how unevenly they arrive, how much it stores and how many job calls are in flight at once." and add "The first table lists assumptions for a mid-sized platform; the second shows what follows from them."
- R5: Add `status` (active, cancelled) and timestamps to `jobs`; add a `cancelled` run state; make next-run creation and retries check that the job is active.
- R7: Replace `request` with `kind` (http, container) and `spec`; describe workers as one executor pool per kind; add notes on long-running container jobs.
- R8: Add a Terminology section between Problem and Requirements: a three-row table (job, run, attempt) at level 1, how they relate at level 2, and the neighbouring words (execute, fire, task, worker) at level 3.
- R9: "One scheduled occurrence of a job" in the record table and "one row per scheduled occurrence" in the schema.
- R10: "so a former owner stops firing runs it no longer owns"; the timing wheel section and its demo talk about runs throughout.
