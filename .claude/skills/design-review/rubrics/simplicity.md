# Pass: simplicity

Every section is readable at every depth: level 1 gives the idea simply, level 2 explains how it works, level 3 adds exact detail, and the section's markup is set up to match.

Applies to pages with depth levels (`data-l="2"`, `data-l="3"`, `data-more2`, `data-more3`). On a page without levels, apply checks 1 and 2 to each section's opening paragraph and skip the rest.

## Setup

Run the helper from this skill's `scripts/` directory before judging:

- `python3 levels.py SOURCE.html` prints, per section, the words, tables, figures, code blocks and headings at each level, the `data-more2` and `data-more3` descriptions, and structural flags.
- `python3 levels.py SOURCE.html --level 1` (then `--level 2`) prints the text a reader sees at that depth. Text is grouped by level inside each section, so check the source when reading order matters.

Take the meaning of each level from the page itself (the depth picker usually states it). If the page gives none, use: level 1 is what the part is for and the one idea behind it; level 2 is how it works, with every term explained; level 3 is exact detail such as code, SQL, example data, edge cases and tuning.

## Check

Go through every section and every level. Do not sample.

1. **Level 1 is complete on its own.** Each section has level-1 text that says what the part does and the one idea that makes it work. Flag a section that is empty or headings-only at level 1, or whose level 1 states the problem and leaves the answer to level 2. A list of self-explanatory statements (requirement titles) counts as content.
2. **Level 1 is simple.** Plain words and one idea per section. No code, SQL, column names, formulas, tuning values or edge cases, and at most one figure or small table. A term of art is explained in the level-1 text where it is used; a hover-only definition is enough for a passing mention, not for a term the section's idea rests on. More than about 150 words at level 1, or level 1 holding over half of a section that has deeper levels, usually means detail that belongs lower.
3. **Level 1 reads as a whole.** Read the `--level 1` output top to bottom. It should describe the whole system with no missing step, and nothing in it may point at content hidden at that level ("the table below", "the schema above").
4. **Level 2 explains what level 1 names.** Every mechanism named at level 1 is explained at level 2, and each term of art is explained at first use (inline, in a brief box or in a glossary). Flag a mechanism explained only at level 3 or nowhere. Flag level-3 material sitting at level 2: full listings, example rows, tuning numbers, rare edge cases. A single short statement that *is* the mechanism (one guarded write) may stay at level 2.
5. **Level 3 only adds detail.** Flag level-3 content that a shallower level depends on: a step in the main flow, the condition a guarantee needs, the definition of a term used at level 2, the fix for a problem raised at level 2.
6. **Each level stands without the next.** With deeper content hidden, the text still reads correctly: no heading with nothing under it, no list introduction whose list is hidden, no sentence whose visible part is wrong without its hidden continuation. A shallower level may leave things out but must not say something the deeper text contradicts.
7. **The setup matches the content.** Use the helper's summary and flags:
   - a section with level-2 or level-3 content declares it, and a declaration has content behind it (`undeclared-level`, `declared-empty`);
   - each `data-more` description names what that level actually adds: every item it lists exists at that level, and no heading, figure or listing at that level is missing from it;
   - no lower level is nested inside a higher one (`inverted-nesting`), and each heading sits at the level of its content;
   - the same kind of content (schema, SQL, example rows, failure cases, tuning) sits at the same level in every section. Flag the outlier.

   A section that is single-level on purpose (Problem, High-level design, References) is fine unless it carries detail that belongs lower.

## Evidence

Quote the level-1 or level-2 sentence that shows the problem, and say in `why` which level it is visible at. For a setup finding, quote the `data-more` description or the heading involved. For something missing at a level, quote the nearest text at that level that shows the gap.

## Severity

- high: a section is empty, misleading or contradicted by deeper text at some level; a level-2 reader lacks a step or term the design depends on.
- medium: level 1 carries implementation detail or rests on an unexplained term; level 1 gives the problem without the idea; a mechanism named at level 1 is not explained at level 2; needed content exists only at level 3; a structural flag; a description that does not match what its level adds.
- low: level 1 slightly overloaded; a description missing one item; the same kind of content placed at different levels in different sections.
