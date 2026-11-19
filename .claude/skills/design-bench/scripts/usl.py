#!/usr/bin/env python3
"""Fit the Universal Scalability Law to measured points and extrapolate, with its error shown.

    usl.py 1:301 2:560 3:790 4:980 6:1290 8:1480 --at 16 [--need 2400] [--json]

Each point is N:throughput, where N is what was scaled (nodes, partitions,
workers, connections) and throughput is the highest rate that still met the
latency target at that N (from a breakpoint run, not a rate you merely offered).

    X(N) = g*N / (1 + a*(N-1) + b*N*(N-1))

g: throughput of one unit. a: contention (the share of work that is serial:
a shared lock, a single writer). b: coherency (the cost of units keeping each
other in step); b > 0 means throughput peaks at N = sqrt((1-a)/b) and then falls.

The prediction comes with the range it takes when any one point is left out. A
wide range means the points do not pin the curve down; say so in the report
instead of quoting the middle. The fit knows nothing about limits that only
appear beyond the measured range (a NIC, a connection cap, a second bottleneck),
so it bounds the claim from above: it can show a design will NOT scale, and can
only say that nothing measured so far prevents it.
"""
import json
import math
import sys


def model(n, g, a, b):
    return g * n / (1 + a * (n - 1) + b * n * (n - 1))


def sse(pts, g, a, b):
    return sum((x - model(n, g, a, b)) ** 2 for n, x in pts)


def fit(pts):
    """Least squares in the measured units, a and b kept at or above zero. Nelder-Mead, no packages."""
    g0 = min(pts)[1] / min(pts)[0]
    f = lambda p: sse(pts, abs(p[0]), abs(p[1]), abs(p[2]))
    best = None
    for start in ((g0, 0.02, 0.0005), (g0, 0.2, 0.01), (g0 * 1.2, 0.0, 0.0)):
        simplex = [list(start)] + [[start[j] * (1.5 if i == j else 1) + (1e-4 if i == j else 0) for j in range(3)] for i in range(3)]
        for _ in range(4000):
            simplex.sort(key=f)
            lo, hi = simplex[0], simplex[-1]
            if abs(f(hi) - f(lo)) < 1e-12 * (1 + f(lo)):
                break
            c = [sum(p[j] for p in simplex[:-1]) / 3 for j in range(3)]
            refl = [c[j] + (c[j] - hi[j]) for j in range(3)]
            if f(refl) < f(lo):
                exp = [c[j] + 2 * (c[j] - hi[j]) for j in range(3)]
                simplex[-1] = exp if f(exp) < f(refl) else refl
            elif f(refl) < f(simplex[-2]):
                simplex[-1] = refl
            else:
                con = [c[j] + 0.5 * (hi[j] - c[j]) for j in range(3)]
                if f(con) < f(hi):
                    simplex[-1] = con
                else:
                    simplex = [lo] + [[lo[j] + 0.5 * (p[j] - lo[j]) for j in range(3)] for p in simplex[1:]]
        simplex.sort(key=f)
        if best is None or f(simplex[0]) < f(best):
            best = simplex[0]
    return tuple(abs(v) for v in best)


def main():
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        return 2
    opt = {}
    for flag in ("--at", "--need"):
        if flag in args:
            i = args.index(flag)
            opt[flag] = float(args[i + 1])
            del args[i:i + 2]
    as_json = "--json" in args
    pts = sorted((float(a.split(":")[0]), float(a.split(":")[1])) for a in args if ":" in a)
    if len(pts) < 4:
        print("Need at least 4 points to fit three numbers; 6 or more for a prediction worth quoting.", file=sys.stderr)
        return 2

    g, a, b = fit(pts)
    mean = sum(x for _, x in pts) / len(pts)
    r2 = 1 - sse(pts, g, a, b) / (sum((x - mean) ** 2 for _, x in pts) or 1)
    peak_n = math.sqrt((1 - a) / b) if b > 1e-12 and a < 1 else None
    out = {"points": pts, "per_unit": round(g, 3), "contention": round(a, 5), "coherency": round(b, 7), "r2": round(r2, 4),
           "peak_n": round(peak_n, 1) if peak_n else None, "peak_throughput": round(model(peak_n, g, a, b), 1) if peak_n else None,
           "warnings": []}
    max_n = pts[-1][0]
    if len(pts) < 6:
        out["warnings"].append(f"{len(pts)} points: fewer than 6, the curve is weakly pinned.")
    if "--at" in opt:
        n = opt["--at"]
        loo = []
        for i in range(len(pts)):
            rest = pts[:i] + pts[i + 1:]
            if len(rest) >= 4:
                loo.append(model(n, *fit(rest)))
        pred = model(n, g, a, b)
        out.update({"at": n, "predicted": round(pred, 1), "linear": round(g * n, 1),
                    "predicted_low": round(min(loo + [pred]), 1), "predicted_high": round(max(loo + [pred]), 1)})
        if n > 4 * max_n:
            out["warnings"].append(f"Predicting at {n:g}, more than 4 times the largest measured N ({max_n:g}): treat as an upper bound only.")
        if peak_n and n > peak_n:
            out["warnings"].append(f"{n:g} is past the peak at N = {peak_n:.1f}: adding units there lowers throughput.")
        if "--need" in opt:
            out["need"] = opt["--need"]
            out["meets_need"] = int(out["predicted_low"] >= opt["--need"])
            out["meets_need_at_best"] = int(out["predicted_high"] >= opt["--need"])
    if as_json:
        json.dump(out, sys.stdout, indent=1)
        print()
        return 0

    print(f"One unit: {g:,.1f}/s   contention a = {a:.4f}   coherency b = {b:.6f}   fit R² = {r2:.4f}")
    print("   N   measured     fitted   of linear")
    for n, x in pts:
        print(f"{n:4g} {x:10,.1f} {model(n, g, a, b):10,.1f}   {x / (g * n):7.0%}")
    if peak_n:
        print(f"Peak: {out['peak_throughput']:,.1f}/s at N = {peak_n:.1f}; beyond that, more units give less.")
    else:
        print("No peak in the fit (b is 0): throughput keeps rising, limited to g/a = " + (f"{g / a:,.0f}/s." if a > 1e-9 else "no ceiling the points show."))
    if "at" in out:
        print(f"At N = {out['at']:g}: {out['predicted']:,.1f}/s (between {out['predicted_low']:,.1f} and {out['predicted_high']:,.1f} "
              f"when any one point is left out); linear scaling would give {out['linear']:,.1f}/s.")
        if "need" in out:
            verdict = "meets" if out["meets_need"] else ("may meet (only at the top of the range)" if out["meets_need_at_best"] else "does not meet")
            print(f"Needed: {out['need']:,.1f}/s. The extrapolation {verdict} it.")
    for w in out["warnings"]:
        print("warning:", w)
    return 0


if __name__ == "__main__":
    sys.exit(main())
