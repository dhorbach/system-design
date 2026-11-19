---
name: design-bench
description: Build a working prototype of a system design page and load-test it against the page's own numbers, in docker compose on this machine, with resource limits, injected delays and failures, and data aged to the design's retention; report a verdict per claim. Use for $design-bench, or when asked to prototype, benchmark, load-test or prove a design page or its numbers, to re-run a bench, or to continue one in progress.
---

Read [Codex runtime](codex-runtime.md), then follow the shared
[design-bench workflow](../../../.claude/skills/design-bench/SKILL.md).
Use the runtime instructions for Codex-specific steps, including the two gates.
Resolve its relative references (`reference/`, `scripts/`, `templates/`) from
the shared file's directory, `.claude/skills/design-bench/`. The scripts and
templates there are plain Python, shell, Go and compose files and run as they are.
