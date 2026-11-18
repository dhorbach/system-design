---
name: design-page
description: Write a new system design guide page for this site in the format of pages/distributed-job-scheduler.html (shared guide layout, three depth levels, component map, requirement tags, glossary), built from a design ledger and checked so that it passes the design-review skill. Use when the user asks to add, write, draft or build a system design page or guide (for example "add a system design for a URL shortener", "write the rate limiter page", "new SD page"), or to turn an existing draft or notes into a guide page.
---

# Design page

Writes one system design guide as `pages/<slug>.html`. The page holds content only.
The look and the behaviour come from the shared layout, so a new page adds no UI
code unless it has a demo no other page has.

`pages/distributed-job-scheduler.html` is the worked example: open it whenever
this skill names a pattern and you want to see it filled in.

Files in this skill:

- `templates/skeleton.html`: the starter page. Every standard section, with a `TODO` where content goes.
- `reference/format.md`: what the page owns and what is shared, every attribute, and the markup of each shared component. Read it before writing markup.
- `reference/writing.md`: what each section must say at each depth, and how to write so each review pass finds nothing. Read it before writing prose.
- `scripts/check_page.py`: the structural check. Recomputes the formulas, follows every link and requirement tag, and checks the depth levels.

The acceptance criteria are the rubrics in `.claude/skills/design-review/rubrics/`.
They are the source of truth; `reference/writing.md` only says how to meet them.

## Workflow

1. **Scope.** Settle the system, the scale it is sized for and anything the user wants in or out. Ask only what you cannot default; state the defaults you chose. Pick the slug (`url-shortener`), the title (`Building a URL shortener`) and the short title (`URL shortener`).

2. **Read.** `reference/format.md`, `reference/writing.md`, and all nine rubrics. Skim the scheduler page at depth 1 (`python3 .claude/skills/design-review/scripts/levels.py pages/distributed-job-scheduler.html --level 1`) to fix the voice and the amount of text per section in your head.

3. **Write the ledger before any prose.** A scratchpad file, `<slug>-ledger.md`, with the facts the page will state. The reviewer builds the same inventory and checks the page against it, so every disagreement between two parts of the page is a finding. Sections of the ledger:
   - **Terms**: the three or so core nouns, one definition each, how they relate, and the words you will not use for them.
   - **Requirements**: FR1…, NFR1…, each as a guarantee a client can observe, with its number, and the section that will deliver it. Then the out-of-scope list.
   - **Numbers**: assumptions (inputs) and every derived number with its formula. Compute them with a script, not in your head. Mark the one number that drives the design.
   - **Components**: name, colour, section id, the one idea behind each, which requirements it delivers.
   - **Data model**: every table and column, every index and who reads it, every state and transition and who writes it.
   - **API**: endpoints, body fields and the column each maps to.
   - **Failure paths**: for each (a crash between two writes, a stale owner, a dead worker, a cancel mid-flight, a manual retry, a failover at the peak): who notices, the end state, what is lost or repeated, and the guard that sits in the write.
   - **Claims**: every statement about a named product, protocol or runtime, with the version or setting it holds for. Look up any you are not sure of.

   Change the ledger first whenever the design changes, then the page. Never state a number, column, state or guarantee that is not in it.

4. **Start the page.** Copy `templates/skeleton.html` to `pages/<slug>.html`. Set the head, the component colours and the map. Add or remove component sections to match the ledger; keep the standard section ids and their order.

5. **Write depth 1 for the whole page first**, top to bottom, then build and read it (`levels.py … --level 1`). It must work as a complete short article: every section says what the part does and the one idea that makes it work, in plain words. Only then add depth 2 to every section (how it works, every term explained), then depth 3 (SQL, code, example rows, edge cases, tuning). Writing level by level is what keeps a level from depending on a deeper one.

6. **Draw.** The architecture figure, a state diagram for anything with a lifecycle, a sequence diagram for each race. Use the shared components in `reference/format.md`. A step-through figure needs no script. Build a page-only demo only where interaction teaches something a static figure cannot.

7. **Wire it up**, last, from what the page now actually contains:
   - `data-req` on the sentence that delivers each requirement;
   - the glossary entries for the terms of art;
   - `data-more2` and `data-more3` for every section, listing what that level really adds;
   - `data-nodes` for every section.

8. **Check.** Repeat until clean:
   ```sh
   python3 scripts/build.py
   python3 .claude/skills/design-page/scripts/check_page.py pages/<slug>.html
   python3 .claude/skills/design-page/scripts/check_page.py pages/<slug>.html --numbers
   python3 .claude/skills/design-review/scripts/levels.py pages/<slug>.html --level 2
   ```
   Fix every error. Read every warning and either fix it or be able to say why it stands. In the `--numbers` listing, each quantity must have one value everywhere. Read the level-1 and level-2 text once more as a reader who cannot see the deeper levels. Then open the built page (`python3 -m http.server 8000 --directory _site`) at a wide and a phone width, in light and dark, at each depth, and try every control.

9. **Pre-review.** Run the judge the way `.claude/skills/design-review/SKILL.md` does in review steps 2 to 4 (fresh-context judge with the rubrics, quote check, refutation), without publishing a report. Give the judge only the page path, the rubrics directory and `levels.py`: not the ledger, not your reasoning. Fix every surviving high and medium finding in the ledger and then the page, rerun step 8, and re-judge once with only the rubrics of the passes you touched. Stop there; do not loop. List what remains.

10. **List it.** Add the page's card to `pages/index.html` (format in `reference/format.md`), newest first, under its month. Run the unit tests (`python3 -m unittest discover -s scripts -p 'test_*.py'`) and the build.

11. **Report**: the files, the defaults you chose in step 1, the check result, what the pre-review found and what you did about each finding, and any warning or finding you left standing with the reason. Do not commit unless asked. The user can then run the design-review skill for the review they decide on.

## Rules that are easy to break

- **No UI in the page.** No fonts, no layout CSS, no copy of a shared component, no restyling of a shared selector. If a shared component needs to change, change `static/assets/guide.css`, `static/assets/guide.js` or `templates/guide.html`, and check every existing page still renders the same.
- **Promote, do not copy.** If the new page needs a component that so far lives only inside another page, move it into the shared files and delete it from that page.
- **One meaning per word.** Once Terminology defines a noun, every sentence, label, caption, tooltip and demo string uses it that way.
- **Requirements say what, never how.** A product name, a data structure or a protocol in a requirement is a finding at any depth.
- **Every number is derived on the page** from the assumptions table, and reused with the same value.
- **Every write that can race shows its guard in the statement itself**, and every failure path ends in a named state.
- **Nothing visible at a depth may point at, or depend on, something hidden at that depth.**
