#!/usr/bin/env python3
"""Build a local dashboard and Parquet archives from completed design-bench runs."""
import argparse
import json
import sys
from pathlib import Path

TEMPLATE = Path(__file__).resolve().parent.parent / "templates/analytics.html"
K6_SCHEMA = """{type: 'VARCHAR', metric: 'VARCHAR',
    data: 'STRUCT(time TIMESTAMPTZ, value DOUBLE, tags MAP(VARCHAR,VARCHAR), metadata MAP(VARCHAR,VARCHAR))'}"""


def rows(db, sql, args=()):
    query = db.execute(sql, args)
    columns = [definition[0] for definition in query.description]
    return [dict(zip(columns, row)) for row in query.fetchall()]


def archive(db, table, path):
    temporary = path.with_suffix(".tmp")
    db.execute(f"COPY {table} TO ? (FORMAT PARQUET, COMPRESSION ZSTD)", [str(temporary)])
    temporary.replace(path)


def expected_count(summary_path):
    if not summary_path.is_file():
        return None
    summary = json.loads(summary_path.read_text())
    if "expected_attempts" in summary:
        return summary["expected_attempts"]
    metrics = summary["metrics"]
    counts = [data["values"]["count"] for name, data in metrics.items()
              if name == "iterations" or name.startswith("step_") and name.endswith(".iterations")]
    return sum(counts) if counts else None


def summaries(metrics):
    return {key: value for key, value in metrics.items()
            if ".http_req_duration." in key or ".http_req_failed." in key or key.endswith(".iterations.count")}


def ingest(db, captures, run_dir, output):
    db.execute("""CREATE OR REPLACE TEMP TABLE points (
        source VARCHAR, metric VARCHAR, t BIGINT, value DOUBLE,
        tags MAP(VARCHAR,VARCHAR), metadata MAP(VARCHAR,VARCHAR))""")
    coverage = []
    for capture in captures:
        source = capture.name.removesuffix(".k6.jsonl")
        db.execute(f"""INSERT INTO points
            SELECT ?, metric, epoch_ms(data.time), data.value, data.tags, data.metadata
            FROM read_json(?, format='newline_delimited', columns={K6_SCHEMA})
            WHERE type = 'Point'""", [source, str(capture)])
        expected = expected_count(run_dir / f"{source}.json")
        count, duration_points = db.execute("""SELECT
            count(*) FILTER (WHERE metric='bench_attempt_ms'),
            count(*) FILTER (WHERE metric='http_req_duration')
            FROM points WHERE source=? AND tags['scenario'] <> 'warmup'""", [source]).fetchone()
        coverage.append({"source": source, "expected": expected, "attempts": count, "http": duration_points})
    archive(db, "points", output / "k6.parquet")
    return coverage


def load_attempts(db):
    db.execute("""CREATE OR REPLACE TEMP TABLE attempts AS
        WITH attempts AS (
            SELECT source, tags['scenario'] AS phase,
                   metadata['bench_request_id'] AS request_id,
                   nullif(metadata['bench_ticket_id'], '') AS ticket_id,
                   coalesce(try_cast(metadata['bench_scheduled_ms'] AS BIGINT),
                            try_cast(metadata['bench_sent_ms'] AS BIGINT), t) AS offered_ms,
                   coalesce(try_cast(metadata['bench_sent_ms'] AS BIGINT), t) AS sent_ms,
                   coalesce(try_cast(metadata['bench_observed_ms'] AS BIGINT), t) AS observed_ms,
                   value AS latency_ms,
                   try_cast(metadata['bench_status'] AS INTEGER) AS status,
                   coalesce(nullif(metadata['bench_region'], ''), 'Unknown') AS region,
                   coalesce(nullif(metadata['bench_mode'], ''), 'Unknown') AS mode,
                   try_cast(metadata['bench_party_size'] AS INTEGER) AS party_size,
                   try_cast(metadata['bench_attempt_no'] AS INTEGER) AS attempt_no
            FROM points WHERE metric='bench_attempt_ms' AND tags['scenario'] <> 'warmup'
        ) SELECT *, status BETWEEN 200 AND 299 AS accepted FROM attempts""")
    # Keep request IDs for joins and reject duplicates in coverage without joining large raw metric tables.
    return db.execute("""SELECT count(*), count(*) - count(DISTINCT (source, request_id)),
                               count(*) FILTER (WHERE request_id IS NULL OR status IS NULL OR latency_ms < 0)
                        FROM attempts""").fetchone()


