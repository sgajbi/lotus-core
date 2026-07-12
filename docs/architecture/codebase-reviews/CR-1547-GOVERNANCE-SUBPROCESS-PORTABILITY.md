# CR-1547: Governance Subprocess Portability

Date: 2026-07-12
Status: Fixed locally; merge proof pending

## Objective

Make repository-native Python governance checks deterministic across Windows and Unix virtual
environments.

## Finding

`migration_contract_check.py` invoked Alembic through a bare `python`. On Windows, its child process
resolved the Windows Store interpreter instead of the active project virtual environment and could
not execute Alembic. A same-lens warning-gate run found one architecture test still monkeypatching
the guard's former `scripts/` module path after its move to `scripts/quality/`.

## Fix

- Use `sys.executable` for Alembic head and history subprocesses.
- Add focused tests that assert both commands preserve the active interpreter.
- Correct the stale architecture-test module path.
- Scan Python governance and test sources for additional bare-interpreter subprocesses; none remain.

No runtime behavior, API, database migration, or deployment contract changed.

## Validation Evidence

- Migration and architecture-script unit cohort: `28 passed`.
- Repository-native migration smoke: passed with one Alembic head.
- Focused Ruff lint: passed; formatting rerun pending after the stale test correction.

## Documentation Decision

The review ledger captures this execution rule. README, wiki, repository context, and platform
skills do not change because repository-native command semantics and architecture ownership remain
the same.
