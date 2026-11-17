# Pass: terminology

The core domain terms are defined once, before they are needed, and every later use keeps that meaning.

## Check

Core terms are the nouns the design is built on: what clients create, what the system produces and tracks, and the unit of work. A noun is core if it is a table, a state machine, an API resource or the subject of a guarantee (for a scheduler: job, run, attempt). Build a table first: term, its definition (quoted), where and at which depth it is defined, synonyms seen, and every use that does not fit. Search for each word; do not sample.

1. **Core terms are defined.** Each has an explicit definition that says what it is and how it relates to the others (one job has many runs; a run has one or more attempts). A column or table name is not a definition. Flag a core term with none.
2. **Defined before use, at the lowest depth.** The definitions come before the first section that depends on them, normally before Requirements, and are visible at the lowest depth level. Flag a term whose only definition is in a later section or at a deeper level.
3. **One meaning per term.** Flag a use that means a different entity: the definition where an instance is meant ("the job is retried" when a run is retried), an instance where a single try is meant, or the term used for something outside the model ("a background job" for a system process). A verb is not a misuse ("the worker runs the job").
4. **One term per meaning.** List the other words used for each core entity (execution, invocation, task, firing, instance, occurrence, request). Flag one that stands in for a core term, unless the page defines it as a separate thing. A product's own noun (ECS task, Kafka partition) is fine where it names that product's object.
5. **Definitions agree with the design.** Compare each definition with the schema, the state machine, the API and the guarantees. Flag a contradiction: a run defined as "one execution" on a page that retries runs, a cardinality the schema does not allow, a term defined as fixed that the API edits.
6. **Labels follow the text.** Diagram labels, table headings, captions, glossary and tooltip entries, example data and demo controls use the same terms. Identifiers in code and SQL may differ if the page says how they map.

## Evidence

Quote the sentence that misuses the term or contradicts the definition. For a missing or late definition, quote the first sentence that relies on the term. For text a script generates (tooltips, demo labels), quote the nearest static text and name the string in `why`.

Report repeated loose uses of one term as a single finding: quote the clearest instance and list the other places in `fix`.

## Severity

- high: a core term is undefined, or its definition contradicts a guarantee, the schema or the state machine, so a guarantee can be read two ways.
- medium: a term defined after it is first needed or only at a deeper level; a term used for a different entity where the difference changes what is retried, counted, cancelled or deduplicated.
- low: a stray synonym or loose use where the meaning is still clear.