def attempt_stats(db, origin, bucket):
    stats = """count(*) AS n, count(*) FILTER (WHERE accepted) AS accepted,
               count(*) FILTER (WHERE accepted AND latency_ms <= 200) AS accepted_200ms,
               round(avg(latency_ms), 3) AS mean_ms,
               round(quantile_cont(latency_ms, .50), 3) AS p50_ms,
               round(quantile_cont(latency_ms, .95), 3) AS p95_ms,
               round(quantile_cont(latency_ms, .99), 3) AS p99_ms"""
    groups = rows(db, f"""SELECT source, phase, region, mode, {stats}
        FROM attempts GROUP BY source,phase,GROUPING SETS ((region,mode),(region),(mode),())
        ORDER BY source,phase,region NULLS FIRST,mode NULLS FIRST""")
    timeline = rows(db, f"""WITH binned AS (
        SELECT *, floor((offered_ms - ?) / ?)::BIGINT AS bucket FROM attempts
        ) SELECT source, phase, region, mode, bucket, {stats}
        FROM binned GROUP BY source,phase,bucket,GROUPING SETS ((region,mode),(region),(mode),())
        ORDER BY bucket""", [origin, bucket])
    return groups, timeline


def drop_stats(db, origin, bucket):
    return rows(db, """SELECT source, tags['scenario'] AS phase,
        floor((t - ?) / ?)::BIGINT AS bucket, sum(value)::BIGINT AS dropped
        FROM points WHERE metric='dropped_iterations' AND tags['scenario'] <> 'warmup'
        GROUP BY ALL ORDER BY bucket""", [origin, bucket])


def ticket_stats(db, path, output, origin, bucket):
    # Join from accepted tickets so absent outcomes remain visible in the denominator.
    db.execute("""CREATE OR REPLACE TEMP TABLE outcomes (
                   ticket_id VARCHAR, outcome VARCHAR, observed_ms BIGINT)""")
    duplicate_outcomes = 0
    if path.is_file():
        db.execute("""INSERT INTO outcomes SELECT ticket_id, outcome, observed_ms FROM read_csv(?,
                header=true, columns={ticket_id:'VARCHAR', outcome:'VARCHAR', observed_ms:'BIGINT'})""",
                   [str(path)])
        invalid = db.execute("""SELECT count(*) FROM outcomes WHERE
            ticket_id IS NULL OR observed_ms IS NULL OR outcome IS NULL
            OR outcome NOT IN ('matched', 'expired', 'cancelled', 'unresolved')""").fetchone()[0]
        if invalid:
            raise ValueError(f"{path}: {invalid} invalid ticket outcomes")
        duplicate_outcomes = db.execute("SELECT count(*) - count(DISTINCT ticket_id) FROM outcomes").fetchone()[0]
    db.execute("""CREATE OR REPLACE TEMP TABLE tickets AS
        WITH accepted AS (
            SELECT DISTINCT ON (ticket_id) ticket_id, source, phase, region, mode, party_size, observed_ms AS accepted_ms
            FROM attempts WHERE accepted AND ticket_id IS NOT NULL
            ORDER BY ticket_id, observed_ms, request_id
        ), terminal AS (
            SELECT DISTINCT ON (ticket_id) * FROM outcomes ORDER BY ticket_id, observed_ms, outcome
        )
        SELECT accepted.*, coalesce(terminal.outcome,'unresolved') AS outcome,
               terminal.observed_ms, terminal.observed_ms - accepted_ms AS wait_ms
        FROM accepted LEFT JOIN terminal USING (ticket_id)""")
    unmatched, too_early = db.execute("""SELECT
        (SELECT count(DISTINCT ticket_id) FROM outcomes WHERE ticket_id NOT IN (SELECT ticket_id FROM tickets)),
        (SELECT count(*) FROM tickets WHERE wait_ms < 0)""").fetchone()
    archive(db, "tickets", output / "tickets.parquet")
    stats = """count(*) AS tickets,
               count(*) FILTER (WHERE outcome='matched' AND wait_ms>=0) AS matched,
               count(*) FILTER (WHERE outcome='expired') AS expired,
               count(*) FILTER (WHERE outcome='cancelled') AS cancelled,
               count(*) FILTER (WHERE outcome='unresolved' OR wait_ms<0) AS unresolved,
               count(*) FILTER (WHERE outcome='matched' AND wait_ms BETWEEN 0 AND 10000) AS matched_10s,
               count(*) FILTER (WHERE outcome='matched' AND wait_ms BETWEEN 0 AND 60000) AS matched_60s,
               round(avg(wait_ms) FILTER (WHERE outcome='matched' AND wait_ms>=0), 3) AS mean_ms,
               round(quantile_cont(wait_ms, .95) FILTER (WHERE outcome='matched' AND wait_ms>=0), 3) AS p95_ms,
               round(quantile_cont(wait_ms, .99) FILTER (WHERE outcome='matched' AND wait_ms>=0), 3) AS p99_ms"""
    grouped = rows(db, f"""SELECT source,phase,region,mode,{stats}
        FROM tickets GROUP BY source,phase,GROUPING SETS ((region,mode),(region),(mode),())""")
    timeline = rows(db, f"""WITH binned AS (
        SELECT *, floor((accepted_ms - ?) / ?)::BIGINT AS bucket FROM tickets
        ) SELECT source,phase,region,mode,bucket,{stats}
        FROM binned GROUP BY source,phase,bucket,GROUPING SETS ((region,mode),(region),(mode),())
        ORDER BY bucket""", [origin, bucket])
    return {"groups": grouped, "timeline": timeline, "outcomes_present": path.is_file(),
            "duplicate_outcomes": duplicate_outcomes, "unmatched_outcomes": unmatched, "early_outcomes": too_early}


