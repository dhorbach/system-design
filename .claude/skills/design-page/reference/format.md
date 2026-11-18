# Page format

## What is shared and what the page owns

| Shared, never copied into a page | Where |
|---|---|
| Document, fonts, analytics | `templates/page.html` |
| Tokens (colours, fonts), reset | `static/assets/base.css` |
| Top bar, depth switch, contents, hero, arrowheads | `templates/guide.html` |
| Styles of the shell and of every component below | `static/assets/guide.css` |
| Depth levels, contents, scroll position, reading time, hover definitions, requirement tags, step-through figures, code colouring | `static/assets/guide.js` |

| The page owns | Where in `pages/<slug>.html` |
|---|---|
| Title, short title, description, what depth 3 holds | `<head>` |
| Component colours; styles of components only this page has | `<style>` in `<head>` |
| The component map | `<template data-slot="map">` |
| The sections | `<section>` elements in `<body>` |
| Hover definitions | `<dl id="glossary" hidden>` after the last section |
| Demos only this page has | one `<script>` at the end |

The build (`scripts/build.py`) puts the page into `templates/guide.html`, then
into `templates/page.html`. A page is a `<head>` fragment followed by a `<body>`
fragment and nothing else.

## Head

```html
<head>
<meta name="layout" content="guide">
<title>Building a distributed job scheduler</title>
<meta name="short-title" content="Distributed job scheduler">
<meta name="description" content="One or two sentences, under 160 characters.">
<meta name="depth-3" content="SQL, example rows, edge cases, tuning and a Go implementation.">
<style>
:root{--api:var(--slate);--store:var(--indigo);--sched:var(--teal)}
.k-api{--k:var(--api)} .k-store{--k:var(--store)} .k-sched{--k:var(--sched)}
</style>
</head>
```

- `<title>` is also the page heading. `short-title` is the name in the top bar.
- `depth-3` is the line under “Full detail” in the depth picker: name what this page holds there. `depth-1` and `depth-2` have defaults (“The whole system and the one idea behind each part.”, “How each part works, with every term explained.”); override them only if the page uses the levels differently.
- No charset, viewport, fonts, stylesheet links or analytics: the templates add them.

### Component colours

Each component gets one shared hue: `--teal`, `--indigo`, `--amber`, `--rose`,
`--violet`, `--green`, `--slate`. Each has a light and a dark value that are
readable on the page surfaces. Name the component once on `:root`, then give it a
`k-` class. Everything shared reads `--k`: section number, contents chip, map
node, diagram box, flow node, idea card.

Use slate for the edge of the system (API, clients). Do not give two components
that sit next to each other in the architecture figure neighbouring hues (teal and
green, indigo and violet). More than seven components means the map is too
detailed: group them.

Other tokens: `--bg`, `--surface`, `--sunken`, `--ink`, `--muted`, `--line`,
`--accent` (controls), `--mark` (highlight, “frozen”, “due”), `--bad` (failure
paths). Never write a hex colour in a page; mix tokens instead:
`color-mix(in srgb,var(--k) 15%,var(--surface))`.

## The map

```html
<template data-slot="map">
  <svg class="minimap" viewBox="0 0 224 150" role="group" aria-label="System map. Select a component to jump to its part of the guide.">
    <path class="wire" marker-end="url(#ah)" d="M102 17H121"/>
    <g class="n k-api" data-node="api" data-go="api" tabindex="0" role="link" aria-label="API service"><rect x="2" y="2" width="100" height="30" rx="7"/><text x="52" y="17">API</text></g>
    …
  </svg>
</template>
```

- Width is always 224. Nodes are 100 × 30 in two columns (`x="2"` and `x="122"`), rows 58 apart (`y="2"`, `60`, `118`, …); set the viewBox height to the last row's `y` + 32. The label is centred on the node (`x` + 50, `y` + 15) and is one or two words.
- `data-node` is the name sections use in `data-nodes`. `data-go` is the id of the section the node jumps to. Two nodes may go to the same section.
- Wires run from the edge of one node to 1 px before the edge of the next, in the direction data flows. Draw only the main flow, five or six wires at most.
- The map is the architecture figure in miniature: same components, same names, same arrows.

## Sections

```html
<section id="scheduler" class="k-sched" data-toc="Scheduler" data-num="3" data-nodes="sched"
  data-more2="why the obvious designs fail, partitions, leases and fencing"
  data-more3="the claim, renew and release writes, failover and tuning">
  <div class="sh"><h2><span class="num">3</span>Scheduler</h2></div>
  <p class="lede">…</p>
  …
</section>
```

