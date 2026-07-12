# CR-848: Unused Symbol Lint Ratchet

Status: Hardened on 2026-06-02.

## Finding

The quality baseline still carried 20 unused-symbol findings: 19 unused imports and one unused
test local. Most findings came from Alembic metadata bootstrap importing each model class by name
even though only the populated `Base.metadata` object is used.

## Change

1. Replaced the Alembic model-class import list with an explicit `portfolio_common.database_models`
   module import and read `database_models.Base.metadata`, preserving model registration while
   removing unused names.
2. Removed an unused SQLAlchemy alias from a historical Alembic migration.
3. Removed stale unused imports from an ingestion integration test.
4. Removed one unused financial-reconciliation consumer test local.
5. Updated quality reports to record that the unused-symbol lint subset is now clean.

Full Ruff findings are down from 344 to 323 after this slice.

## Boundary Preserved

This change does not alter:

1. runtime service behavior,
2. API routes or DTO fields,
3. database schema or migration operations,
4. Alembic target metadata content,
5. test assertions or fixture behavior.

## Wiki Decision

No repo-local `wiki/` source update is included. This is a code hygiene and quality-ratchet slice
with no operator-facing behavior change.

## Validation

Local validation passed for the slice:

1. `python -m ruff check . --select F401,F841`,
2. `python -m alembic heads`,
3. migration SQL contract smoke,
4. ingestion transaction-router collection,
5. focused financial-reconciliation consumer test,
6. git diff whitespace checks.
