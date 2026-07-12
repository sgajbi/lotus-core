# CR-864: Shared Test Support Ruff Format Batch

Status: Hardened on 2026-06-02.

## Finding

After CR-863, Ruff lint was clean and enforced, but full `ruff format --check .` still reported 40
files requiring formatting. The next bounded subset covered shared test support, persistence
repository integration collection, portfolio-common unit tests, and local stack contract tests.

## Change

Ran Ruff formatting against selected files under:

1. `tests/test_support/`,
2. `tests/integration/services/persistence_service/repositories/`,
3. `tests/unit/libs/portfolio-common/`,
4. `tests/unit/libs/portfolio_common/`,
5. focused unit docs, local stack, releasability, and runtime-mode contract tests.

The repository-wide format baseline is down from 40 files to 21 files requiring formatting.

## Boundary Preserved

This change does not alter:

1. persistence repository behavior,
2. shared runtime-mode support behavior,
3. portfolio-common unit assertions,
4. local stack contract assertions,
5. API contracts,
6. database schema.

## Wiki Decision

No repo-local `wiki/` source update is included. This is mechanical formatting of test/support
files with no operator-facing behavior change.

## Validation

Local validation passed for the slice:

1. scoped `python -m ruff format --check <batch>`,
2. `make quality-ruff-gate`,
3. `python -m ruff format --check .` baseline measurement,
4. `python -m py_compile <batch>`,
5. focused shared/library unit tests: 111 passed,
6. persistence repository integration collection: 12 tests collected,
7. `git diff --check`.
