# Running design-bench in Codex

Use the shared workflow for the bench and the steps below for Codex's Docker
execution, gates and report.

- **Bash / Read / Write / Edit**: use the available shell and file tools, under
  the repository's instructions and the current permissions.
- **Docker.** Stage 1 starts with the read-only `python3 .claude/skills/design-bench/scripts/preflight.py`.
  Preflight calls `docker info` and `docker ps`. If it reports unusable Docker
  while Docker is installed, check `docker info` for the underlying error. On
  a sandbox socket denial, retry preflight using the runtime's approved
  execution path (in Codex shell tools, `sandbox_permissions: "require_escalated"`
  when available). Use that path for later Docker commands when needed.
  `run.sh` also needs loopback access to the bench ports. Image pulls and builds
  may need network access. Reuse access already granted in this session.
  Scope every command to the bench's own compose project (`bench-<slug>`); never
  stop, restart or reconfigure another project's containers.
- **Long runs.** Start `./run.sh <scenario> <unique-run-id>` as one foreground
  command. For a shell tool that yields a session ID (`exec_command`), retain
  it and wait for the exit status via `write_stdin` with empty input. Record the
  active run ID and session ID in the plan's results log if the run spans turns.
  After exit 0, check that the new `metrics.json` parses and has the expected
  metrics. On failure, diagnose from the process output and run directory before
  retrying with a new ID. If resuming with no session handle, confirm whether the
  original process is still running before retrying. Run one scenario at a time.
- **Plan and results gates.** Use chat backed by `bench/<slug>/plan.md` as the
  approval record. Use the same question and section criteria as the shared
  workflow. Link the plan and, at the results gate, the report.
  1. Before asking, save the current stage and add Stage, Item ID, Revision
     and Status columns to the plan's Decisions table. Save the three options,
     their costs and the recommendation for each question. Mark new items pending.
  2. Ask for choices and section approvals in chat or a question tool. An
     explicit approval of the entire current gate covers every item as shown
     and selects the recommendations for its questions if those defaults were
     stated when requesting approval. Require an explicit user response.
  3. Record answers against the reviewed revisions before acting. On resume,
     read the plan and its decision record first. Ask about pending items only.
     For a changed section or question, increment that item's revision and
     return it to pending. Carry forward decisions for unchanged items. Wait to
     start dependent work until all current items are decided.
  4. When the user explicitly skips the gates, take the recommendations and
     record those choices and section approvals as user-authorized defaults.
     Still write the plan and generate the report. A generic request to
     continue resumes the current stage.
  Replace the template's board and report URL placeholders with references to
  the Decisions table and local report. If switching from a Claude run with
  inaccessible board decisions, ask for any decisions the plan lacks.
- **The report.** Build a local HTML report and link the file:
  ```sh
  python3 .claude/skills/design-bench/scripts/report.py bench/<slug>/verdicts.json bench/<slug>/notes.json drafts/<slug>/bench-report.html --standalone
  ```
  Say that it is a local file. Do not claim it is published and do not upload it
  to any service. Also print the verdict table (`verdict.py judge` prints it as
  Markdown) in chat, so the gate can be answered without opening the page. Skip
  `bench-report.url`.
- **Agent** (a fresh-context run, if a shared reference asks for one): use an
  available subagent tool and pass it the repository root and the exact file
  paths. If delegation is unavailable, do the pass yourself and say it was not
  independent.
- **`design-page` and `design-review`.** This workflow uses two files of theirs
  as plain files: `.claude/skills/design-review/scripts/levels.py` (prints a
  page's text) and the page's ledger `drafts/<slug>/ledger.md`. Stage 5 edits
  the ledger and the page directly, by the rules quoted in the shared workflow;
  it does not need those skills to be installed in Codex.

An approved plan authorizes building and running the bench it describes. It does
not authorize installing software, using more disk or time than the plan states,
committing, or touching anything outside `bench/<slug>/`, `drafts/<slug>/`, the
page and its ledger.
