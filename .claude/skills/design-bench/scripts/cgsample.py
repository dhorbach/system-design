#!/usr/bin/env python3
"""Sample what every part of the bench consumed, straight from the kernel's cgroup files.

    cgsample.py run --project bench-x --out samples.jsonl [--interval 2]
    cgsample.py summarize samples.jsonl [--from MS --to MS] > resources.json

`run` samples until it is stopped (SIGINT or SIGTERM): every container of the
compose project. It reads the
counters the limits are enforced with, so "was it throttled" and "how close to
the memory limit" need no agent inside the bench. It also samples the host, to
show whether something outside the bench disturbed the run.

`summarize` turns a window of samples into one flat set of numbers per unit:
utilization (against the unit's limit), saturation (throttled share, pressure),
and errors (OOM kills, restarts): the USE method, per container.

Needs cgroup v2. Reads only; never writes to a cgroup.
"""
import argparse
import glob
import json
import math
import os
import re
import signal
import subprocess
import sys
import time

CG = "/sys/fs/cgroup"


def sh(cmd):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        return r.stdout if r.returncode == 0 else ""
    except Exception:
        return ""


def read(path):
    try:
        with open(path) as f:
            return f.read()
    except OSError:
        return ""


def kv(text):
    out = {}
    for line in text.splitlines():
        p = line.split()
        if len(p) == 2:
            try:
                out[p[0]] = int(p[1])
            except ValueError:
                pass
    return out


def pressure(text):
    m = re.search(r"some .*?total=(\d+)", text)
    return int(m.group(1)) if m else 0


def container_cgroup(cid):
    for pattern in (f"{CG}/system.slice/docker-{cid}.scope", f"{CG}/docker/{cid}", f"{CG}/**/docker-{cid}.scope"):
        hits = glob.glob(pattern, recursive=True)
        if hits:
            return hits[0]
    return ""


def compose_units(project):
    out = sh(["docker", "ps", "--no-trunc", "--filter", f"label=com.docker.compose.project={project}",
              "--format", '{{.ID}} {{.Label "com.docker.compose.service"}} {{.Names}}'])
    units = {}
    for line in out.splitlines():
        cid, service, name = (line.split() + ["", ""])[:3]
        path = container_cgroup(cid)
        if path:
            units[(name or service).removeprefix(project + "-")] = (path, cid, service)
    return units


def cpu_set(text):
    cpus = set()
    for part in filter(None, text.split(",")):
        first, _, last = part.partition("-")
        cpus.update(range(int(first), int(last or first) + 1))
    return cpus


def sample_unit(path):
    cpu, mem, ev = kv(read(f"{path}/cpu.stat")), kv(read(f"{path}/memory.stat")), kv(read(f"{path}/memory.events"))
    io = {"rbytes": 0, "wbytes": 0, "rios": 0, "wios": 0}
    for line in read(f"{path}/io.stat").splitlines():
        for k, v in re.findall(r"(rbytes|wbytes|rios|wios)=(\d+)", line):
            io[k] += int(v)
    quota = read(f"{path}/cpu.max").split()
    mmax = read(f"{path}/memory.max").strip()
    cpuset = read(f"{path}/cpuset.cpus.effective")
    return {
        "cpu_usec": cpu.get("usage_usec", 0), "periods": cpu.get("nr_periods", 0),
        "throttled": cpu.get("nr_throttled", 0), "throttled_usec": cpu.get("throttled_usec", 0),
        "cpu_limit": (int(quota[0]) / int(quota[1])) if len(quota) == 2 and quota[0] != "max" else None,
        "mem": int(read(f"{path}/memory.current") or 0), "anon": mem.get("anon", 0), "file": mem.get("file", 0),
        "mem_limit": int(mmax) if mmax.isdigit() else None,
        "cpuset": cpuset,
        "cpus_allowed": len(cpu_set(cpuset)),
        "oom_kill": ev.get("oom_kill", 0), "pids": int(read(f"{path}/pids.current") or 0),
        "psi_cpu": pressure(read(f"{path}/cpu.pressure")), "psi_io": pressure(read(f"{path}/io.pressure")),
        "psi_mem": pressure(read(f"{path}/memory.pressure")), **io,
    }


