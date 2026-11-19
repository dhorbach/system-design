# Critical-path benchmark tests

Write both suites before calibration. Keep them beside the prototype in
`bench/<slug>/tests/` and commit them with the bench source.

- **Unit tests** run the local decisions behind each claim. Exercise success,
  boundary values, rejected inputs and failure branches. Use an injected clock
  for time-sensitive logic and deterministic seeds for generated inputs.
- **Storage integration tests** invoke the prototype's real code and migrations
  against the store or broker used by the bench. Assert the persisted state and
  return value, including behavior after commit, retry and rollback. Where the
  design depends on idempotency, fencing, leases or atomic ownership, exercise
  competing operations and verify the invariant using a separate connection.
  Use the same durability and isolation settings that the claim depends on.
- **Performance scenarios** still check capacity, injected faults and recovery
  under load. A passing test suite establishes the prototype behavior needed to
  interpret those measurements.

## Files and command

1. Write `tests/unit.sh` as a shell entry point for the bench's normal unit test
   commands. Make it fail if no tests run or if a required test is skipped.
2. Write `tests/compose.yaml` with an `integration` service that exits nonzero
   on test failure. Give each store its bench service name, image or build,
   startup command and settings, with a healthy readiness probe. Use the same
   migrations and application source. Store data in project-named test volumes
   and have the runner connect over the test network. Use project volumes or
   read-only local source/fixtures for mounts. The suite should fail if its
   store, migrations or required tests are unavailable.
3. Write `tests/contract.json` to make the critical-path coverage reviewable.
   List every storage engine the prototype uses, or set `stores` to `[]`
   and add a `storage_free_reason` for a genuinely storage-free design.
   Critical-path entries point to source under the bench and name the cases
   the two suites execute. Review coverage against the plan and claims when
   adding a path. The harness checks the mapping and executable results.

```json
{
  "stores": ["store"],
  "critical_paths": [
    {
      "source": "api/join.go",
      "unit": ["TestJoinRejectsInvalidParty"],
      "integration": ["TestConcurrentJoinsCreateOneTicket", "TestFailedJoinRollsBack"]
    }
  ]
}
```

Run `./run.sh test` from the bench directory. It runs the unit suite, checks the
Compose topology, creates a unique `bench-<slug>-tests-<id>` project for the
integration suite and removes that project's volumes and network afterward.
The runner holds a per-design lock during tests and scenarios. Run suites
outside measured windows for other designs too. Logs go into the relevant project
directory under `test-results/`. Commit `test-results/latest.json` after it
records a pass. Each scenario copies the applicable pass record into its own
result directory. Changes to the bench's source inputs invalidate the pass.

The shared PostgreSQL fixture can be replayed with `make test-bench-integration`
on a host with approved Docker access. Its queue write is test fixture code.
