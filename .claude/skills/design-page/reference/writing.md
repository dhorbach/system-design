# Writing the page

Part 1 says what each section holds at each depth. Part 2 goes through the nine
review passes and says how to write so each finds nothing. The rubrics in
`.claude/skills/design-review/rubrics/` decide; where this file and a rubric
differ, the rubric wins.

## The three depths

| Depth | Name | Holds | Does not hold |
|---|---|---|---|
| 1 | Overview | What the part is for and the one idea that makes it work, in plain words. At most one small table or figure per section. About 150 words per section at most. | Code, SQL, column names, formulas, tuning values, edge cases |
| 2 | Mechanics | How it works, step by step. Why the obvious design fails. Every term of art explained where it is first used. The one statement that *is* the mechanism (a guarded write) may appear here. | Full listings, example rows, tuning numbers, rare edge cases |
| 3 | Full detail | Exact SQL and code, example rows, index lists, tuning, rare failure paths, product-specific notes. | Anything a shallower level needs: a step of the main flow, the condition a guarantee rests on, a definition, the fix for a problem raised above |

Three tests, applied to every section:

- **Depth 1 alone** reads as a complete short article about the whole system. Each section gives the answer, not only the problem.
- **Depth 2 alone** (levels 1 and 2 together) explains every mechanism depth 1 named, and no sentence in it needs level 3 to be true.
- **Nothing visible points at something hidden** (“the table below”, “the schema above”), and no heading or list introduction is left with nothing under it.

The same kind of content sits at the same depth in every section: schemas at 2,
example rows and index lists at 3, exact SQL at 3, failure walk-throughs with
numbers at 3.

## Part 1: the sections

### Problem (`overview`)
One lede paragraph, single-level. What the system does, with two concrete
examples in brackets; who uses it; what makes it hard. No sentence about the
guide (“the next section…”, “the features fit in one sentence”).

### Terminology (`terms`)
- **1**: one sentence on why the words matter, then a table of the core terms: Term, Meaning, Example. The core terms are the nouns the design is built on: what a client creates, what the system produces and tracks, and the unit of work. Each row has `id="term-…"`. Each meaning says what the thing is and how it relates to the others.
- **2**: “How they relate”: the cardinalities in plain words, one example counted through with numbers, and where each term lives in the data model.
- **3**: “Neighbouring words”: the verbs and near-synonyms (execute, fire, task, request, event) and the one thing this guide uses each for.

Check each definition against the design before moving on: if the thing can be
retried, it is not “one execution”; if the API can edit it, it is not “fixed”.

### Requirements (`requirements`)
- **1**: the titles only, in bold, as two lists. A title is a short statement a reader understands on its own (“Accepted means it will run.”).
- **2**: one line per requirement with its number, and the “Out of scope” list.
- **3**: the precise guarantee and its exception, with links to the sections that deliver it.

Five to six functional and four to six non-functional requirements. Out of scope
holds variants of the problem the design leaves out (more regions, dependencies
between items), never a design choice.

### Capacity estimates (`estimates`)
- **1**: a lede that says what is being sized and why, then the single number that drives the design. One sentence saying which table is which. A results table of four to six rows.
- **2**: the assumptions table (every input, with its value), one heading and one `.formula` per derived quantity with a sentence on what stands out, then “What the numbers say”: each design decision with the number that forces it.
- **3**: the secondary numbers (background writes, memory, polling).

Size for the peak, not the average, and say where the peak comes from.

### High-level design (`system`)
A lede naming the split into parts and why; the architecture figure with every
box linking to its section; “The life of one *item*” as five or so stages from
creation to final state; “The *N* ideas that make it work” as cards. The cards are
the design's key decisions and each links to the section that explains it.

### Component sections
One per box in the figure, numbered, in the order the item flows through them.
- **1**: a lede: what the component does and the difficulty. Then the idea that answers it, each term explained in the same sentence. Optionally one small table (the endpoints) or one figure.
- **2**: why the obvious designs fail (two bullets); the mechanism in order, with a Brief for each term of art; the schema; the diagram of the race or the flow; the loop or the life cycle as numbered steps.
- **3**: the exact statements with their guards; example rows; failover and rebalancing; tuning; when to skip the mechanism.

A component with a deep sub-topic (a data structure, an algorithm) gets a second
section marked `data-sub="1"`, with the code at depth 3.

### Correctness (`correctness`)
The delivery guarantee and why a stronger one is impossible; how repeats are made
harmless; retries with backoff; what happens to work that keeps failing.

### Behaviour under load (`load`)
Where the peak comes from; the policies that decide who waits (priority,
fairness, catching up after an outage), each named at depth 1; a failure at the
peak walked through with the estimate's numbers; what to measure, each metric
computed from columns the schema has.

### Design at lower scale (`simple-design`)
The simplest design that works below a stated volume, what it drops, and the
number at which it stops being enough. Every component section that could be
skipped at that scale says so in one sentence and links here.

### References (`reading`)
Six to eight sources, each with what the guide takes from it. Then the citation.