| Attribute | Meaning |
|---|---|
| `id` | Lower-case words joined by hyphens. Links and the map point at it. |
| `data-toc` | Name in the contents list and in “Previous / Next”. Short; the `<h2>` may be longer. |
| `data-group` | Starts a group in the contents list with this label: `Framing`, `Components`, `Cross-cutting concerns`, `Wrap-up`. Put it on the first section of the group only. |
| `data-num` | Number of a component section. Also needs the `k-` class and `<span class="num">` in the heading. |
| `data-sub="1"` | A sub-part of the component above it (“Inside the scheduler: the timing wheel”): indented in the contents, no number. |
| `data-nodes` | Map nodes lit while this section is read, separated by spaces. `""` for none. Required. |
| `data-more2`, `data-more3` | What that depth adds. Shown as “Mechanics adds *text*.” and “Full detail adds *text*.”, so write a lower-case list with no full stop. Required when the section has content at that depth, and only then. A section with either gets its own 1-2-3 switch. |
| `data-ref="1"` | Leaves the section out of the reading time. References only. |
| `class="k-…"` | The component the section belongs to. Cross-cutting sections take the colour of the component they lean on most. |

Standard ids, in this order: `overview`, `terms`, `requirements`, `estimates`,
`system`, then the component sections, then cross-cutting sections (`correctness`,
`load`), then `simple-design`, then `reading`. The check insists on `overview`,
`terms`, `requirements`, `estimates`, `system` and `reading`; the others are the
names to use when the page has those sections.

`<h3>` headings get an id on their own (`<section id>-1`, `-2`, …) and appear
under the section in the contents list. To link to a place inside a section, put
your own `id` on the element (`<div data-l="2" id="store-failover">`).

## Depth levels

`data-l="2"` or `data-l="3"` on any element hides it below that depth. Unmarked
content is level 1.

```html
<p>Level 1 text.<span data-l="2"> A sentence added at level 2.</span></p>
<div data-l="2">
  <h3>How it works</h3>
  <p>…</p>
  <p data-l="3">A level-3 aside inside level-2 text.</p>
</div>
<pre data-l="3" data-lang="sql"><code>…</code></pre>
```

- A deeper level may sit inside a shallower one, never the other way round.
- A heading sits at the level of the first thing under it. A heading whose content is all deeper shows with nothing under it.
- Level 1 and level 2 blocks may alternate down a section, so the reading order is right at every depth. Do not sort a section into “all level 1, then all level 2”.
- A `<span data-l>` inside a sentence starts with a space and must leave a correct sentence when hidden.

## Shared components

Use these as they are. Each is styled and, where it does something, driven by the
shared files.

**Lede**: the first paragraph of a section.
```html
<p class="lede">The job store is the single source of truth: every other component can crash and rebuild its state from it.</p>
```

**Table**: always inside `.scroll`, always with a header row. Keep identifiers in `<code>`.
```html
<div class="scroll"><table>
  <tr><th>Option</th><th>Insert</th><th>Fits</th></tr>
  <tr><td>Min-heap by due time</td><td>O(log n)</td><td>Most schedulers</td></tr>
</table></div>
```

**Brief**: explains one term of art where it is first needed. The title is “Brief: term.”; the term gets no hover definition inside its own brief.
```html
<div class="brief"><b>Brief: lease.</b> A lock with an expiry time. The holder must renew it before it expires; if the holder dies, the lease lapses on its own.</div>
```

**Formula**: one step per line, `label: a × b = c unit`. Use `×`, `÷`, `−`, `=` for exact results and `≈` for rounded ones, with spaces around them, and thousands separators. The check recomputes every line.
```html
<div class="formula">every-minute: 2,000 × 1,440 = 2,880,000 runs/day<br>total: 3,510,000 runs/day ÷ 86,400 s ≈ 40 runs/s</div>
```

**Code**: escape `<`, `>` and `&`. `data-lang` is `go`, `sql`, `json` (also for an HTTP request with a JSON body) or `none`. Another language needs a row in `LANGS` in `static/assets/guide.js` and in `check_page.py`. SQL keywords are upper case. Put the role of a statement in a trailing comment (`-- claim`).
```html
<pre data-lang="sql"><code>UPDATE leases SET expires_at = now() + interval '20 seconds'  -- renew
WHERE partition_id = ? AND owner = ? AND epoch = ?;</code></pre>
```

