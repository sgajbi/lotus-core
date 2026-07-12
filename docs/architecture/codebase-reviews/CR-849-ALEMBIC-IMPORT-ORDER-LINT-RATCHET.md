# CR-849: Alembic Import Order Lint Ratchet

Status: Hardened on 2026-06-02.

## Finding

After the unused-symbol cleanup, the Ruff baseline still carried 72 import-order findings. Forty
of those findings were isolated to `alembic/`, mostly historical migration scripts with
non-standard `alembic` and `sqlalchemy` import ordering.

## Change

Ran Ruff import organization against `alembic/` only. This normalized import grouping and spacing
for Alembic environment and migration files without changing revision identifiers, upgrade logic,
downgrade logic, migration graph shape, or database operations.

Full Ruff findings are down from 323 to 283 after this slice.

## Boundary Preserved

This change does not alter:

1. migration revision IDs,
2. migration dependencies,
3. upgrade or downgrade operations,
4. Alembic target metadata loading,
5. runtime service behavior,
6. API contracts or database schema.

## Wiki Decision

No repo-local `wiki/` source update is included. This is a migration-source formatting and quality
ratchet with no operator-facing behavior change.

## Validation

Local validation passed for the slice:

1. `python -m ruff check alembic --select I001`,
2. `python -m ruff check . --statistics`,
3. `python -m alembic heads`,
4. migration SQL contract smoke,
5. git diff whitespace checks.