## Part 2: writing for each review pass

### framing
- Start every section by saying what it works out and why it matters; results come second. A section never opens with a number.
- Delete any sentence that only announces structure, restates the heading or promises content.
- Two tables in a row, or a table followed by formulas, get one sentence saying how they relate (inputs and results).

### terminology
- Define the core terms in Terminology at depth 1, before Requirements, and never redefine them.
- After the draft, search the page for each core term and each near-synonym (execution, invocation, task, instance, request, event, message). Every hit either uses the term as defined or is replaced. A product's own noun (ECS task, Kafka partition) is fine where it names that product's object; say so under “Neighbouring words”.
- The usual slips: the thing a client creates named where its instance is meant (“the job is retried” when a run is), an instance named where a single try is meant, and the term used for a system process.
- Diagram labels, table headings, captions, glossary entries, step notes and demo strings count. Identifiers in code may differ if the page says how they map.

### requirements
- State what a client can observe: “a run may execute more than once, but the receiver can always recognise a repeat”, not “every run carries an idempotency key”. No data structure, protocol, table, queue, cache, polling interval, product or SQL in a requirement at any depth. The requirement may link to the section that has the mechanism.
- Give every non-functional requirement a number or a bound, and the same number appears in the estimates and in the section that delivers it.
- Every requirement is delivered somewhere and tagged there with `data-req`; every component section delivers at least one. A mechanism no requirement needs is either cut or shows which requirement is missing.
- The check lists mechanism words it finds in requirements and requirements with no tag.

### data-model
- Every operation the API or the text describes leaves a record: a status, a timestamp, a reason. Cancelling does not delete. Ask of each operation: can the system say afterwards that it happened, when, and who did it?
- Long-lived tables have `created_at` and `updated_at`; anything with a life cycle has a status column; anything the page measures (lag, duration, failures) has the columns to compute it.
- Every column named in an index, a query, an example row or the prose is in the schema card of its table. The check lists identifiers it cannot find there.
- Every state in the diagram is in the text and the reverse; every transition names who writes it; the final states are stated.
- Every request field maps to a column or is said to be derived; every column a client sets is reachable through the API.

### assumptions
- Do not model the core entity as one concrete case. If a “job” could be an HTTP call or a container, give it a kind and a kind-specific spec, say which parts of the design do not depend on the kind, and say what a second kind changes.
- Every property the estimates or a mechanism rely on (how long work takes, one region, who the clients are) is in the assumptions table or in Out of scope.

### arithmetic
- Every derived number is produced by a `.formula` line from values in the assumptions table. Compute them with a script and paste the results; the check recomputes each line.
- One quantity, one value, everywhere: run `check_page.py … --numbers` and look at each number that appears in more than one section. Say “about” where you round, and round the same way each time.
- Two thresholds that look contradictory (a limit of a few thousand per second and a peak of 30,000 in one second) need the sentence that reconciles them.
- Keep units on every number, with a space (`2 s`, `100 ms`, `3.5 GB`), and do not mix per-second and per-minute rates for one quantity.

### correctness
- Walk each failure path in the ledger to its end in the prose: who notices, what state the item ends in, whether anything is lost or repeated. A path that “is retried” needs the limit that stops it.
- Every write two actors could make at once shows its guard in the `WHERE` clause or a unique constraint, in the statement on the page. A check made earlier in memory or in a previous read is not a guard, and the text says what the writer does when zero rows match.
- When an operation adds a condition (cancelled, paused, expired), every path that continues work checks it: retries, creation of the next item, background resets.

### claims
- For each claim about a named product, protocol or runtime, state the version, the setting or “by default” that makes it true (“Postgres and MySQL 8 both support it”, “at the default `REPEATABLE READ` level”).
- Verify the ones the design relies on against the product's documentation while writing, and name vendor-specific syntax as such with the alternative.
- Prefer “for example Kafka, SQS or RabbitMQ” to a single product unless the design depends on one product's behaviour.

### simplicity
- Follow the three depths and the three tests at the top of this file. The check enforces the structure; `levels.py --level 1` and `--level 2` show you what a reader at that depth sees.
- A term of art used at depth 1 is explained in that same depth-1 sentence. A hover definition is enough only for a passing mention.
- Write `data-more2` and `data-more3` last, from the headings, figures and listings that level really adds: everything listed exists, and nothing at that level is left out.

## Voice

- Plain declarative sentences in the present tense, addressed to an engineer who has not built this system. British spelling (behaviour, recognise).
- Say the thing, then the reason: “Commit before calling anything, so row locks last milliseconds.”
- Concrete over abstract: a time (09:00:00), a count (30,000 runs), an id (`r_5002`), and the same examples reused across sections.
- Bold the lead-in of a list item or the term being introduced; nothing else. Italics for a contrast (“deciding when” against “doing the work”).
- Curly quotes (“ ” ’), no em dashes (use a comma, a colon or brackets), an en dash for ranges (10–30 s), `×` and `÷` in formulas.
- No sentence that only links two others, and no summary that repeats the section.