**Figure**: a frame with a caption. The caption says how to read the figure and the one thing it shows; it may carry a `<span data-l="2">`.
```html
<figure><div class="scroll"><svg viewBox="0 0 720 236" style="min-width:560px" role="img" aria-label="Run states: pending to dispatched to running, then succeeded or dead; …">
  …
</svg></div>
<figcaption>…</figcaption></figure>
```

**Diagram parts** (inside any figure SVG):

| Part | Markup |
|---|---|
| Box in a component colour | `<g class="k-store"><rect class="box" x y width height rx="9"/><text class="t" …>Job store</text></g>` |
| Box that links to a section | `<a href="#job-store" class="k-store">…same content…</a>` |
| Box with no component | `<g style="--k:var(--muted)">…</g>`; a failure state uses `--bad` |
| Title and small text | `<text class="t">` (13 px, bold) and `<text class="s">` (11.5 px, muted); centre with `text-anchor="middle"` |
| Arrow | `<path class="wire" marker-end="url(#ah)" d="M150 92H209"/>` with an `s` label beside it |
| Failure arrow | `<path marker-end="url(#ahb)" d="…" stroke="var(--bad)" stroke-width="1.3" fill="none"/>`; dashed (`stroke-dasharray="5 4"`) for a rejection coming back |
| Lifeline in a sequence | `<path d="M90 44V310" stroke="var(--line)" stroke-width="1.2" stroke-dasharray="4 4"/>` |
| A pause or freeze | `<rect … fill="color-mix(in srgb,var(--mark) 55%,var(--surface))" stroke="var(--amber)"/>` |

Give every SVG a `viewBox`, `role="img"` and an `aria-label` that tells the whole
story in words. Set `min-width` so labels stay readable on a phone (the frame
scrolls). Boxes are 140 × 56 in the architecture figure and 120 × 34 to 44
elsewhere; end an arrow 1 px before the box it points at. All text in a diagram
uses the page's terms exactly.

**Step-through figure**: any figure whose parts appear in order. Mark each part `data-s="1"`, `"2"`, … and give one note per step. Play, Next step and Show all are added for you; no script.
```html
<figure class="steps">
  <div class="scroll"><svg …>
    <g data-s="1">…arrow and label of step 1…</g>
    <g data-s="2">…</g>
  </svg></div>
  <figcaption>Read top to bottom as time passing, or press Play to step through it. …</figcaption>
  <ol class="stepnotes">
    <li>What happens in step 1 and why.</li>
    <li>What happens in step 2 and why.</li>
  </ol>
</figure>
```
The notes are plain text, one per step, and are part of the reviewed text.

**Life of one item**: the main flow as numbered stages, in High-level design.
```html
<ol class="life">
  <li><b>Created</b><span>A client calls the API … The API stores a job definition and the first run.</span></li>
</ol>
```

**Key ideas**: cards that link to the section explaining each idea.
```html
<div class="ideas">
  <a href="#scheduler" class="k-sched"><strong>Fencing tokens</strong><span>Writes from a node that lost ownership are rejected</span></a>
</div>
```

**Schema**: one card per table. `<i class="pk">key</i>` marks the key; other `<i>` notes say what is not obvious (copied, never changes, the allowed values).
```html
<figure><div class="schema">
  <div><h4>leases <small>one row per partition</small></h4><ul><li>partition_id <i class="pk">key</i></li><li>owner <i>NULL when released</i></li><li>epoch <i>never goes down</i></li><li>expires_at</li></ul></div>
</div>
<figcaption>…</figcaption></figure>
```
The check compares identifiers in SQL and inline code against these cards.

**Flow**: a left-to-right pipeline in HTML, with an optional dashed group (a transaction, a trust boundary).
```html
<figure><div class="flow">
  <div class="nd k-sched"><b>Scheduler</b><small>fires the run</small></div><span class="ar" aria-hidden="true">→</span>
  <div class="tx k-store"><small>one database transaction</small>
    <div class="nd k-store"><b>runs</b><small>state = dispatched</small></div>
    <div class="nd k-store"><b>outbox</b><small>new event row</small></div></div><span class="ar" aria-hidden="true">→</span>
  <div class="nd k-queue"><b>Queue</b><small>may see it twice</small></div>
</div>
<figcaption>…</figcaption></figure>
```

**Controls and legend** for a page-only demo.
```html
<div class="ctl"><button id="crash">Crash node B</button>
  <span class="key k-sched"><i></i>node A</span><span class="key k-queue"><i></i>node B</span></div>
```

