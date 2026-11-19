#!/usr/bin/env python3
"""Generate a deterministic matchmaking analytics fixture and openable report."""
import argparse
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ANALYTICS = HERE.parents[1] / ".claude/skills/design-bench/scripts/analytics.py"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records", type=int, default=1_000_000)
    parser.add_argument("--output", type=Path, default=HERE / "analytics/synthetic")
    args = parser.parse_args()
    if args.records <= 0:
        parser.error("--records must be positive")
    try:
        import duckdb
    except ImportError:
        parser.error("install the offline DuckDB Python package (duckdb>=1.4,<2)")
    output = args.output.resolve()
    if output.exists():
        parser.error(f"choose a new output directory: {output}")
    results = output / "results"
    run = results / "steady/synthetic"
    raw = run / "raw"
    raw.mkdir(parents=True)
    (run / "k6.json").write_text(json.dumps({"expected_attempts": args.records, "metrics": {}}))
    (run / "metrics.json").write_text("{}")
    with duckdb.connect() as db:
        db.execute("SET VARIABLE record_count = ?", [args.records])
        db.execute("""CREATE TEMP VIEW attempts AS
            SELECT i, 1700000000000 + i * 1000 // 1333 AS sent_ms,
                   i % 100 + 1 AS latency_ms,
                   CASE WHEN i % 2 = 0 THEN 'eu' ELSE 'us' END AS region,
                   CASE WHEN i % 3 = 0 THEN 'duel' ELSE 'siege' END AS mode
            FROM range(getvariable('record_count')) AS records(i)""")
        db.execute("""COPY (
            SELECT 'Point' AS type, 'bench_attempt_ms' AS metric, {
                'time': epoch_ms(sent_ms + latency_ms), 'value': latency_ms,
                'tags': {'scenario':'measure'},
                'metadata': {'bench_request_id': i::VARCHAR, 'bench_ticket_id': i::VARCHAR,
                             'bench_sent_ms': sent_ms::VARCHAR,
                             'bench_observed_ms': (sent_ms + latency_ms)::VARCHAR,
                             'bench_status': '200', 'bench_region': region, 'bench_mode': mode}
            } AS data FROM attempts ORDER BY i
        ) TO ? (FORMAT JSON)""", [str(raw / "k6.k6.jsonl")])
        db.execute("""COPY (
            SELECT i::VARCHAR AS ticket_id, CASE WHEN i % 100 < 95 THEN 'matched' ELSE 'expired' END AS outcome,
                   sent_ms + latency_ms + CASE WHEN i % 100 < 95 THEN 5000 ELSE 300000 END AS observed_ms
            FROM attempts WHERE i % 100 <> 99 ORDER BY i
        ) TO ? (FORMAT CSV, HEADER)""", [str(raw / "tickets.csv")])
    subprocess.run([sys.executable, ANALYTICS, results, output / "dashboard.html",
                    "--archive-dir", output / "parquet"], check=True)


if __name__ == "__main__":
    main()
