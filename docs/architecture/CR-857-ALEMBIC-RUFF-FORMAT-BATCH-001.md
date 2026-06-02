# CR-857: Alembic Ruff Format Batch 001

Status: Hardened on 2026-06-02.

## Finding

After CR-856, Ruff lint was clean and enforced, but full `ruff format --check .` still reported 154
files requiring formatting. Enforcing format at that point would have created an avoidable broad
mechanical churn commit.

## Change

Ran Ruff formatting against the remaining Alembic environment and migration subset reported by the
format baseline:

1. `alembic/env.py`,
2. 14 historical Alembic revision files.

The repository-wide format baseline is down from 154 files to 141 files requiring formatting.

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

1. scoped `python -m ruff format --check <batch>`,
2. `python -m ruff check . --statistics`,
3. `python -m ruff format --check .` baseline measurement,
4. `python -m py_compile <batch>`,
5. `python -m alembic heads`,
6. migration SQL contract smoke,
7. `git diff --check`.
