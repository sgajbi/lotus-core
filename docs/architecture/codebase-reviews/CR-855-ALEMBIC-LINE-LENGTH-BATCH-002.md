# CR-855: Alembic Line Length Batch 002

Status: Hardened on 2026-06-02.

## Finding

After CR-854, repository-wide Ruff still carried 172 findings. All remaining findings were
`E501` line-length findings concentrated in seven historical Alembic migration hotspot files.

## Change

Ran Ruff formatting against the remaining Alembic hotspot revisions:

1. `bfe95fef89d8_feat_describe_your_schema_change.py`,
2. `d0e1f2a3b4c5_feat_add_rfc062_reference_data_contract_tables.py`,
3. `d9e2b3a0c1f4_feat_add_epoch_and_watermark_model.py`,
4. `e0f1a2b3c4d5_feat_add_pipeline_stage_state_table.py`,
5. `e1f2a3b4c6d7_feat_add_analytics_export_jobs_table.py`,
6. `e3f4a5b6c7d8_feat_add_simulation_sessions_and_changes_tables.py`,
7. `f9b0c1d2e3f4_feat_add_financial_reconciliation_control_tables.py`.

Repository-wide Ruff is now clean under `python -m ruff check . --statistics`.

## Boundary Preserved

This change does not alter:

1. Alembic revision IDs,
2. down revisions or branch labels,
3. upgrade or downgrade operations,
4. generated SQL semantics,
5. runtime service behavior,
6. API contracts or database schema.

## Wiki Decision

No repo-local `wiki/` source update is included. This is migration-source formatting with no
operator-facing behavior change.

## Validation

Local validation passed for the slice:

1. scoped `python -m ruff check <batch> --select E501`,
2. `python -m ruff check . --statistics`,
3. `python -m py_compile <batch>`,
4. `python -m alembic heads`,
5. migration SQL contract smoke,
6. `git diff --check`.