**Requirements and their tags.**
```html
<ul data-reqs="FR">
  <li><strong>Create, cancel and query.</strong><span data-l="2"> One line.</span><span data-l="3"> The precise guarantee (<a href="#api">API service</a>).</span></li>
</ul>
…
<p data-req="FR2 NFR1">A request is accepted only once the job and its first run are committed to the job store.</p>
```
Items of `data-reqs="FR"` become FR1, FR2, … in order (`NFR` likewise), with ids `fr1`, `nfr1`. `data-req` goes on the `<p>`, `<li>` or `.brief` that makes the claim; a tag linking back to the requirement is appended to it.

**Glossary**: hover definitions. The first mention of a term in each block of a section is underlined.
```html
<dl id="glossary" hidden>
  <dt data-match="transactional outbox|\boutbox\b">Transactional outbox</dt><dd>Writing an event row in the same transaction as the state change, published later by a relay.</dd>
  <dt data-match="SKIP LOCKED" data-case data-code>SKIP LOCKED</dt><dd>SQL clause that skips rows locked by others.</dd>
</dl>
```
- `data-match` is a regular expression, case-insensitive unless `data-case` is set. Without it the term itself is matched, with an optional plural `s`. Use `\b` so a short term does not match inside a longer word.
- Order is priority: put a longer term (`Idempotency key`) before a shorter one it contains (`Idempotent`).
- `data-code` lets the term match inside `<code>`.
- Where the word means something else, switch it off on that element: `<p data-noterm="Partition">…daily table partitions…</p>` (several names separated by `|`).
- Core terms defined in Terminology do not go in the glossary. Entries are for terms of art: one sentence each, consistent with the brief that introduces the term.

**References and citation**: the last section.
```html
<section id="reading" data-toc="References" data-nodes="" data-ref="1">
  <div class="sh"><h2>References</h2></div>
  <ul>
    <li>Author, <a href="https://…" target="_blank" rel="noopener">Title</a>: what this guide takes from it.</li>
  </ul>
  <h3>How to cite this page</h3>
  <p class="cite">“Building a ….” System design walkthrough, Month Year. <span id="citeurl"><a href="https://dhorbach.github.io/system-design/<slug>.html" target="_blank" rel="noopener">https://dhorbach.github.io/system-design/<slug>.html</a></span></p>
</section>
```

**Links**: `<a href="#section-id">` for another section, named in lower case as part of the sentence (“see <a href="#correctness">correctness</a>”). External links open in a new tab with `rel="noopener"`.

## A component only this page has

Styles go in the page's `<style>`, under a class no shared file uses. The script
goes at the end of the body and starts from `guide:ready`, which fires once the
contents, tags and definitions are in place:

```html
<script>
document.addEventListener('guide:ready',({detail:{$,$$,still}})=>{
  const box=$('#parts');          // $ = querySelector, $$ = querySelectorAll as an array
  if(!still){ /* animate only when the reader has not asked for reduced motion */ }
});
</script>
```

- Build it from the shared parts first: `<figure>`, `.ctl`, `.key`, `<figcaption>`, tokens, `--k`.
- Draw the starting state as soon as the page loads and put the explanation in the caption, so the figure makes its point before anyone presses a button. A caption the script rewrites starts as real text in the HTML.
- Keep every string the reader sees in the page's terms; the reviewer reads demo strings too.
- A loop that runs on a timer pauses when its element is hidden (`el.offsetParent===null`) and offers Pause.
- Announce changes politely (`aria-live="polite"`) and make every control a `<button>` or a labelled input.
- If a second page wants the component, move its CSS to `guide.css` and its script to `guide.js`, driven by markup, and delete it from the first page.

## Changing something shared

Edit `static/assets/guide.css`, `static/assets/guide.js`, `static/assets/base.css`
or `templates/guide.html`. The change reaches every page on the next build, so
build and look at each existing page afterwards. Add to the unit tests in
`scripts/test_build.py` when the build itself changes.

## The index card

In `pages/index.html`, inside the `<ul class="articles">` of the page's month,
newest first. Add a month block (`<section class="month" aria-labelledby="month-YYYY-MM">`
with its `<h2>`) above the others when the month is new.

```html
<li>
  <a class="article" href="<slug>.html">
    <div class="meta">
      <time datetime="2026-11-17">Nov 17, 2026</time>
      <span class="tag">Distributed systems</span>
    </div>
    <h3>Building a …</h3>
    <p>The description from the page's head, or a little longer.</p>
    <span class="read">Read the guide <span aria-hidden="true">↗</span></span>
  </a>
</li>
```
