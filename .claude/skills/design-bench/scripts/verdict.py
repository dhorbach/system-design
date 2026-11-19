#!/usr/bin/env python3
"""Turn measurements into verdicts, by rule and not by eye.

    verdict.py flatten load=k6.json sink=sink.json res=resources.json [--set name=value ...] > metrics.json
    verdict.py judge claims.json results/ [--out verdicts.json]

`flatten` merges the outputs of one run into one flat map of named numbers
(`load.http_req_duration.p99`, `sink.delay.p99_ms`, `res.api-1.throttled_share`).

`judge` reads the claims (the design's promises, each with the check that would
disprove it) and every `results/<scenario>/<run>/metrics.json`, and decides:

- a run counts only if every gate holds for it (the bench itself was sound);
- a claim passes only if every valid run passes every one of its checks,
  and there are at least `min_runs` valid runs;
- runs that disagree make the claim inconclusive, never passed;
- a claim guarded by a control is inconclusive until that control has shown
  the check can fail (a check that cannot fail proves nothing);
- measured and scaled claims require passing calibration unless they provide
  a calibration_exemption reason for a measurement independent of the bench;
- a claim marked untestable is reported as such, with its reason.

Exit code: 0 when no claim failed, 1 when one did, 2 on bad input.
"""
import json
import os
import re
import statistics
import sys
import time

OPS = {"<=": lambda a, b: a <= b, "<": lambda a, b: a < b, ">=": lambda a, b: a >= b,
       ">": lambda a, b: a > b, "==": lambda a, b: a == b, "!=": lambda a, b: a != b}
LABELS = {  # (verdict, evidence) -> what the report says
    ("pass", "measured"): "Verified", ("pass", "scaled"): "Verified at bench scale",
    ("pass", "extrapolated"): "Extrapolated: holds", ("pass", "analytic"): "Arithmetic holds",
    ("fail", "measured"): "Failed", ("fail", "scaled"): "Failed at bench scale",
    ("fail", "extrapolated"): "Extrapolated: does not hold", ("fail", "analytic"): "Arithmetic fails",
}


def flat(prefix, obj, out):
    if isinstance(obj, dict):
        for k, v in obj.items():
            k = re.sub(r"p\((\d+)(?:\.(\d+))?\)", lambda m: "p" + m.group(1) + (m.group(2) or ""), str(k))
            flat(f"{prefix}.{k}" if prefix else k, v, out)
    elif isinstance(obj, bool):
        out[prefix] = int(obj)
    elif isinstance(obj, (int, float)):
        out[prefix] = obj


def flatten(argv):
    out = {}
    it = iter(argv)
    for a in it:
        if a == "--set":
            name, _, value = next(it).partition("=")
            out[name] = float(value)
            continue
        prefix, _, path = a.partition("=")
        with open(path) as f:
            data = json.load(f)
        if isinstance(data, dict) and isinstance(data.get("metrics"), dict):  # a k6 summary
            for name, m in data["metrics"].items():
                flat(f"{prefix}.{name}", m.get("values", m), out)
            # k6 can omit zero drops. Only infer zero for a window with iterations.
            for name in data["metrics"]:
                if (name == "iterations" or name.endswith(".iterations")) and f"{prefix}.{name}.count" in out:
                    out.setdefault(f"{prefix}.{name.removesuffix('iterations')}dropped_iterations.count", 0)
        else:
            flat(prefix, data, out)
    json.dump(out, sys.stdout, indent=1, sort_keys=True)
    print()


def load_runs(root):
    """{scenario: [(run name, metrics)]}"""
    runs = {}
    if not os.path.isdir(root):
        return runs
    for scenario in sorted(os.listdir(root)):
        sdir = os.path.join(root, scenario)
        if not os.path.isdir(sdir):
            continue
        for run in sorted(os.listdir(sdir)):
            p = os.path.join(sdir, run, "metrics.json")
            if os.path.exists(p):
                with open(p) as f:
                    runs.setdefault(scenario, []).append((run, json.load(f)))
    return runs


