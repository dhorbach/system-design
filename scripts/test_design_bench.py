import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL = Path(__file__).resolve().parents[1] / ".claude/skills/design-bench"
SAMPLER_SPEC = importlib.util.spec_from_file_location("cgsample", SKILL / "scripts/cgsample.py")
cgsample = importlib.util.module_from_spec(SAMPLER_SPEC)
SAMPLER_SPEC.loader.exec_module(cgsample)


class CalibrationTests(unittest.TestCase):
    def test_only_expected_and_correctly_limited_replicas_pass(self):
        services = {
            "sink": {},
            "api": {"cpus": 0.5, "mem_limit": "67108864", "cpuset": "2-3", "deploy": {"replicas": 2}},
        }
        replica = {"service": "api", "cpu_limit": 0.5, "mem_limit_bytes": 67108864, "cpuset": "2,3"}
        self.assertTrue(cgsample.limit_problems({"sink": {}}, {}))
        self.assertTrue(cgsample.limit_problems(services, {"sink-1": {"service": "sink"}}))
        self.assertTrue(cgsample.limit_problems(services, {"api-1": replica}))
        self.assertEqual(cgsample.limit_problems(services, {"api-1": replica, "api-2": replica}), [])
        for key, wrong_value in {"cpu_limit": 1, "mem_limit_bytes": None, "cpuset": "4-5"}.items():
            with self.subTest(limit=key):
                wrong_replica = {**replica, key: wrong_value}
                self.assertTrue(cgsample.limit_problems(services, {"api-1": replica, "api-2": wrong_replica}))


class VerdictTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        template = json.loads((SKILL / "templates/claims.json").read_text())
        self.claim = {"id": "C", "scenario": "steady", "metric": "p99", "op": "<=", "target": 10}
        self.spec = {"calibration": [c for c in template["calibration"] if c["id"] == "K7"],
                     "gates": template["gates"], "min_runs": 1, "claims": [self.claim]}

    def record(self, scenario, metrics, name="r1"):
        output = self.root / "results" / scenario / name
        output.mkdir(parents=True, exist_ok=True)
        metrics_path = output / "metrics.json"
        metrics_path.write_text(json.dumps(metrics))
        return metrics_path

    def judge(self):
        spec = self.root / "claims.json"
        verdicts = self.root / "verdicts.json"
        spec.write_text(json.dumps(self.spec))
        subprocess.run(
            [sys.executable, SKILL / "scripts/verdict.py", "judge", spec, self.root / "results",
             "--out", verdicts], capture_output=True, text=True, check=True,
        )
        return json.loads(verdicts.read_text())["claims"][0]

    def test_k6_run_requires_drop_count_and_planned_delivery(self):
        self.record("calibration", {"calib.limit_problems": 0})
        run = {"p99": 5, "res.host.cpu_busy_max": 0.1, "res.host.psi_cpu": 0.01}
        self.record("steady", run)
        verdict = self.judge()
        self.assertEqual(verdict["verdict"], "inconclusive")
        self.assertTrue(any("G1" in reason for reason in verdict["runs"][0]["why_invalid"]))
        self.assertTrue(any("G2" in reason for reason in verdict["runs"][0]["why_invalid"]))
        run.update({"load.dropped_iterations.count": 0, "load.iterations.count": 100, "load.offered": 100})
        self.record("steady", run)
        self.assertEqual(self.judge()["verdict"], "pass")
        self.record("steady", {**run, "load.iterations.count": 98})
        self.assertEqual(self.judge()["verdict"], "inconclusive")
        self.record("steady", {**run, "load.dropped_iterations.count": 1})
        self.assertEqual(self.judge()["verdict"], "inconclusive")

    def test_skipping_run_gates_does_not_skip_calibration(self):
        self.claim["no_gates"] = True
        self.record("steady", {"p99": 5})
        self.assertEqual(self.judge()["verdict"], "inconclusive")
        self.record("calibration", {"calib.limit_problems": 1})
        self.assertEqual(self.judge()["verdict"], "inconclusive")
        self.claim["calibration_exemption"] = "Independent static measurement."
        self.assertIn("Independent static measurement", self.judge()["note"])
        del self.claim["calibration_exemption"]
        self.record("calibration", {"calib.limit_problems": 0})
        self.assertEqual(self.judge()["verdict"], "pass")

    def test_latest_calibration_is_chosen_by_completion_time(self):
        self.claim["no_gates"] = True
        self.record("steady", {"p99": 5})
        older = self.record("calibration", {"calib.limit_problems": 0}, "z-first")
        newer = self.record("calibration", {"calib.limit_problems": 1}, "a-second")
        os.utime(older, (100, 100))
        os.utime(newer, (200, 200))
        self.assertEqual(self.judge()["verdict"], "inconclusive")

    def test_timed_control_needs_valid_load(self):
        self.claim["no_gates"] = True
        self.spec["controls"] = [
            {"id": "N", "scenario": "control", "guards": ["C"], "metric": "duplicates", "op": ">", "target": 0},
        ]
        self.record("calibration", {"calib.limit_problems": 0})
        self.record("steady", {"p99": 5})
        self.record("control", {"duplicates": 1})
        self.assertEqual(self.judge()["verdict"], "inconclusive")
        self.record("control", {"duplicates": 1, "load.dropped_iterations.count": 0,
                                "load.iterations.count": 100, "load.offered": 100,
                                "res.host.cpu_busy_max": 0.1, "res.host.psi_cpu": 0.01})
        self.assertEqual(self.judge()["verdict"], "pass")

    def test_k6_zero_drop_defaults_are_per_measured_window(self):
        summary = self.root / "k6.json"
        summary.write_text(json.dumps({"metrics": {
            "step_0050.iterations": {"values": {"count": 100}},
            "step_0100.iterations": {"values": {"count": 197}},
            "step_0100.dropped_iterations": {"values": {"count": 3}},
        }}))
        result = subprocess.run([sys.executable, SKILL / "scripts/verdict.py", "flatten", f"load={summary}"],
                                check=True, capture_output=True, text=True)
        metrics = json.loads(result.stdout)
        self.assertEqual(metrics["load.step_0050.dropped_iterations.count"], 0)
        self.assertEqual(metrics["load.step_0100.dropped_iterations.count"], 3)
        self.assertNotIn("load.dropped_iterations.count", metrics)
