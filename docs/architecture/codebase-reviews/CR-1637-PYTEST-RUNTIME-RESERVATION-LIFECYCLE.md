# CR-1637: Pytest Runtime Reservation Lifecycle

## Objective

Release every process-owned dynamic test-runtime socket through pytest lifecycle ownership without
weakening the held-port protection used by Docker-backed suites.

## Finding

Root `tests/conftest.py` prepares and exports one collision-resistant runtime during import. That
runtime holds 17 sockets so another process cannot claim the selected host ports before Compose is
ready to bind. The only normal release call was inside the `docker_services` fixture finalizer.
Unit-only sessions never request that fixture, so their sockets remained open until interpreter
finalization and emitted `ResourceWarning: unclosed <socket.socket ...>` after pytest had completed.
Those late warnings occurred outside normal pytest warning accounting, making a green `-W error`
result noisy and incomplete.

The same-pattern scan found one module-level pytest runtime owner. Managed Compose runs and direct
runtime-support tests already release their locally constructed reservations through explicit
`finally` paths. The correction therefore belongs at the root pytest lifecycle boundary rather
than in the reusable reservation object or application runtime.

## Change

- Added one `_release_test_runtime_port_reservation()` lifecycle operation.
- Added `pytest_sessionfinish` ownership so unit-only and collection-only sessions release any
  still-held ports before interpreter finalization.
- Reused the same operation in `docker_services` teardown. `RuntimePortReservation.release()` is
  already idempotent, so Docker fixture finalization followed by session finalization is safe.
- Preserved the existing startup contract: reservations remain held through image build and are
  released immediately before Compose attempts to bind.
- Added focused tests that exercise a unit-only session release and a fully finalized mocked Docker
  fixture followed by the session hook.

## Compatibility

This changes test-harness resource ownership only. It does not start or stop Docker, change Compose
project identity, alter dynamic port selection/reallocation, open a command window, or modify any
application API, OpenAPI schema, event, database, calculation, product, or production runtime
contract.

## Validation

- `16` focused runtime lifecycle, reservation, and service-scope tests passed with warnings promoted
  to errors.
- The original issue reproduction passed `26` unit-only tests with `-W error`, exit code `0`, and
  zero matches for `ResourceWarning` or `unclosed.*socket` in combined process output.
- The repository-native unit collection gate selected `5,047` of `5,059` tests and completed
  without a finalizer warning.
- Scoped pinned Ruff passed for the root fixture and lifecycle tests.
- The source scan found no second module-level pytest runtime owner requiring the same hook.
- Signed implementation commit: `bd9797c9a`.

## Documentation Decision

The operations runbook, repository engineering context, validation wiki source, this review, and
the review ledger change because test-lifecycle truth changed. Application docs, API/OpenAPI,
calculation methodology, migrations, data-product contracts, and supported-feature documentation
remain intentionally unchanged.
