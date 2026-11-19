#!/usr/bin/env python3
"""What this machine can offer a bench, and what would spoil a measurement on it.

    python3 preflight.py            # readable report
    python3 preflight.py --json     # the same facts for scripts

It only reads. It reports Docker and compose, whether CPU, memory and disk
limits can be enforced, whether delays can be injected in the kernel, how the
CPUs are laid out (and a suggested split between the system under test, its
datastores, the stand-ins and the load generator), and what else is running.
"""
import json
import os
import re
import shutil
import subprocess
import sys


def sh(cmd, timeout=15):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""


def read(path):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return ""


def cpu_list(text):
    """'0-3,8' -> [0, 1, 2, 3, 8]"""
    out = []
    for part in filter(None, text.split(",")):
        a, _, b = part.partition("-")
        out.extend(range(int(a), int(b or a) + 1))
    return out


def fmt_cpus(cpus):
    """[0, 1, 2, 3, 8] -> '0-3,8'"""
    cpus, out, i = sorted(cpus), [], 0
    while i < len(cpus):
        j = i
        while j + 1 < len(cpus) and cpus[j + 1] == cpus[j] + 1:
            j += 1
        out.append(str(cpus[i]) if i == j else f"{cpus[i]}-{cpus[j]}")
        i = j + 1
    return ",".join(out)


