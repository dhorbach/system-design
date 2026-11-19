import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SKILL = Path(__file__).resolve().parents[1] / ".claude/skills/design-bench"
GATE_SPEC = importlib.util.spec_from_file_location("check_tests", SKILL / "scripts/check_tests.py")
gate = importlib.util.module_from_spec(GATE_SPEC)
with patch.object(sys, "path", [str(SKILL / "scripts"), *sys.path]):
    GATE_SPEC.loader.exec_module(gate)


class TestStorageGate(unittest.TestCase):
    def test_contract_requires_both_suites_for_each_source(self):
        with tempfile.TemporaryDirectory() as folder:
            bench = Path(folder)
            (bench / "tests").mkdir()
            (bench / "path.go").touch()
            contract = bench / "tests/contract.json"
            spec = {"stores": ["store"], "critical_paths": [{"source": "path.go", "unit": ["TestUnit"]}]}
            contract.write_text(json.dumps(spec))
            with self.assertRaisesRegex(ValueError, "list the integration test cases"):
                gate.contract(bench)
            spec["critical_paths"][0]["integration"] = ["TestStorage"]
            contract.write_text(json.dumps(spec))
            self.assertEqual(gate.contract(bench), ["store"])

    def test_compose_rejects_external_volume_and_mismatched_store(self):
        bench = Path("/tmp/test-bench")
        project = "bench-x-tests-123"
        service = {"image": "postgres:17"}
        base = {"services": {"store": service}}
        config = {"services": {"integration": {}, "store": service},
                  "volumes": {"data": {"name": project + "_data"}}}

        def validate():
            outputs = [json.dumps(config), json.dumps(base)]
            with patch.object(gate.subprocess, "check_output", side_effect=outputs):
                gate.checked_config(bench, ["compose", "test"], ["compose", "base"], project, ["store"])

        validate()
        config["volumes"]["data"]["external"] = True
        with self.assertRaisesRegex(ValueError, "must belong to"):
            validate()
        config["volumes"]["data"]["external"] = False
        config["services"]["store"] = {"image": "postgres:16"}
        with self.assertRaisesRegex(ValueError, "must use the benchmark's image"):
            validate()


@unittest.skipUnless(os.environ.get("RUN_BENCH_INTEGRATION") == "1", "run make test-bench-integration with Docker")
class TestPostgresGate(unittest.TestCase):
    def test_runner_checks_real_postgres_then_blocks_stale_sources(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            bench = root / "bench/storage-fixture"
            shutil.copytree(SKILL / "fixtures/postgres", bench)
            shutil.copy2(SKILL / "templates/run.sh", bench / "run.sh")
            scripts = root / ".claude/skills/design-bench/scripts"
            scripts.mkdir(parents=True)
            for name in ("check_tests.py", "provenance.py"):
                shutil.copy2(SKILL / "scripts" / name, scripts / name)
            git = ["git", "-C", str(root)]
            subprocess.run([*git, "init", "-q"], check=True)
            subprocess.run([*git, "add", "."], check=True)
            subprocess.run([*git, "-c", "user.name=Bench fixture", "-c", "user.email=bench@example.invalid",
                            "commit", "-qm", "Storage test fixture"], check=True)

            def runner(*args):
                return subprocess.run(["bash", "run.sh", *args], cwd=bench, capture_output=True, text=True)

            missing = runner("calibration")
            self.assertNotEqual(missing.returncode, 0)
            self.assertIn("Run ./run.sh test", missing.stderr)
            tested = runner("test")
            self.assertEqual(tested.returncode, 0, tested.stdout + tested.stderr)
            receipt = json.loads((bench / gate.RECEIPT).read_text())
            self.assertEqual(receipt["status"], "passed")
            logs = bench / gate.RECEIPT.parent / receipt["project"]
            self.assertIn("Passed PostgreSQL", (logs / "integration.log").read_text())
            def verify_cleanup(project):
                for command in (["ps", "-aq"], ["volume", "ls", "-q"], ["network", "ls", "-q"]):
                    objects = subprocess.check_output(
                        ["docker", *command, "--filter", f"label=com.docker.compose.project={project}"], text=True,
                    )
                    self.assertFalse(objects.strip(), command)

            verify_cleanup(receipt["project"])

            current = subprocess.run([sys.executable, scripts / "check_tests.py", "require", bench, "storage-fixture"],
                                     capture_output=True, text=True)
            self.assertEqual(current.returncode, 0, current.stderr)
            with (bench / "src/enqueue.sh").open("a") as stream:
                stream.write("\n# Source changed after this test pass.\n")
            stale = runner("calibration")
            self.assertNotEqual(stale.returncode, 0)
            self.assertIn("stale", stale.stderr)
            self.assertFalse((bench / "results/calibration").exists())

            with (bench / "tests/integration.sh").open("a") as stream:
                stream.write("\nexit 37\n")
            failed = runner("test")
            self.assertNotEqual(failed.returncode, 0)
            self.assertIn("integration failed", failed.stderr)
            receipt = json.loads((bench / gate.RECEIPT).read_text())
            self.assertEqual(receipt["status"], "failed")
            verify_cleanup(receipt["project"])
            self.assertIn("stale", runner("calibration").stderr)
