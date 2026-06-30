# CR-1182 Reconciliation Runtime Provider Ports

## Objective

Begin GitHub issue #655 by replacing direct runtime time and UUID calls in a representative
financial reconciliation workflow with deterministic provider ports.

## Expected Improvement

- `ReconciliationService` no longer imports `perf_counter` or `uuid4`.
- Elapsed-duration metrics and generated reconciliation finding IDs are deterministic under tests.
- Runtime providers isolate system monotonic time and UUID generation.
- `make architecture-guard` blocks direct `time` and `uuid` imports in
  `reconciliation_service.py`.

## Changes

- Added `runtime_providers.py` with `MonotonicTimer`, `IdGenerator`, `SystemMonotonicTimer`, and
  `UuidHexIdGenerator`.
- Injected `monotonic_timer` and `id_generator` into `ReconciliationService`.
- Routed transaction-cashflow, position-valuation, and timeseries-integrity elapsed-duration
  measurement through the timer provider.
- Routed reconciliation finding IDs through the ID provider.
- Added deterministic unit coverage for generated finding IDs and observed elapsed seconds without
  monkeypatching global functions.
- Added architecture-boundary guard coverage for the old direct imports.
- Added `runtime-provider-port-policy.md` documenting allowed direct runtime calls and provider-port
  expectations.

## Compatibility

No API route, response DTO, database schema, reconciliation type, finding shape, summary shape,
metric name, metric labels, repository contract, or downstream consumer behavior changed. Runtime
defaults still use `perf_counter()` and `uuid4().hex` through adapters.

## Validation

- `python -m pytest tests/unit/services/financial_reconciliation_service/test_reconciliation_service.py tests/unit/scripts/test_architecture_boundary_guard.py -q`
- `make architecture-guard`
- `make quality-import-boundary-gate`
- `python -m ruff check src/services/financial_reconciliation_service/app/services/runtime_providers.py src/services/financial_reconciliation_service/app/services/reconciliation_service.py scripts/architecture_boundary_guard.py tests/unit/services/financial_reconciliation_service/test_reconciliation_service.py tests/unit/scripts/test_architecture_boundary_guard.py`
- `python -m ruff format --check src/services/financial_reconciliation_service/app/services/runtime_providers.py src/services/financial_reconciliation_service/app/services/reconciliation_service.py scripts/architecture_boundary_guard.py tests/unit/services/financial_reconciliation_service/test_reconciliation_service.py tests/unit/scripts/test_architecture_boundary_guard.py`
- `git diff --check`

## Documentation And Wiki Decision

Updated this CR evidence note, `runtime-provider-port-policy.md`, the codebase review ledger, and
quality scorecard/health report because provider-port architecture policy changed. No wiki source
update is required because no supported operator workflow or public API contract changed.

## Follow-Up

Issue #655 remains open for representative snapshot/simulation workflows, wall-clock `Clock`
providers, broader static guard coverage, and eventual shared provider ports where multiple Lotus
Core services converge on the same interfaces.