def resource_series(path, origin, bucket):
    if not path.is_file():
        return []
    previous, series = {}, {}
    with path.open() as samples:
        for line in samples:
            sample = json.loads(line)
            name, timestamp = sample["unit"], sample["t"]
            old = previous.get(name)
            previous[name] = sample
            if old is None or timestamp <= old["t"] or sample.get("id") != old.get("id"):
                continue
            elapsed = (timestamp - old["t"]) / 1000
            if name == "host":
                total = sample["cpu_total"] - old["cpu_total"]
                fields = {"Host CPU busy (%)": 100 * (1 - (sample["cpu_idle"] - old["cpu_idle"]) / total)} if total else {}
            else:
                cores = (sample["cpu_usec"] - old["cpu_usec"]) / (elapsed * 1e6)
                fields = {f"{name} CPU (cores)": cores, f"{name} RAM (MiB)": sample["mem"] / 1048576,
                          f"{name} write (MiB/s)": (sample["wbytes"] - old["wbytes"]) / elapsed / 1048576}
                if sample["cpu_limit"]:
                    fields[f"{name} CPU (% of limit)"] = 100 * cores / sample["cpu_limit"]
            fields[f"{name} I/O pressure (%)"] = (sample["psi_io"] - old["psi_io"]) / (elapsed * 10000)
            fields[f"{name} CPU pressure (%)"] = (sample["psi_cpu"] - old["psi_cpu"]) / (elapsed * 10000)
            elapsed_bucket = (timestamp - origin) // bucket * bucket / 1000
            for label, value in fields.items():
                points = series.setdefault(label, {})
                points[elapsed_bucket] = round(max(value, points.get(elapsed_bucket, value)), 3)
    return [{"label": label, "points": sorted(points.items())} for label, points in sorted(series.items())]


