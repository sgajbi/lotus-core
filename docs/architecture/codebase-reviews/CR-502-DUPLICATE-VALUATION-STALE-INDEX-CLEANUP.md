# CR-502: Duplicate Valuation Stale Index Cleanup

Date: 2026-05-28

## Scope

`portfolio_valuation_jobs` stale-processing scan index hygiene.

## Finding

The live migration chain still included legacy index
`idx_portfolio_valuation_jobs_processing_updated_at` on
`portfolio_valuation_jobs(status, updated_at)`. The canonical model-declared index
`ix_portfolio_valuation_jobs_status_updated_at` covers the same key shape.

Keeping both indexes adds maintenance cost to valuation job inserts and status transitions without
adding a distinct query path.

## Change

Added Alembic migration `c0d8e9f0a1b2_perf_drop_duplicate_valuation_stale_index.py` to drop the
legacy duplicate while retaining the canonical model-declared index. The downgrade recreates the
legacy index for reversibility.

## Evidence

Commands:

1. `python -m alembic heads`
2. `python scripts/migration_contract_check.py --mode alembic-sql`
3. `python -m ruff check alembic/versions/c0d8e9f0a1b2_perf_drop_duplicate_valuation_stale_index.py`
4. `python -m ruff format --check alembic/versions/c0d8e9f0a1b2_perf_drop_duplicate_valuation_stale_index.py`
5. `git diff --check`

Results:

1. Alembic head proof: `c0d8e9f0a1b2 (head)`
2. Migration contract smoke: passed
3. Touched-surface ruff: passed
4. Touched-surface format check: passed
5. Whitespace check: passed

## Closure

Status: Hardened.

No API route shape, wiki source, or platform contract change was required. The valuation job table
now keeps one canonical status/updated-at index for stale-processing and operations scans.
