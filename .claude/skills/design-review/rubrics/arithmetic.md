# Pass: arithmetic

Every number follows from its stated inputs, and numbers agree across the page.

## Check

1. Recompute every derived number from its inputs (rates, totals, ratios, storage, concurrency). Allow rounding the page states ("about"). Show your working in `why`.
2. The same quantity has the same value everywhere it appears (for example writes per run, peak size, retention days).
3. Thresholds do not contradict each other (a "few thousand per second" limit against a stated peak of 30,000 in one second needs an explanation).
4. Units are consistent (per second vs per minute, KB vs KiB where it matters).

## Evidence

Quote the number that is wrong or inconsistent.

## Severity

- high: a wrong number that drives a design decision.
- medium: an inconsistency between two places.
- low: a rounding or unit slip with no consequence.