def analyze(db, run_dir, archive_root, bucket, input_errors):
    scenario, name = run_dir.parent.name, run_dir.name
    metrics_path = run_dir / "metrics.json"
    metrics = json.loads(metrics_path.read_text()) if metrics_path.is_file() else {}
    window_path = run_dir / "window.json"
    window = json.loads(window_path.read_text()) if window_path.is_file() else {}
    captures = sorted((run_dir / "raw").glob("*.k6.jsonl"))
    partial = sorted(path.name for path in (run_dir / "raw").glob("*.partial"))
    output = archive_root / scenario / name
    report = {"scenario": scenario, "run": name, "finished": metrics_path.is_file(),
              "metrics": summaries(metrics), "coverage": [], "partial": partial}
    source_path = run_dir / "source.json"
    if source_path.is_file():
        source = json.loads(source_path.read_text())
        report["source"] = {key: source[key] for key in ("commit", "dirty_sources", "sampler_cpus_requested")}
    origin = window.get("from_ms")
    try:
        output.mkdir(parents=True, exist_ok=True)
        if captures:
            report["coverage"] = ingest(db, captures, run_dir, output)
    except input_errors as error:
        print(f"{run_dir}: raw capture could not be read: {error}", file=sys.stderr)
        report["capture_error"] = True
    else:
        if captures:
            origin, bucket = analyze_attempts(db, run_dir, output, report, origin, bucket, input_errors)
    samples = run_dir / "samples.jsonl"
    if origin is None and samples.is_file():
        with samples.open() as stream:
            first_line = stream.readline()
            origin = json.loads(first_line)["t"] if first_line else None
    report["resources"] = resource_series(samples, origin, bucket) if origin is not None else []
    if samples.is_file() and samples.stat().st_size:
        output.mkdir(parents=True, exist_ok=True)
        db.execute("CREATE OR REPLACE TEMP TABLE resources AS SELECT * FROM read_json_auto(?)", [str(samples)])
        archive(db, "resources", output / "resources.parquet")
    if (run_dir / "raw/sink.csv").is_file():
        output.mkdir(parents=True, exist_ok=True)
        db.execute("""CREATE OR REPLACE TEMP TABLE arrivals AS SELECT * FROM read_csv(?, header=true,
            columns={arrived_ms:'BIGINT', due_ms:'BIGINT', key:'VARCHAR', class:'VARCHAR', outcome:'VARCHAR'})""",
            [str(run_dir / "raw/sink.csv")])
        archive(db, "arrivals", output / "sink.parquet")
    report["bucket_seconds"] = bucket / 1000
    return report


def analyze_attempts(db, run_dir, output, report, origin, bucket, input_errors):
    count, duplicates, invalid = load_attempts(db)
    report.update(attempt_count=count, duplicate_attempts=duplicates, invalid_attempts=invalid)
    first, last = db.execute("SELECT min(offered_ms),max(observed_ms) FROM attempts").fetchone()
    if first is None:
        first, last = db.execute("SELECT min(t),max(t) FROM points").fetchone()
    origin = first if origin is None else origin
    if origin is not None and last is not None:
        bucket = max(bucket, ((last - origin) // 240000 + 1) * 1000)
    if count:
        archive(db, "attempts", output / "attempts.parquet")
        report["groups"], report["timeline"] = attempt_stats(db, origin, bucket)
        report["drops"] = drop_stats(db, origin, bucket)
        try:
            report["tickets"] = ticket_stats(db, run_dir / "raw/tickets.csv", output, origin, bucket)
        except input_errors as error:
            print(f"{run_dir}: ticket outcomes could not be read: {error}", file=sys.stderr)
            report["ticket_error"] = True
    return origin, bucket


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results", type=Path)
    parser.add_argument("dashboard", type=Path)
    parser.add_argument("--archive-dir", type=Path)
    parser.add_argument("--bucket-seconds", type=int, default=10)
    args = parser.parse_args()
    if args.bucket_seconds < 1 or not args.results.is_dir():
        parser.error("provide a results directory and a positive bucket width")
    try:
        import duckdb
    except ImportError:
        parser.error("install the offline DuckDB Python package in an isolated environment (duckdb>=1.4,<2)")
    archive_dir = args.archive_dir or args.results.parent / "analytics"
    archive_dir.mkdir(parents=True, exist_ok=True)
    with duckdb.connect() as db:
        db.execute("SET memory_limit='1GB'")
        db.execute("SET temp_directory=?", [str(archive_dir / "_spill")])
        input_errors = (duckdb.Error, ValueError)
        runs = [analyze(db, path, archive_dir, args.bucket_seconds * 1000, input_errors)
                for path in sorted(args.results.glob("*/*")) if path.is_dir()]
    args.dashboard.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(runs, separators=(",", ":"), allow_nan=False).replace("<", "\\u003c")
    temporary = args.dashboard.with_suffix(".tmp")
    temporary.write_text(TEMPLATE.read_text().replace("<!--DATA-->", payload))
    temporary.replace(args.dashboard)
    print(f"wrote {args.dashboard} for {len(runs)} run(s). Parquet archives in {archive_dir}")


if __name__ == "__main__":
    main()
