#!/usr/bin/env python3
"""Run a bench's unit and storage integration suites or check their pass record."""
import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from provenance import git, source_files


RECEIPT = Path("test-results/latest.json")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def contract(bench):
    spec = json.loads((bench / "tests/contract.json").read_text())
    stores, paths = spec["stores"], spec["critical_paths"]
    require(isinstance(stores, list) and all(isinstance(name, str) and name for name in stores)
            and len(set(stores)) == len(stores), "List each real store service once in tests/contract.json.")
    require(stores or spec.get("storage_free_reason"), "List the storage services or explain the storage-free design.")
    require(isinstance(paths, list) and paths, "List the bench's critical paths and their test cases.")
    for path in paths:
        source = (bench / path["source"]).resolve()
        require(source.is_relative_to(bench) and source.is_file(), f"Missing bench source {path['source']}")
        for suite in ("unit", "integration"):
            cases = path.get(suite, [])
            require(isinstance(cases, list) and cases and all(isinstance(case, str) and case for case in cases),
                    f"{path['source']}: list the {suite} test cases.")
    return stores


def checked_config(bench, compose, base, project, stores):
    def config(command):
        return json.loads(subprocess.check_output([*command, "config", "--format", "json"], cwd=bench))

    model = config(compose)
    base_services = config(base)["services"]
    services = model["services"]
    require("integration" in services, "Define the integration test runner service.")
    for name in stores:
        require(name != "integration" and name in services and name in base_services,
                f"Storage service {name} must exist in both Compose files.")
        test, measured = services[name], base_services[name]
        same_storage = (test.get("image") or test.get("build")) and all(
            test.get(key) == measured.get(key) for key in ("image", "build", "command", "entrypoint")
        )
        require(same_storage, f"Storage service {name} must use the benchmark's image/build and startup command.")
    for kind in ("volumes", "networks"):
        for name, definition in model.get(kind, {}).items():
            require(not definition.get("external") and definition.get("name", "").startswith(f"{project}_"),
                    f"Test {kind} entry {name} must belong to {project}.")
            require(not definition.get("driver_opts"), f"Test {kind} entry {name} uses external driver settings.")
    for name, service in services.items():
        overrides = ("ports", "container_name", "network_mode", "pid", "ipc", "volumes_from", "devices",
                     "privileged", "use_api_socket")
        require(not any(service.get(key) for key in overrides), f"Test service {name} overrides Compose isolation.")
        for mount in service.get("volumes", []):
            if mount["type"] == "volume":
                require(not mount.get("source") or mount["source"] in model.get("volumes", {}),
                        f"Test service {name} uses an undeclared volume.")
            else:
                source = Path(mount.get("source", "")).resolve()
                require(mount["type"] == "tmpfs" or (mount["type"] == "bind" and mount.get("read_only")
                        and source.is_relative_to(bench) and not source.is_socket()),
                        f"Test service {name} must use project volumes or read-only inputs in the bench.")


def run_logged(command, bench, log):
    print(f"Running {log.stem} tests or setup. Log in {log.relative_to(bench)}", flush=True)
    with log.open("w") as stream:
        result = subprocess.run(command, cwd=bench, stdout=stream, stderr=subprocess.STDOUT)
    if result.returncode:
        print(log.read_text(errors="replace")[-6000:], file=sys.stderr)
        raise ValueError(f"{log.stem} failed with exit status {result.returncode}.")


def run_tests(bench, logs, stores, project):
    base = ["docker", "compose", "--project-directory", str(bench), "--env-file", "bench.env",
            "--project-name", project, "-f", "compose.yaml"]
    compose = [*base[:-1], "tests/compose.yaml"]
    run_logged(["bash", "tests/unit.sh"], bench, logs / "unit.log")
    checked_config(bench, compose, base, project, stores)
    try:
        if stores:
            run_logged([*compose, "up", "--build", "--wait", *stores], bench, logs / "storage.log")
        run_logged([*compose, "run", "--build", "--rm", "-T", "integration"], bench, logs / "integration.log")
    finally:
        run_logged([*compose, "down", "--volumes", "--remove-orphans"], bench, logs / "cleanup.log")


def source_hashes(bench, slug):
    root = Path(git(bench, "rev-parse", "--show-toplevel").strip())
    files, _ = source_files(root, bench.relative_to(root), Path("pages") / f"{slug}.html")
    return {name: entry["sha256"] for name, entry in files.items()}


def save(path, record):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(record, indent=2) + "\n")
    temporary.replace(path)


def test(bench, slug):
    receipt = bench / RECEIPT
    project = f"bench-{slug}-tests-{uuid4().hex[:10]}"
    logs = receipt.parent / project
    logs.mkdir(parents=True)
    record = {"project": project, "started": datetime.now(timezone.utc).isoformat(), "status": "running"}
    save(receipt, record)
    try:
        hashes = source_hashes(bench, slug)
        stores = contract(bench)
        run_tests(bench, logs, stores, project)
        require(source_hashes(bench, slug) == hashes, "Bench sources changed during the test pass. Run the suites again.")
    except BaseException:
        save(receipt, {**record, "status": "failed"})
        raise
    save(receipt, {**record, "status": "passed", "stores": stores, "files": hashes})
    print(f"Unit and integration tests passed. Pass record saved in {RECEIPT}.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("run", "require"))
    parser.add_argument("bench", type=Path)
    parser.add_argument("slug")
    args = parser.parse_args()
    bench = args.bench.resolve()
    try:
        if args.action == "run":
            test(bench, args.slug)
        else:
            receipt = bench / RECEIPT
            require(receipt.is_file(), "Run ./run.sh test before calibration or load testing.")
            record = json.loads(receipt.read_text())
            require(record["status"] == "passed" and record["files"] == source_hashes(bench, args.slug),
                    "The test pass is missing or stale. Run ./run.sh test again.")
    except (ValueError, OSError, KeyError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
