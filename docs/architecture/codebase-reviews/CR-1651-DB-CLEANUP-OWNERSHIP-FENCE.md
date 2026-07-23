# CR-1651: Database Cleanup Ownership Fence

## Objective

Prevent DB-direct pytest cleanup from mutating any PostgreSQL target unless the current test
process generated the Compose project, dynamically reserved the PostgreSQL host port, and connected
the SQLAlchemy engine to that exact prepared target.

GitHub issue: [#824](https://github.com/sgajbi/lotus-core/issues/824).

## Finding

The root pytest harness prepares collision-resistant runtime identities, but
`prepare_test_runtime(..., preserve_existing=True)` intentionally preserves inherited project and
port values. Both `clean_db` fixtures then reached broad recovery, session termination, or
`TRUNCATE ... RESTART IDENTITY CASCADE` without proving that the connected engine belonged to the
runtime prepared by the current process.

The module-scoped path was the earliest destructive boundary. After a quiescence timeout it could
update replay jobs and position state and delete instrument replay state before truncation.
Authorizing only the truncate statement would therefore leave a destructive bypass.

## Change

1. `PreparedTestRuntime` now retains immutable provenance for:
   - current-process preparation;
   - generated rather than inherited Compose project identity;
   - a PostgreSQL host port dynamically reserved by this runtime.
2. `DatabaseCleanupAuthorization` compares the actual SQLAlchemy engine with the exact prepared
   user, host, port, and database. Diagnostics omit passwords.
3. Function- and module-scoped cleanup obtain authorization at fixture entry, before quiescence
   recovery, `pg_terminate_backend`, or truncate SQL.
4. Replay-only cleanup recovery requires and revalidates the same authorization, so a direct helper
   call or different engine cannot bypass the fixture fence.
5. Inherited app-local, shared, test-shaped, fixed-port, mixed-provenance, and drifted-engine
   targets fail before any SQL. Generated-project, process-reserved-port, exact-engine function,
   module, and recovery paths remain supported.

## Same-Pattern Scan

Repository-wide searches for `TRUNCATE TABLE`, `pg_terminate_backend`,
`recover_reprocessing_activity_for_test_cleanup`, and `truncate_with_deadlock_retry` found one
broad pytest cleanup owner: `tests/conftest.py`. Its recovery helper is now capability-bound.

The canonical front-office seed has separately scoped managed-runtime and portfolio cleanup with
explicit project ownership and bounded identity-prefixed deletion. It is not the inherited
DB-direct fixture pattern and remains unchanged. The retry primitive remains non-authoritative; it
does not decide whether a target is safe.

## Validation

- `python -m pytest tests/unit/test_support/test_runtime_env.py
  tests/unit/test_support/test_db_cleanup.py
  tests/unit/test_support/test_pipeline_quiescence.py -q -W error`
  - `32 passed`
- `python -m pytest tests/unit/test_support -q -W error`
  - `106 passed`
- Pinned Ruff check and format verification passed for all changed Python files.
- Strict scoped MyPy passed for `runtime_env.py`, `db_cleanup.py`, and
  `pipeline_quiescence.py`.
- Documentation, diff-hygiene, and broader repository-native checks are recorded with the delivery
  commit.

## Compatibility And Documentation Decision

This is a test-infrastructure safety change. It does not change production schema, migrations,
API/OpenAPI, events, financial calculations, runtime topology, or Docker resources. Protected
DB-direct lanes retain their generated project and dynamic port behavior. Generic inherited or
fixed target overrides can no longer authorize destructive cleanup.

Repository context and this review record change because the test-runtime contract changed.
No README or wiki source changes are required: the supported repository-native commands are
unchanged, and no product or operator runtime behavior changed.
