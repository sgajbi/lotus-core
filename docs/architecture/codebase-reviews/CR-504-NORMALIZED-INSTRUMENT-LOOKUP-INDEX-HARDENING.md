# CR-504: Normalized Instrument Lookup Index Hardening

Date: 2026-05-29

## Scope

Instrument lookup and valuation backfill joins that use normalized `security_id` predicates.

## Finding

Multiple calculation and query repositories already compare instruments through
`trim(instruments.security_id)` so padded bank identifiers do not break enrichment, valuation, or
source-data lookups. The `instruments` table still only had its raw unique `security_id` index.

That left normalized instrument lookups and joins dependent on expression evaluation rather than a
matching functional index. The valuation backfill scan also still joined instruments to
`position_state` by raw `security_id`, so whitespace drift could skip a key that otherwise had a
valid instrument definition.

## Change

Added SQLAlchemy model index and Alembic migration
`c0e0f1a2b3c4_perf_add_normalized_instrument_lookup_index.py`:

1. `ix_instruments_norm_security_id` on `trim(instruments.security_id)`.

Updated valuation backfill candidate selection to join instruments and position-state keys through
trimmed security identifiers.

## Evidence

Commands:

1. `python -m pytest tests/unit/libs/portfolio-common/test_database_models.py tests/unit/services/calculators/position_valuation_calculator/repositories/test_valuation_repository_worker_metrics.py tests/unit/services/query_service/repositories/test_instrument_repository.py -q`
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. `python -m ruff check src/libs/portfolio-common/portfolio_common/database_models.py src/libs/portfolio-common/portfolio_common/valuation_repository_base.py tests/unit/libs/portfolio-common/test_database_models.py tests/unit/services/calculators/position_valuation_calculator/repositories/test_valuation_repository_worker_metrics.py alembic/versions/c0e0f1a2b3c4_perf_add_normalized_instrument_lookup_index.py`
5. `python -m ruff format --check src/libs/portfolio-common/portfolio_common/database_models.py src/libs/portfolio-common/portfolio_common/valuation_repository_base.py tests/unit/libs/portfolio-common/test_database_models.py tests/unit/services/calculators/position_valuation_calculator/repositories/test_valuation_repository_worker_metrics.py alembic/versions/c0e0f1a2b3c4_perf_add_normalized_instrument_lookup_index.py`
6. `git diff --check`

Results:

1. Focused model, valuation, and instrument repository proof: `32 passed`
2. Alembic head proof: `c0e0f1a2b3c4 (head)`
3. Migration contract smoke: passed
4. Touched-surface ruff: passed
5. Touched-surface format check: passed
6. Whitespace check: passed

## Closure

Status: Hardened.

No API route shape, wiki source, or platform contract change was required. Instrument lookup now has
functional index support for the normalized security-id predicates already used across calculation
and query paths.
