# CR-1619: Owner-Direct Package Exports

## Objective

Keep public transaction-processing package imports stable while making each exported contract trace directly to its owning module.

## Finding

The application package re-exported corporate-action evidence values transitively through the coordinator module even though the values are owned by the ports package. The settlement package similarly re-exported its rejection reason code through the cash-movement policy instead of the reason-code module. These indirect aliases obscured ownership and failed strict explicit-export checks.

## Change

- Imported corporate-action evidence values directly from their ports owner in the application package facade.
- Imported `SettlementCashRejectionReasonCode` directly from `settlement.reason_codes` in the settlement package facade.
- Preserved the existing application and settlement public import paths and `__all__` contracts.

## Same-Pattern Review

The full transaction-processing strict check now has no package export findings. No implementation modules were moved because ownership was already correct; only the package facades were pointing through non-owning modules.

## Measurable Improvement

- Unified transaction-processing strict debt reduced from 8 errors in 4 files to 4 errors in 2 files.
- Four transitive export aliases were replaced with owner-direct imports without adding compatibility modules.

## Validation

- `python -m mypy --strict --no-incremental src/services/portfolio_transaction_processing_service/app`
- `python -m pytest -q tests/unit/services/portfolio_transaction_processing_service/application/test_corporate_action_reconciliation_evidence.py tests/unit/services/portfolio_transaction_processing_service/application/test_reconcile_corporate_action_groups.py tests/unit/services/portfolio_transaction_processing_service/domain/transaction/settlement`
- Focused Ruff and repository documentation guards.
- `git diff --check`

## Compatibility And Documentation Decision

Downstream Python import paths, runtime identities, application behavior, settlement calculations, API contracts, persistence, and database structures are unchanged. The implementation now reflects existing ownership more clearly. README, wiki, and repository context do not require changes because capability and architectural ownership truth did not change.

## Follow-Up

Complete #779 by typing the two Kafka consumer boundaries and adding the full-package strict gate.
