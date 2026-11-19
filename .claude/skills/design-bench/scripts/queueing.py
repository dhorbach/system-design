#!/usr/bin/env python3
"""Two checks from queueing theory, to compare a design's arithmetic with what was measured.

    queueing.py little --rate 200 --time 0.150 [--inflight 31]
    queueing.py mmc --rate 200 --service 0.150 --servers 40 [--json]

little: Little's law, L = rate x time. It holds for any system in a steady state,
whatever the distribution, so it is a test of the measurement itself: if the
in-flight count you observed is not rate x time, either the run was not steady
or one of the three numbers is measured wrong. It also sizes a pool: 50 workers
that each hold a job for 10 s can start at most 50 / 10 = 5 jobs a second.

mmc: c identical servers, random (Poisson) arrivals, exponential service times.
Gives the utilization, the chance a request waits, and the waiting time. Real
service times are rarely exponential, so read it as the shape (waiting explodes
as utilization nears 1), and as a floor for how many servers are needed, not as
a prediction of the measured tail.
"""
import argparse
import json
import math
import sys


def erlang_c(c, a):
    """Probability an arrival waits, for c servers and offered load a = rate x service."""
    if a >= c:
        return 1.0
    inv_b = 1.0
    for k in range(1, c + 1):  # Erlang B by its recurrence: stable for large c
        inv_b = 1 + inv_b * k / a
    b = 1 / inv_b
    return b / (1 - (a / c) * (1 - b))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    li = sub.add_parser("little")
    li.add_argument("--rate", type=float, required=True, help="completions per second")
    li.add_argument("--time", type=float, required=True, help="mean time in the system, seconds")
    li.add_argument("--inflight", type=float, help="mean number in the system, as observed")
    mm = sub.add_parser("mmc")
    mm.add_argument("--rate", type=float, required=True, help="arrivals per second")
    mm.add_argument("--service", type=float, required=True, help="mean service time, seconds")
    mm.add_argument("--servers", type=int, required=True)
    mm.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if args.cmd == "little":
        expect = args.rate * args.time
        print(f"rate x time = {args.rate:g} x {args.time:g} = {expect:,.2f} in flight")
        if args.inflight is not None:
            off = abs(args.inflight - expect) / expect if expect else 0
            print(f"observed {args.inflight:,.2f}: {off:.0%} off. " +
                  ("Consistent." if off <= 0.10 else "More than 10% apart: the run was not steady, or one of the three numbers is wrong."))
            return 0 if off <= 0.10 else 1
        return 0

    a = args.rate * args.service
    rho = a / args.servers
    out = {"offered_load": round(a, 3), "utilization": round(rho, 4), "stable": rho < 1}
    if rho < 1:
        pw = erlang_c(args.servers, a)
        drain = args.servers / args.service - args.rate          # c*mu - lambda
        out.update({"p_wait": round(pw, 4), "mean_wait_s": round(pw / drain, 5),
                    "mean_time_s": round(pw / drain + args.service, 5),
                    # P(wait > t) = p_wait * exp(-drain * t)
                    "p99_wait_s": round(max(0.0, math.log(pw / 0.01) / drain), 5) if pw > 0.01 else 0.0,
                    "servers_for_80pct": math.ceil(a / 0.8)})
    if args.json:
        json.dump(out, sys.stdout, indent=1)
        print()
        return 0
    print(f"Offered load {a:,.2f} server-seconds per second on {args.servers} servers: utilization {rho:.0%}.")
    if rho >= 1:
        print(f"Unstable: work arrives faster than it can be served, and the queue grows without bound. At least {math.floor(a) + 1} servers are needed.")
        return 1
    print(f"{out['p_wait']:.1%} of requests wait. Mean wait {out['mean_wait_s'] * 1000:,.1f} ms; 99% wait at most {out['p99_wait_s'] * 1000:,.1f} ms; "
          f"mean time in system {out['mean_time_s'] * 1000:,.1f} ms.")
    print(f"For 80% utilization: {out['servers_for_80pct']} servers.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
