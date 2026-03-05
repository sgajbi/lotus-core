# INTEREST Slice 5 - Query and Observability Supportability

## Scope

Slice 5 extends existing query surfaces to expose INTEREST semantic and linkage evidence without adding transaction-specific endpoints.

## Delivered Artifacts

- `src/libs/portfolio-common/portfolio_common/database_models.py`
  - `transactions` columns:
    - `interest_direction`
    - `withholding_tax_amount`
    - `other_interest_deductions_amount`
    - `net_interest_amount`
- `alembic/versions/d6e7f8a9b0c1_feat_add_interest_transaction_semantic_fields.py`
  - schema migration for the above fields
- `src/libs/portfolio-common/portfolio_common/events.py`
  - transaction event fields for INTEREST semantics
- `src/services/ingestion_service/app/DTOs/transaction_dto.py`
  - ingestion contract fields for INTEREST semantics
- `src/services/query_service/app/dtos/transaction_dto.py`
  - transaction response DTO fields for INTEREST semantic visibility
- Query/integration coverage:
  - `tests/integration/services/query_service/test_transactions_router.py`
  - `tests/unit/services/query_service/services/test_transaction_service.py`
- Persistence coverage update:
  - `tests/integration/services/persistence_service/repositories/test_repositories.py`

## Query Contract Behavior

`/portfolios/{portfolio_id}/transactions` now surfaces INTEREST-specific semantic fields through existing transaction DTOs:

- `interest_direction`
- `withholding_tax_amount`
- `other_interest_deductions_amount`
- `net_interest_amount`

No dedicated INTEREST endpoint was introduced.

## Observability and Audit Value

The transaction read model now exposes the complete linkage and semantic decomposition needed for:

- operational diagnostics
- reconciliation support
- tax/withholding visibility
- economic-event linkage tracing

## Shared-Doc Conformance Note (Slice 5)

Validated shared standards for this slice:

- `shared/10-query-audit-and-observability.md`: query outputs now include required INTEREST supportability fields.
- `shared/07-accounting-cash-and-linkage.md`: linkage + cash-entry mode + semantic decomposition fields are query-visible.
- `shared/12-canonical-modeling-guidelines.md`: canonical field names are propagated consistently across ingestion/event/storage/query layers.
- `shared/11-test-strategy-and-gap-assessment.md`: integration and unit tests validate query-path propagation.

## Residual Gaps (Expected for Later Slices)

- dedicated conformance suite wiring and closure report are Slice 6.
