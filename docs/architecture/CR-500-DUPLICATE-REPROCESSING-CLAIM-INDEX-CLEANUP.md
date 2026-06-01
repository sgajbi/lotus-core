# CR-500: Duplicate Reprocessing Claim Index Cleanup

Date: 2026-05-28

## Scope

`reprocessing_jobs` claim-path index hygiene.

## Finding

The live migration chain created legacy index `idx_reprocessing_jobs_claim_order` on
`reprocessing_jobs(job_type, status, created_at, id)`. A later platform-aligned index,
`ix_reprocessing_jobs_job_type_status_created_at_id`, declared the same key shape in SQLAlchemy model
metadata and migration history.

Keeping both indexes does not improve the claim or operations query plan, but it does add index write
maintenance overhead for every reprocessing job insert and status transition.

## Change

Added Alembic migration `c0d6e7f8a9b0_perf_drop_duplicate_reprocessing_claim_index.py` to drop the
legacy `idx_reprocessing_jobs_claim_order` index while keeping the canonical model-declared
`ix_reprocessing_jobs_job_type_status_created_at_id` index.

The downgrade recreates the legacy index to preserve migration reversibility.

## Evidence

Commands:

1. `python -m alembic heads`
2. `python scripts/migration_contract_check.py --mode alembic-sql`
3. `python -m ruff check alembic/versions/c0d6e7f8a9b0_perf_drop_duplicate_reprocessing_claim_index.py`
4. `python -m ruff format --check alembic/versions/c0d6e7f8a9b0_perf_drop_duplicate_reprocessing_claim_index.py`

Results:

1. Alembic head proof: `c0d6e7f8a9b0 (head)`
2. Migration contract smoke: passed
3. Touched-surface ruff: passed
4. Touched-surface format check: passed

## Closure

Status: Hardened.

No API route shape, wiki source, or platform contract change was required. The `reprocessing_jobs`
claim path now keeps one canonical composite index for the job-type/status/created-at/id access path.
