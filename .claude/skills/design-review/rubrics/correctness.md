# Pass: correctness

Failure paths end somewhere defined, and concurrent writes are guarded.

## Check

1. **Failure walkthroughs.** Trace one unit of work through each bad path the design implies: crash between two non-transactional writes, owner loses its lease mid-operation, worker dies, cancel while queued or running, manual retry, failover during peak load. For each, name who notices, what state the item ends in, and whether anything is lost or duplicated. Flag a path with no owner or no end state.
2. **Race guards.** Every write two actors could make concurrently carries its guard in the write itself (a version, epoch, attempt or state predicate in the WHERE clause, a unique constraint). Flag guards that live only in memory or in an earlier read.
3. **Cross-cutting checks.** When an operation adds a new condition (a job can be cancelled or paused), every path that continues work (retries, next-run creation, reaper resets) checks it.

## Evidence

Quote the step or statement where the path ends without a defined outcome, or the unguarded write.

## Severity

- high: work can be silently lost, or a stale actor can overwrite newer state.
- medium: a path that ends correctly only by accident or relies on an unstated check.
- low: a path that is handled but not described.