def evaluate(check, metrics):
    """-> (ok or None when a number is missing, value, target)"""
    value = metrics.get(check["metric"])
    target = check["target"]
    if isinstance(target, str):  # another metric of the same run, optionally scaled: "sink.calls*0.01"
        name, _, factor = target.partition("*")
        target = metrics.get(name.strip())
        if target is not None and factor:
            target = target * float(factor)
    if value is None or target is None:
        return None, value, target
    return OPS[check["op"]](value, target), value, target


def judge_item(item, runs, gates, min_runs):
    checks = item.get("checks") or [{k: item[k] for k in ("metric", "op", "target")}]
    use_gates = item.get("evidence", "measured") in ("measured", "scaled") and not item.get("no_gates")
    rows, valid = [], []
    for name, metrics in runs:
        row = {"run": name, "valid": True, "why_invalid": [], "values": {}, "pass": True}
        if use_gates:
            for g in gates:
                if g.get("scenarios") and item.get("scenario") not in g["scenarios"]:
                    continue
                ok, value, _ = evaluate(g, metrics)
                if ok is None and g.get("optional"):
                    continue
                if not ok:
                    row["valid"] = False
                    row["why_invalid"].append(f"{g['id']}: {g['metric']} = {value if value is not None else 'missing'}")
        for c in checks:
            ok, value, target = evaluate(c, metrics)
            row["values"][c["metric"]] = value
            if ok is None:
                row["valid"] = False
                row["why_invalid"].append(f"no value for {c['metric'] if value is None else c['target']}")
            elif not ok:
                row["pass"] = False
        rows.append(row)
        if row["valid"]:
            valid.append(row)

    summary = []  # one entry per check, in order
    for c in checks:
        vals = [r["values"][c["metric"]] for r in valid if r["values"].get(c["metric"]) is not None]
        if vals:
            summary.append({"metric": c["metric"], "median": statistics.median(vals), "min": min(vals), "max": max(vals),
                            "op": c["op"], "target": c["target"], "unit": c.get("unit", item.get("unit", ""))})
    need = item.get("min_runs", min_runs if use_gates else 1)
    if not rows:
        verdict, note = "not-run", "No run of this scenario has results."
    elif len(valid) < need:
        bad = sorted({w for r in rows for w in r["why_invalid"]})
        verdict, note = "inconclusive", f"{len(valid)} valid run(s) of {len(rows)}, {need} needed." + (" Invalid because: " + "; ".join(bad[:4]) if bad else "")
    elif all(r["pass"] for r in valid):
        verdict, note = "pass", f"{len(valid)} of {len(valid)} valid runs pass."
    elif not any(r["pass"] for r in valid):
        verdict, note = "fail", f"{len(valid)} of {len(valid)} valid runs fail."
    else:
        n = sum(r["pass"] for r in valid)
        verdict, note = "inconclusive", f"Runs disagree: {n} of {len(valid)} pass. The margin is inside the run-to-run spread."
    return {"verdict": verdict, "note": note, "runs": rows, "summary": summary}


