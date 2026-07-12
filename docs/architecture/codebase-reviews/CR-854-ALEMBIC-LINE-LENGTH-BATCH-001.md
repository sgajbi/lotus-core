# CR-854: Alembic Line Length Batch 001

Status: Hardened on 2026-06-02.

## Finding

After the active-code line-length cleanup, the remaining Ruff findings were concentrated in
historical Alembic migrations. The first small migration batch carried 46 `E501` findings across
early cashflow, reprocessing, cost-basis, issuer, FX metadata, lifecycle, and FX contract
migrations.

## Change

Ran Ruff formatting against a bounded set of nine Alembic revision files. The change wraps
migration function calls and literals while preserving revision identifiers, down revisions,
upgrade operations, downgrade operations, and migration graph shape.

Full Ruff findings are down from 218 to 172 after this slice. The remaining findings are still all
`E501`.

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
2. `python -m ruff check . --select E501 --statistics`,
3. `python -m py_compile <batch>`,
4. `python -m alembic heads`,
5. migration SQL contract smoke.