def cpus():
    online = cpu_list(read("/sys/devices/system/cpu/online"))
    cores = {}
    for c in online:
        sib = read(f"/sys/devices/system/cpu/cpu{c}/topology/thread_siblings_list")
        cores.setdefault(sib or str(c), cpu_list(sib) if sib else [c])
    fast = cpu_list(read("/sys/devices/cpu_core/cpus"))   # hybrid CPUs only
    slow = cpu_list(read("/sys/devices/cpu_atom/cpus"))
    info = {
        "logical": len(online),
        "physical_cores": len(cores),
        "threads_per_core": max(len(v) for v in cores.values()) if cores else 1,
        "model": sh("grep -m1 'model name' /proc/cpuinfo | cut -d: -f2").strip(),
        "governor": read("/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor"),
        "hybrid": bool(fast and slow),
        "fast_cpus": fmt_cpus(fast), "slow_cpus": fmt_cpus(slow),
    }
    # A split that keeps the load generator and the stand-ins off the CPUs being measured.
    if info["hybrid"]:
        # Unequal cores: the measured side gets one kind only, or a "0.5 CPU" limit means two things.
        n = len(fast)
        cut = max(2, (n * 5 // 8) // 2 * 2)
        aux, load = slow[:len(slow) // 2], slow[len(slow) // 2:]
        monitor = next((group for group in reversed(list(cores.values()))
                        if set(group) < set(aux)), [])
        info["map"] = {"sut": fmt_cpus(fast[:cut]), "data": fmt_cpus(fast[cut:]),
                       "aux": fmt_cpus(set(aux) - set(monitor)), "load": fmt_cpus(load),
                       "mon": fmt_cpus(monitor)}
    else:
        groups = list(cores.values())
        monitor = groups.pop() if len(groups) >= 5 else []
        n = len(groups)
        a = n // 2
        b = min(n * 3 // 4, n - 2) if n >= 4 else n * 3 // 4
        c = max(b + 1, n * 7 // 8) if n >= 4 else n * 7 // 8
        slices = {"sut": groups[:a], "data": groups[a:b], "aux": groups[b:c], "load": groups[c:]}
        info["map"] = {name: fmt_cpus(cpu for group in bucket for cpu in group)
                       for name, bucket in slices.items()}
        info["map"]["mon"] = fmt_cpus(monitor)
    return info


def docker():
    if not shutil.which("docker"):
        return {"present": False}
    fmt = "{{.ServerVersion}}|{{.CgroupDriver}}|{{.CgroupVersion}}|{{.Driver}}|{{.DockerRootDir}}|{{.NCPU}}|{{.MemTotal}}"
    parts = sh(f"docker info --format '{fmt}'").split("|")
    if len(parts) < 7:
        return {"present": True, "usable": False}
    root = parts[4]
    src = sh(f"findmnt -no SOURCE,FSTYPE -T {root}").split()
    dev = src[0] if src else ""
    disk = sh(f"lsblk -ndo PKNAME {dev}") or os.path.basename(dev)
    running = [l for l in sh("docker ps --format '{{.Names}}'").splitlines() if l]
    return {
        "present": True, "usable": True, "version": parts[0], "cgroup_driver": parts[1],
        "cgroup_version": parts[2], "storage_driver": parts[3], "root": root,
        "compose": sh("docker compose version --short"),
        "data_fs": src[1] if len(src) > 1 else "", "data_device": f"/dev/{disk}" if disk else "",
        "data_device_model": read(f"/sys/block/{disk}/device/model"),
        "data_device_rotational": read(f"/sys/block/{disk}/queue/rotational") == "1",
        "free_gb": int(sh(f"df -BG --output=avail {root} | tail -1").strip("G ") or 0),
        "running_containers": running,
    }


def main():
    d = docker()
    controllers = read("/sys/fs/cgroup/cgroup.controllers").split()
    mem_kb = int(re.search(r"MemAvailable:\s+(\d+)", read("/proc/meminfo") or "MemAvailable: 0").group(1))
    psi = read("/proc/pressure/cpu")
    psi60 = float(re.search(r"some .*?avg60=([\d.]+)", psi).group(1)) if psi else None
    facts = {
        "kernel": os.uname().release,
        "wsl": "microsoft" in read("/proc/version").lower(),
        "cpu": cpus(),
        "mem_available_gb": round(mem_kb / 1048576, 1),
        "cgroup_v2": os.path.exists("/sys/fs/cgroup/cgroup.controllers"),
        "cgroup_controllers": controllers,
        "netem": bool(sh("modinfo -F filename sch_netem")) or "sch_netem" in read("/proc/modules"),
        "docker": d,
        "tools": {t: bool(shutil.which(t)) for t in ("go", "jq", "curl", "git", "flock")},
        "load_1m": float(read("/proc/loadavg").split()[0]),
        "cpu_pressure_avg60": psi60,
    }

    problems, notes = [], []
    if not d.get("usable"):
        problems.append("Docker is missing or not usable by this user: no bench can run.")
    if not facts["cgroup_v2"]:
        problems.append("cgroup v1: disk limits apply to direct I/O only and throttling counters differ. "
                        "Treat every limit as unverified until calibration shows it biting.")
    for c in ("cpu", "memory", "io", "cpuset"):
        if facts["cgroup_v2"] and c not in controllers:
            problems.append(f"cgroup controller '{c}' is not enabled: that limit cannot be enforced.")
    if facts["wsl"]:
        notes.append("WSL: no netem and no disk throttling in the kernel. Use a proxy for delays and report disk as uncapped.")
    if not facts["netem"]:
        notes.append("No netem module: packet-level delay, loss and reordering are unavailable. Use Toxiproxy (TCP only).")
    if d.get("usable"):
        if d["data_fs"] not in ("ext4", "xfs", "btrfs", "f2fs"):
            notes.append(f"Docker data is on {d['data_fs'] or 'an unknown filesystem'}: buffered writes may escape disk limits.")
        if d["running_containers"]:
            notes.append(f"{len(d['running_containers'])} other container(s) are running "
                         f"({', '.join(d['running_containers'][:4])}{'…' if len(d['running_containers']) > 4 else ''}). "
                         "Leave them alone; pin the bench to its own CPUs and watch host pressure during runs.")
    if facts["cpu"]["hybrid"]:
        notes.append(f"Hybrid CPU: fast cores {facts['cpu']['fast_cpus']}, slow cores {facts['cpu']['slow_cpus']}. "
                     "Pin everything that is measured to one kind; an unpinned limit means a different speed on each run.")
    if not facts["cpu"]["map"]["mon"]:
        notes.append("No dedicated monitoring CPU in the suggested split. Reserve a physical core if possible.")
    if facts["cpu"]["governor"] and facts["cpu"]["governor"] != "performance":
        notes.append(f"CPU governor is '{facts['cpu']['governor']}': expect more run-to-run spread at low load. Record it in the report.")
    if psi60 is not None and psi60 > 5:
        notes.append(f"The host is already busy (CPU pressure {psi60}% over the last minute). Results will not be clean.")
    for t in ("jq", "curl", "git", "flock"):
        if not facts["tools"][t]:
            problems.append(f"'{t}' is not installed: run.sh needs it.")
    facts["problems"], facts["notes"] = problems, notes
    facts["compose"] = bool(d.get("usable") and d.get("compose"))
    if d.get("usable") and not d.get("compose"):
        problems.append("docker compose is missing: no bench can run.")

    if "--json" in sys.argv:
        json.dump(facts, sys.stdout, indent=1)
        print()
        return 1 if problems else 0

    c = facts["cpu"]
    print(f"Host      {c['model']}; {c['logical']} CPUs on {c['physical_cores']} cores; "
          f"{facts['mem_available_gb']} GB memory free; kernel {facts['kernel']}")
    if d.get("usable"):
        print(f"Docker    {d['version']}, compose {d['compose'] or 'missing'}, cgroup v{d['cgroup_version']} ({d['cgroup_driver']}), "
              f"data on {d['data_fs']} {d['data_device']} ({d['data_device_model'] or 'unknown'}), {d['free_gb']} GB free")
    print(f"Limits    cgroup controllers: {' '.join(controllers) or 'none'}")
    print(f"Delays    netem: {'yes' if facts['netem'] else 'no'}; Toxiproxy runs as a container")
    print(f"CPU map   measured services {c['map']['sut']} | datastores {c['map']['data']} | "
          f"stand-ins and proxies {c['map']['aux']} | load generator {c['map']['load']} | "
          f"monitoring {c['map']['mon'] or 'shares auxiliary CPUs'}")
    for p in problems:
        print("PROBLEM  ", p)
    for n in notes:
        print("note     ", n)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
