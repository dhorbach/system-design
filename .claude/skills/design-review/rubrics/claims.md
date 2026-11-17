# Pass: claims

Technology-specific statements are correct and current.

## Check

List every claim about a named product, protocol, language runtime or standard (for example how Kafka commits offsets, which databases support SKIP LOCKED, MySQL gap locking at REPEATABLE READ, Go ticker behaviour, what a library does). For each, decide:

- correct as stated,
- needs a qualifier (version, configuration, default vs option),
- wrong.

Report only the last two. Do not search the web unless the orchestrator allows it; mark uncertain claims as low severity with "verify" in the title.

## Evidence

Quote the claim.

## Severity

- high: wrong, and the design relies on it.
- medium: true only under a configuration the page does not state.
- low: likely right but worth a check, or a missing qualifier.
