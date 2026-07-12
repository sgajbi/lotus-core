# CR-652: Realized Tax Evidence Timestamp Reuse

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

`PortfolioRealizedTaxSummary:v1` loaded all explicit tax-evidence transaction rows for aggregation
and then issued a second tax-evidence-scoped `max(updated_at)` query over the same sparse predicate
to populate runtime metadata. The source transaction count query has different semantics and must
remain, but the timestamp scan duplicated work already present in the loaded evidence rows.

## Change

Derived `latest_evidence_timestamp` from the loaded explicit tax-evidence rows, removed the
now-redundant repository timestamp query, and updated the methodology to state that the timestamp is
based on filtered explicit tax evidence.

## Impact

This removes one database round trip from realized-tax summary reads while preserving source-window
counts, explicit tax-evidence aggregation, reporting-currency restatement, empty-evidence behavior,
data-quality posture, response shape, and product identity.

No route shape, database schema, wiki source, or platform contract changed.

## Validation

Local validation passed:

1. `python -m pytest tests/unit/services/query_service/repositories/test_transaction_repository.py tests/unit/services/query_service/services/test_transaction_service.py -q`
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. touched-surface `python -m ruff check`
5. touched-surface `python -m ruff format --check`
6. `git diff --check`
