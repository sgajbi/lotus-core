# CR-450: Warning Gate Unique Repository Test Basenames

Date: 2026-05-28

## Scope

Unit warning-gate collection for persistence-service and query-service repository tests.

## Finding

The new persistence-service instrument repository proof used the basename
`test_instrument_repository.py`, which already existed in the query-service repository test
suite. The CI unit warning gate collects the broader unit suite, so pytest imported one module
basename and then reported an import-file mismatch when collecting the other. That failure blocked
the Feature Lane and could mask whether the actual repository tests had run.

## Change

Renamed the persistence-service instrument repository test to
`test_persistence_instrument_repository.py`, matching the existing repository-test naming pattern
used for persistence-specific proofs and avoiding pytest module basename collisions in broad
collection.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/persistence_service/repositories/test_persistence_instrument_repository.py tests/unit/services/query_service/repositories/test_instrument_repository.py -q`
2. `python -m ruff check tests/unit/services/persistence_service/repositories/test_persistence_instrument_repository.py`
3. `python scripts/warning_budget_gate.py --suite unit --max-warnings 0 --quiet`
4. `git diff --check`

Results:

1. Focused persistence/query repository pytest: `8 passed`
2. Touched-surface ruff: passed
3. Unit warning gate: `2244 passed, 9 deselected`; `warnings=0`
4. Diff hygiene: passed

## Closure

Status: Hardened.

No application code, route, OpenAPI schema shape, wiki source, or platform contract change was
required. This slice restores deterministic unit-gate collection for the enterprise hardening
branch and keeps repository test filenames unique by service ownership.
