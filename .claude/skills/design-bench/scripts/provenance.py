#!/usr/bin/env python3
"""Record the repository revision and exact contents of a design bench's source inputs."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path


def git(cwd, *args):
    return subprocess.check_output(["git", "-C", cwd, *args], text=True)


def source_files(root, bench, page):
    paths = (str(bench), str(page), ".claude/skills/design-bench", ".agents/skills/design-bench")
    tracked = set(git(root, "ls-files", "-z", "--cached", "--", *paths).split("\0"))
    untracked = set(git(root, "ls-files", "-z", "--others", "--exclude-standard", "--", *paths).split("\0"))
    files = {}
    for relative in sorted((tracked | untracked) - {""}):
        path = Path(relative)
        if path.is_relative_to(bench):
            parts = path.relative_to(bench).parts
            if parts[0] in {"results", "analytics", "verdicts.json"} or parts[0].startswith("results-"):
                continue
        input_file = root / path
        digest = None
        if input_file.is_file():
            with input_file.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
        files[relative] = {"sha256": digest, "tracked": relative in tracked}
    dirty = set(git(root, "diff", "--name-only", "-z", "HEAD", "--", *paths).split("\0"))
    return files, bool((dirty | untracked) & files.keys())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bench", type=Path)
    parser.add_argument("slug")
    parser.add_argument("output", type=Path)
    parser.add_argument("--capture", choices=("0", "1"), required=True)
    parser.add_argument("--sampler-cpus", required=True)
    args = parser.parse_args()
    root = Path(git(args.bench, "rev-parse", "--show-toplevel").strip())
    bench = args.bench.resolve().relative_to(root)
    revision = git(root, "rev-parse", "HEAD").strip()
    files, dirty = source_files(root, bench, Path("pages") / f"{args.slug}.html")
    doc = {"commit": revision, "dirty_sources": dirty, "raw_capture": args.capture == "1",
           "sampler_cpus_requested": args.sampler_cpus, "files": files}
    args.output.write_text(json.dumps(doc, indent=2) + "\n")


if __name__ == "__main__":
    main()
