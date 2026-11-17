# Pass: requirements

Requirements state what the system must guarantee, measurably where possible. They do not describe how.

## Check

1. **Mechanism in requirements.** Flag any requirement (functional or non-functional, at any depth level) that names an implementation device: specific data structures, protocols, tokens, tables, queues, caches, polling intervals, lookahead windows, outboxes, fencing, epochs, leases, idempotency keys, SQL, indexes, specific products. The requirement should state the observable guarantee; the mechanism belongs in the design section, which the requirement may link to.
2. **Measurable targets.** Non-functional requirements give a number or a bound where one is meaningful (latency, throughput, recovery time, retention). Flag vague ones ("fast", "scalable") only if the page has the number elsewhere.
3. **Traceability.** Every requirement is delivered by some section; every major mechanism serves some requirement. Flag a requirement nothing delivers, and a mechanism no requirement needs.
4. **Out of scope holds scope, not design choices.** Flag "out of scope" items that are really decisions about the design ("partitions are not needed at small scale").

## Evidence

Quote the phrase that names the mechanism, or the requirement with no delivering section.

## Severity

- high: a requirement that is only a mechanism, with no guarantee stated.
- medium: a guarantee mixed with mechanism detail.
- low: a missing link or a vague target where the number exists elsewhere.

## Rewrite pattern

"Writes are fenced on epoch and attempt, and every run carries an idempotency key"
becomes "A run may execute more than once, but the receiver can always recognise a repeat, and a late result from an old attempt never overwrites a newer one."