def sample_host():
    f = read("/proc/stat").splitlines()[0].split()[1:]
    vals = list(map(int, f))
    idle = vals[3] + vals[4]
    return {"cpu_total": sum(vals), "cpu_idle": idle, "psi_cpu": pressure(read("/proc/pressure/cpu")),
            "psi_io": pressure(read("/proc/pressure/io")), "psi_mem": pressure(read("/proc/pressure/memory")),
            "ncpu": os.cpu_count()}


def run(args):
    stop = []
    signal.signal(signal.SIGINT, lambda *_: stop.append(1))
    signal.signal(signal.SIGTERM, lambda *_: stop.append(1))
    with open(args.out, "a") as out:
        nxt = time.time()
        while not stop:
            units = compose_units(args.project)
            t = int(time.time() * 1000)
            out.write(json.dumps({"t": t, "unit": "host", **sample_host()}) + "\n")
            for name, (path, ident, service) in units.items():
                out.write(json.dumps({"t": t, "unit": name, "id": ident[:12],
                                      "service": service, **sample_unit(path)}) + "\n")
            out.flush()
            nxt += args.interval
            while not stop and time.time() < nxt:
                time.sleep(0.05)


def slope(points):
    """Least-squares slope of (seconds, value)."""
    n = len(points)
    if n < 3:
        return 0.0
    mx = sum(p[0] for p in points) / n
    my = sum(p[1] for p in points) / n
    den = sum((p[0] - mx) ** 2 for p in points)
    return sum((p[0] - mx) * (p[1] - my) for p in points) / den if den else 0.0


def summarize(args):
    rows = {}
    with open(args.samples) as f:
        for line in f:
            r = json.loads(line)
            if (args.frm and r["t"] < args.frm) or (args.to and r["t"] > args.to):
                continue
            rows.setdefault(r["unit"], []).append(r)
    out = {}
    for unit, rs in rows.items():
        rs.sort(key=lambda r: r["t"])
        if len(rs) < 2:
            continue
        first, last = rs[0], rs[-1]
        secs = (last["t"] - first["t"]) / 1000
        if unit == "host":
            busy = [1 - (b["cpu_idle"] - a["cpu_idle"]) / max(1, b["cpu_total"] - a["cpu_total"]) for a, b in zip(rs, rs[1:])]
            out["host"] = {"seconds": round(secs, 1), "cpu_busy_avg": round(sum(busy) / len(busy), 4),
                           "cpu_busy_max": round(max(busy), 4),
                           "psi_cpu": round((last["psi_cpu"] - first["psi_cpu"]) / 1e6 / secs, 4),
                           "psi_io": round((last["psi_io"] - first["psi_io"]) / 1e6 / secs, 4)}
            continue
        # A restarted container has a new id and its counters start again: add up per id.
        segs, cur = [], [rs[0]]
        for r in rs[1:]:
            if r.get("id") != cur[-1].get("id"):
                segs.append(cur)
                cur = []
            cur.append(r)
        segs.append(cur)
        tot = lambda k: sum(s[-1][k] - s[0][k] for s in segs)
        cores = [(b["cpu_usec"] - a["cpu_usec"]) / 1000 / max(1, b["t"] - a["t"]) for s in segs for a, b in zip(s, s[1:])]
        limit, mlimit = last.get("cpu_limit"), last.get("mem_limit")
        periods = tot("periods")
        u = {
            "service": last.get("service"),
            "seconds": round(secs, 1),
            "cpu_cores_avg": round(tot("cpu_usec") / 1e6 / secs, 4),
            "cpu_cores_max": round(max(cores), 4) if cores else 0,
            "cpu_limit": limit,
            "throttled_share": round(tot("throttled") / periods, 4) if periods else 0,
            "throttled_s": round(tot("throttled_usec") / 1e6, 3),
            "mem_max_mb": round(max(r["mem"] for r in rs) / 1048576, 1),
            "anon_max_mb": round(max(r["anon"] for r in rs) / 1048576, 1),
            "anon_slope_mb_per_h": round(slope([((r["t"] - first["t"]) / 1000, r["anon"]) for r in rs]) * 3600 / 1048576, 3),
            "mem_limit_mb": round(mlimit / 1048576, 1) if mlimit else None,
            "mem_limit_bytes": mlimit,
            "oom_kills": tot("oom_kill"), "restarts": len(segs) - 1, "pids_max": max(r["pids"] for r in rs),
            "write_iops": round(tot("wios") / secs, 1), "write_mb_s": round(tot("wbytes") / 1048576 / secs, 2),
            "read_iops": round(tot("rios") / secs, 1),
            "psi_cpu": round(tot("psi_cpu") / 1e6 / secs, 4), "psi_io": round(tot("psi_io") / 1e6 / secs, 4),
            "psi_mem": round(tot("psi_mem") / 1e6 / secs, 4),
        }
        if limit:
            u["cpu_util_avg"] = round(u["cpu_cores_avg"] / limit, 4)
            u["cpu_util_max"] = round(u["cpu_cores_max"] / limit, 4)
        if last.get("cpus_allowed"):  # for a unit with a CPU set and no quota (the load generator)
            u["cpuset"] = last.get("cpuset", "")
            u["cpus_allowed"] = last["cpus_allowed"]
            u["cpu_of_set_max"] = round(u["cpu_cores_max"] / last["cpus_allowed"], 4)
        if mlimit:
            u["mem_util_max"] = round(max(r["mem"] for r in rs) / mlimit, 4)
        out[unit] = u
    json.dump(out, sys.stdout, indent=1)
    print()


