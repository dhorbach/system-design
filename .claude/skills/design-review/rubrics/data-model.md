# Pass: data-model

The schema, states and API agree with each other and record everything the design's behaviour needs.

## Check

1. **Every action leaves a record.** For each operation the API or text describes (create, edit, cancel, pause, retry, delete), find the column or state that records it. Flag operations that only delete rows or rely on a side effect (a chain breaking) instead of recording a status. Ask: can the system answer "was this cancelled, when, by whom" afterwards?
2. **Lifecycle and audit columns.** Long-lived tables have `created_at` and `updated_at`; entities with a lifecycle have a status column; executions have start and finish times and the last error if the page measures lag or shows failures.
3. **Referenced columns exist.** Every column used in an index, a query, a WHERE clause, an example row or the text exists in that table's schema. Flag an index on a column the table does not list.
4. **States are closed.** Every state in a diagram appears in the text and vice versa; every transition has a named writer; final states are stated correctly.
5. **API matches schema.** Every request body field maps to a column (or is explained as derived), and every column that clients set is reachable from the API.

## Evidence

Quote the schema line, index, or API description that shows the gap.

## Severity

- high: an operation whose effect cannot be observed or audited; a referenced column that does not exist.
- medium: missing status or lifecycle timestamps the design implicitly needs.
- low: a state or field mentioned in one place only.
