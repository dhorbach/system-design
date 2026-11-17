# Pass: assumptions

The design does not silently narrow the problem.

## Check

1. **Over-specific abstractions.** A core entity modelled as one concrete case when the problem is broader: a "job" that can only be an HTTP request, a "notification" that is only email, a "file" that is only an image. Look at schema columns, API bodies and examples for a single concrete shape (url, method, headers) standing in for the general concept.
2. **Unstated workload assumptions.** Estimates and mechanisms that rely on a property the requirements never state (all jobs take 2 s; all clients are internal; one region). Flag where the assumption drives a design choice.
3. **Generalisation path.** If the page keeps a narrow scope on purpose, it says so in Requirements or Out of scope. Flag a narrow scope that is never stated.

## Evidence

Quote the column, field or sentence that encodes the narrow assumption.

## Severity

- high: the core entity cannot express common variants of the problem.
- medium: an unstated assumption that drives estimates or a component choice.
- low: an example that suggests a narrower scope than the text intends.

## Fix pattern

Name the general concept with a type discriminator and a type-specific payload (`kind` + `spec`), say which part of the design is independent of the type, and note what changes for the second type.
