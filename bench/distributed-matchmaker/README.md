# Distributed matchmaker bench source

The design draft `pages/distributed-matchmaker.html` specifies the join and
ticket-outcome targets. This directory currently holds the source for
replaying the dashboard with synthetic data. The replay checks reporting and
does not run a matchmaking service.

Use the DuckDB Python package (`duckdb>=1.4,<2`) in an isolated environment.
Run from the repository root:

```sh
python3 bench/distributed-matchmaker/replay-analytics.py
```

Open `bench/distributed-matchmaker/analytics/synthetic/dashboard.html`. The
default replay generates one million attempts at 1,333/s, spread across two
regions and two modes. The overall join mean is 50.5 ms and p95 is 95.05 ms.
Of the million accepted tickets, 950,000 match within five seconds, 40,000
expire and 10,000 have no observed outcome. The output also contains the
raw inputs and their Parquet tables. Use `--records` for a smaller replay
or `--output` for a separate output directory.

Keep the eventual prototype, Compose and workload configuration, data
generators and seeds, observer source, claim definitions and rerun commands in
this directory. Commit those files and the small run manifests and summaries.
Use [the analytics instructions](../../.claude/skills/design-bench/reference/analytics.md)
for raw capture, CPU placement and offline analysis.
