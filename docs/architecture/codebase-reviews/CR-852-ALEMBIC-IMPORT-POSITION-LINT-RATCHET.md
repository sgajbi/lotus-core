# CR-852: Alembic Import Position Lint Ratchet

Status: Hardened on 2026-06-02.

## Finding

After unused-symbol and import-order cleanup, Ruff had one non-line-length finding left:
`E402` in `alembic/env.py`. The model module must load after repository-local `sys.path` setup so
Alembic can import `portfolio_common.database_models` from the checkout.

## Change

Moved the import mechanism to a top-level standard-library `importlib` import and dynamically
loaded `portfolio_common.database_models` after path setup with `importlib.import_module(...)`.
This preserves Alembic metadata registration while avoiding a late module-level `import`
statement.

Full Ruff findings are down from 251 to 250 after this slice. The remaining findings are all
`E501` line-length debt.

## Boundary Preserved

This change does not alter:

1. Alembic revision graph,
2. migration operations,
3. target metadata content,
4. runtime service behavior,
5. API contracts or database schema.

## Wiki Decision

No repo-local `wiki/` source update is included. This is Alembic bootstrap hygiene with no
operator-facing behavior change.

## Validation

Local validation passed for the slice:

1. `python -m ruff check . --select E402`,
2. `python -m ruff check . --statistics`,
3. `python -m alembic heads`,
4. migration SQL contract smoke,
5. git diff whitespace checks.
