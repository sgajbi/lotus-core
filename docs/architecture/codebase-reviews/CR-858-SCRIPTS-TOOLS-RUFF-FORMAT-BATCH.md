# CR-858: Scripts And Tools Ruff Format Batch

Status: Hardened on 2026-06-02.

## Finding

After CR-857, Ruff lint was clean and enforced, but full `ruff format --check .` still reported 141
files requiring formatting. The next bounded subset was concentrated in operational scripts, tools,
and focused tests for those support utilities.

## Change

Ran Ruff formatting against selected files under:

1. `scripts/`,
2. `tools/`,
3. `tests/unit/scripts/`,
4. `tests/integration/tools/`.

The repository-wide format baseline is down from 141 files to 125 files requiring formatting.

## Boundary Preserved

This change does not alter:

1. runtime service behavior,
2. API contracts,
3. database schema,
4. migration graph shape,
5. existing workflow semantics,
6. script/tool command contracts.

## Wiki Decision

No repo-local `wiki/` source update is included. This is mechanical formatting of repository
support utilities and focused tests with no operator-facing behavior change.

## Validation

Local validation passed for the slice:

1. scoped `python -m ruff format --check <batch>`,
2. `make quality-ruff-gate`,
3. `python -m ruff format --check .` baseline measurement,
4. `python -m py_compile <batch>`,
5. focused script/tool tests,
6. `git diff --check`.
