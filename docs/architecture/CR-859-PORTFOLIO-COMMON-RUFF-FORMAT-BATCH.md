# CR-859: Portfolio Common Ruff Format Batch

Status: Hardened on 2026-06-02.

## Finding

After CR-858, Ruff lint was clean and enforced, but full `ruff format --check .` still reported 125
files requiring formatting. The next bounded subset was concentrated in `portfolio_common`
shared-library helpers and transaction-domain validation modules.

## Change

Ran Ruff formatting against selected files under:

1. `src/libs/portfolio-common/portfolio_common/`,
2. `src/libs/portfolio-common/portfolio_common/transaction_domain/`.

The repository-wide format baseline is down from 125 files to 110 files requiring formatting.

## Boundary Preserved

This change does not alter:

1. shared helper behavior,
2. transaction-domain validation semantics,
3. runtime service behavior,
4. API contracts,
5. database schema,
6. migration graph shape.

## Wiki Decision

No repo-local `wiki/` source update is included. This is mechanical formatting of shared-library
helpers with no operator-facing behavior change.

## Validation

Local validation passed for the slice:

1. scoped `python -m ruff format --check <batch>`,
2. `make quality-ruff-gate`,
3. `python -m ruff format --check .` baseline measurement,
4. `python -m py_compile <batch>`,
5. focused shared-library tests,
6. `git diff --check`.
