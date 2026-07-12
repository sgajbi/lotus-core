# CR-862: Query Service Ruff Format Batch

Status: Hardened on 2026-06-02.

## Finding

After CR-861, Ruff lint was clean and enforced, but full `ruff format --check .` still reported 68
files requiring formatting. The next bounded subset covered query-service DTO/router/service files,
query-control-plane operations, and closest focused query tests.

## Change

Ran Ruff formatting against selected files under:

1. `src/services/query_service/`,
2. `src/services/query_control_plane_service/`,
3. focused query-service and query-control-plane tests.

The repository-wide format baseline is down from 68 files to 52 files requiring formatting.

## Boundary Preserved

This change does not alter:

1. query DTO shape,
2. query router behavior,
3. query-control-plane behavior,
4. API contracts,
5. database schema,
6. migration graph shape.

## Wiki Decision

No repo-local `wiki/` source update is included. This is mechanical formatting of query service
files and focused tests with no operator-facing behavior change.

## Validation

Local validation passed for the slice:

1. scoped `python -m ruff format --check <batch>`,
2. `make quality-ruff-gate`,
3. `python -m ruff format --check .` baseline measurement,
4. `python -m py_compile <batch>`,
5. focused query tests and collection checks,
6. `git diff --check`.
