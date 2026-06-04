# CR-847: Pytest Collection And Build Artifact Hardening

Status: Hardened on 2026-06-02.

## Finding

The initial quality baseline identified three repository-wide pytest collection blockers and one
generated source-tree build directory. Those blockers prevented collection from reaching the
repository's own runtime-lane guard and inflated local quality-surface measurements with generated
copies under `src/services/query_service/build`.

## Change

1. Moved e2e support plugin registration from `tests/e2e/conftest.py` to repository-root
   `conftest.py`, which keeps pytest 9 plugin discovery at a supported top-level boundary.
2. Enabled pytest `--import-mode=importlib` in `pyproject.toml` so duplicate unit and integration
   test module basenames no longer collide during collection.
3. Removed the local generated `src/services/query_service/build` directory after verifying it was
   untracked, ignored by `.gitignore`, and resolved inside the repository checkout.
4. Updated the quality health and scorecard evidence to distinguish fixed collection blockers from
   the existing governed mixed-runtime separation rule.

## Boundary Preserved

This change does not alter:

1. production runtime behavior,
2. API routes or DTO fields,
3. database schema or migrations,
4. test assertions or fixture semantics,
5. existing runtime-lane separation between db-direct integration and live-worker E2E tests.

## Wiki Decision

No repo-local `wiki/` source update is included in this slice. The change is test harness and
quality-evidence hardening; the operator-facing wiki remains unchanged.

## Validation

Local validation passed for the slice:

1. `python -m pytest --collect-only -q` progressed past the previous plugin/import mismatch
   blockers, collected 3,575 tests, and then stopped at the expected governed mixed-runtime guard,
2. generated build directory absence verified under `src`,
3. focused transaction-record pytest smoke,
4. Alembic head check,
5. migration SQL contract smoke,
6. git diff whitespace checks.