def judge(argv):
    out_path = None
    if "--out" in argv:
        i = argv.index("--out")
        out_path = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]
    with open(argv[0]) as f:
        spec = json.load(f)
    runs = load_runs(argv[1])
    gates, min_runs = spec.get("gates", []), spec.get("min_runs", 3)

    # Calibration: the bench's own checks. The latest calibration run is the one that counts.
    calibration = []
    latest = {}
    for c in spec.get("calibration", []):
        scenario = c["scenario"]
        if scenario not in latest:
            candidates = runs.get(scenario, [])
            latest[scenario] = [max(candidates, key=lambda run: (
                os.stat(os.path.join(argv[1], scenario, run[0], "metrics.json")).st_mtime_ns, run[0],
            ))] if candidates else []
        r = judge_item({**c, "evidence": "analytic"}, latest[scenario], [], 1)
        calibration.append({**c, **r, "label": {"pass": "Holds", "fail": "Does not hold", "not-run": "Not run"}.get(r["verdict"], "Inconclusive")})
    uncalibrated = [c["id"] for c in calibration if c["verdict"] != "pass"]
    calibration_problem = ", ".join(uncalibrated) if calibration else "no calibration checks defined"

    controls = {}
    for c in spec.get("controls", []):
        r = judge_item(c, runs.get(c["scenario"], []), gates, 1)
        controls[c["id"]] = {**c, **r, "label": {"pass": "Detected", "fail": "NOT detected", "not-run": "Not run"}.get(r["verdict"], "Inconclusive")}

    claims = []
    for c in spec["claims"]:
        ev = c.get("evidence", "measured")
        if ev == "untestable":
            claims.append({**c, "verdict": "not-testable", "label": "Not testable here", "note": c.get("reason", ""), "runs": [], "summary": []})
            continue
        r = judge_item(c, runs.get(c.get("scenario", ""), []), gates, min_runs)
        guards = [k for k, v in controls.items() if c["id"] in v.get("guards", [])]
        unproven = [k for k in guards if controls[k]["verdict"] != "pass"]
        if r["verdict"] == "pass" and unproven:
            r["verdict"] = "inconclusive"
            r["note"] = f"The checks pass, but control {', '.join(unproven)} has not shown that they can fail."
        exemption = c.get("calibration_exemption")
        if r["verdict"] in ("pass", "fail") and calibration_problem and ev in ("measured", "scaled"):
            if isinstance(exemption, str) and exemption.strip():
                r["note"] += f" Calibration exemption: {exemption.strip()}"
            else:
                r["note"] = f"The checks {r['verdict']}, but the bench is not calibrated ({calibration_problem}), so the numbers cannot be trusted either way."
                r["verdict"] = "inconclusive"
        label = LABELS.get((r["verdict"], ev), {"inconclusive": "Inconclusive", "not-run": "Not run"}.get(r["verdict"], r["verdict"]))
        claims.append({**c, **r, "label": label, "controls": guards})

    counts = {}
    for c in claims:
        counts[c["verdict"]] = counts.get(c["verdict"], 0) + 1
    result = {"design": spec.get("design", {}), "bench": spec.get("bench", {}), "judged": time.strftime("%Y-%m-%d %H:%M"),
              "min_runs": min_runs, "gates": gates, "counts": counts, "claims": claims, "controls": list(controls.values()), "calibration": calibration,
              "scenarios": {s: [n for n, _ in rs] for s, rs in runs.items()}}
    if out_path:
        with open(out_path, "w") as f:
            json.dump(result, f, indent=1)

    def num(v):
        return "–" if v is None else (f"{v:,.0f}" if abs(v) >= 100 or float(v).is_integer() else f"{v:,.3g}")
    print("| ID | Claim | Target | Measured: median (range) | Verdict |")
    print("|---|---|---|---|---|")
    for c in claims:
        tgt = "; ".join(f"{s['op']} {num(s['target']) if not isinstance(s['target'], str) else s['target']} {s['unit']}".strip() for s in c["summary"]) or "–"
        got = "; ".join(f"{num(s['median'])} ({num(s['min'])} to {num(s['max'])})" for s in c["summary"]) or "–"
        print(f"| {c['id']} | {c.get('statement', '')} | {tgt} | {got} | **{c['label']}**. {c['note']} |")
    for c in controls.values():
        print(f"| {c['id']} | Control: {c.get('statement', '')} | | | **{c['label']}** |")
    for c in calibration:
        got = "; ".join(f"{num(s['median'])}" for s in c["summary"]) or "–"
        print(f"| {c['id']} | Bench: {c.get('statement', '')} | | {got} | **{c['label']}** |")
    print("\n" + ", ".join(f"{v} {k}" for k, v in sorted(counts.items())))
    return 1 if counts.get("fail") else 0


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "flatten":
        flatten(sys.argv[2:])
    elif len(sys.argv) >= 4 and sys.argv[1] == "judge":
        sys.exit(judge(sys.argv[2:]))
    else:
        print(__doc__)
        sys.exit(2)
