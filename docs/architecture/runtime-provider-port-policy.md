# Runtime Provider Port Policy

## Purpose

Application workflows that create business evidence, audit rows, generated IDs, expiry decisions,
elapsed-duration metrics, or support diagnostics must receive time and ID capabilities through
provider ports. Direct global calls make those workflows harder to test deterministically and hide
runtime dependencies inside business logic.

## Required Pattern

Use explicit provider ports for application and domain workflow code:

- `Clock` or equivalent for wall-clock UTC timestamps and dates.
- `MonotonicTimer` for elapsed-duration measurement.
- `IdGenerator` or `UuidProvider` for generated identifiers.
- A dedicated correlation provider only when a caller has not supplied a governed correlation ID.

Runtime adapters may wrap `datetime.now`, `date.today`, `perf_counter`, and `uuid4`. Tests may use
fixed providers or fakes. Application services should not monkeypatch global time or UUID functions
when a provider can be injected.

## Current Enforced Boundary

CR-1182 applies this policy to `financial_reconciliation_service`:

- `ReconciliationService` receives a `MonotonicTimer` and `IdGenerator`.
- `runtime_providers.py` owns the system `perf_counter` and `uuid4` adapters.
- `make architecture-guard` blocks direct `time` and `uuid` imports in
  `reconciliation_service.py`.

## Allowed Direct Calls

Direct runtime calls remain allowed in:

- provider adapter modules that implement the port,
- framework/bootstrap composition,
- repository infrastructure when a later slice has not yet introduced a port,
- scripts and tests that are not asserting application workflow determinism.

New application services should prefer provider ports from the start.