def limit_problems(services, resources):
    expected = {name: spec for name, spec in services.items()
                if name not in {"toxiproxy", "sink", "k6", "burn"} and not spec.get("profiles")}
    if not expected:
        return ["No measured services in the Compose configuration"]

    problems = []
    for service, spec in expected.items():
        replicas = spec.get("scale", spec.get("deploy", {}).get("replicas", 1))
        units = {name: unit for name, unit in resources.items() if unit.get("service") == service}
        if len(units) != replicas or replicas < 1:
            problems.append(f"{service}: expected {replicas} running replica(s), sampled {len(units)}")
        cpus = float(spec.get("cpus") or 0)
        memory = int(spec.get("mem_limit") or 0)
        cpuset = cpu_set(spec.get("cpuset") or "")
        if not (cpus > 0 and memory > 0 and cpuset):
            problems.append(f"{service}: set cpus, mem_limit and cpuset in Compose")
            continue
        for name, unit in units.items():
            if not math.isclose(unit.get("cpu_limit") or 0, cpus, abs_tol=1e-5):
                problems.append(f"{name}: CPU limit {unit.get('cpu_limit')}, expected {cpus}")
            if unit.get("mem_limit_bytes") != memory:
                problems.append(f"{name}: memory limit {unit.get('mem_limit_bytes')}, expected {memory} bytes")
            if cpu_set(unit.get("cpuset", "")) != cpuset:
                problems.append(f"{name}: CPU set {unit.get('cpuset')}, expected {spec['cpuset']}")
    return problems


def check_limits(args):
    with open(args.compose) as f:
        services = json.load(f)["services"]
    with open(args.resources) as f:
        resources = json.load(f)
    problems = limit_problems(services, resources)
    for problem in problems:
        print(problem, file=sys.stderr)
    print(len(problems))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--project", required=True, help="compose project name")
    r.add_argument("--out", required=True)
    r.add_argument("--interval", type=float, default=2.0)
    s = sub.add_parser("summarize")
    s.add_argument("samples")
    s.add_argument("--from", dest="frm", type=int, default=0, help="window start, Unix ms")
    s.add_argument("--to", type=int, default=0, help="window end, Unix ms")
    c = sub.add_parser("check-limits", help="count limit or coverage failures for measured Compose services")
    c.add_argument("compose", help="service limits from docker compose config --format json")
    c.add_argument("resources", help="summarized cgroup samples")
    args = ap.parse_args()
    if args.cmd == "run" and not os.path.exists(f"{CG}/cgroup.controllers"):
        sys.exit("cgsample needs cgroup v2")
    {"run": run, "summarize": summarize, "check-limits": check_limits}[args.cmd](args)


if __name__ == "__main__":
    main()
