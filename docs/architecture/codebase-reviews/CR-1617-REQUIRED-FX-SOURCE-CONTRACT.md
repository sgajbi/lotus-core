# CR-1617: Required FX Source Contract

## Objective

Make the cost engine's canonical FX boundary explicit, statically checkable, and fail closed when a dynamically populated transaction omits required economic fields.

## Finding

`FxTransactionSource` required both the core fields read directly by canonicalization and optional lifecycle/P&L extensions read through tolerant lookup. The legacy cost transaction stores FX attributes dynamically, so static analysis could not prove compatibility and an incomplete record could raise an uncontrolled `AttributeError`.

## Change

- Limited `FxTransactionSource` to the 23 fields required directly by canonical FX economics.
- Made the protocol runtime-checkable and exported it from the FX domain package.
- Added a cost-engine boundary guard that records a deterministic validation error before canonicalization when required fields are absent.
- Added a regression scenario for an incomplete FX forward record.

## Measurable Improvement

- Unified transaction-processing strict MyPy debt reduced from 21 errors in 8 files to 20 errors in 7 files.
- The FX source contract shrank by 68 lines while preserving optional extension ingestion.
- Incomplete dynamic FX records now fail as controlled calculation errors instead of escaping through attribute access.

## Validation

- `python -m mypy --strict --no-incremental src/services/portfolio_transaction_processing_service/app`
- `python -m pytest -q tests/unit/services/portfolio_transaction_processing_service/domain/cost_basis/calculation/test_cost_calculator.py tests/unit/services/portfolio_transaction_processing_service/domain/transaction/fx/test_package_structure.py`
- `python -m ruff check src/services/portfolio_transaction_processing_service/app/domain/transaction/fx src/services/portfolio_transaction_processing_service/app/domain/cost_basis/calculation/cost_basis_calculator.py tests/unit/services/portfolio_transaction_processing_service/domain/cost_basis/calculation/test_cost_calculator.py tests/unit/services/portfolio_transaction_processing_service/domain/transaction/fx/test_package_structure.py`
- `git diff --check`

## Compatibility And Documentation Decision

Canonical FX values, optional metadata propagation, public cost-calculation entry points, persistence contracts, and database structures are unchanged. The only behavior change is intentional fail-closed handling for malformed FX input. No README or wiki change is required because operator-facing capability and invocation truth did not change; this review and the #779 issue evidence record the internal contract correction.

## Follow-Up

Continue #779 with typed infrastructure instrumentation, explicit package exports, Kafka consumer boundaries, and the full-package strict gate.
