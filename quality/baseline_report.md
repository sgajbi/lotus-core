# lotus-core Quality Baseline Report

Status: Initial report-only baseline captured on 2026-06-02.

## Scope

This baseline starts the measurable refactor program for `lotus-core`. It is intentionally
report-only: current findings are not hidden, and this document does not claim production or
bank-buyable readiness.

## Measured Current State

| Area | Baseline Evidence |
| --- | --- |
| Python files | 1,040 files under `src` and `tests` |
| Python lines | 213,290 lines under `src` and `tests` |
| Quality surface | 2,184 `py`, `md`, `yaml`, `yml`, and `json` files under `src`, `tests`, and `docs` |
| Generated/build copies | 1 build directory: `src/services/query_service/build` |
| Largest files | `tests/integration/services/ingestion_service/test_ingestion_routers.py` 6,566 lines; `tests/unit/services/query_service/services/test_integration_service.py` 4,219 lines; `src/services/query_service/app/dtos/reference_integration_dto.py` 3,643 lines |
| Ruff baseline | 344 findings: 250 `E501`, 73 `I001`, 19 `F401`, 1 `E402`, 1 `F841` |
| Test collection baseline | 3,500 tests collected before 3 collection errors |
| Test collection errors | e2e non-top-level `pytest_plugins`; unit/integration import-name collisions for `test_outbox_dispatcher.py` and `test_kafka_setup.py` |
| Cyclomatic complexity | `radon cc src -s -a`: 3,886 blocks, average complexity `A (3.01)` |
| High-complexity examples | `validate_event_supportability_catalog` `E (39)`, `validate_fx_transaction` `E (37)`, `enrich_fx_transaction_metadata` `D (30)`, `validate_interest_transaction` `D (29)` |
| Maintainability examples | `portfolio_common/openapi_enrichment.py` `C (3.38)`, `portfolio_common/enterprise_readiness.py` `B (13.90)` |
| Installed baseline tools | `radon 6.0.1`, `pip-audit 2.10.0`, `mypy 1.20.2`, `pytest 9.0.3`, `ruff 0.15.14` |
| Missing local commands | `xenon`, `vulture`, `deptry`, `bandit`, `import-linter`, `interrogate`, `spectral` command were not locally available in this shell |

## Baseline Gaps

1. Full-suite pytest collection is not clean; collection must be fixed before using repository-wide
   test count or coverage as an enterprise readiness claim.
2. Ruff is not yet repository-clean under the current root config.
3. Generated `build` copies under `src/services/query_service/build` inflate line-count and
   duplicate-surface metrics.
4. OpenAPI quality, architecture-boundary, security, dependency, docstring, dead-code, and
   dependency-usage checks need report-only CI artifacts before threshold enforcement.
5. Coverage and branch coverage are not yet captured in this initial baseline because full-suite
   collection fails.

## Next Ratchet

1. Make report-only CI publish the same baseline checks on pull requests.
2. Run pytest collection as runtime-separated lanes now that import/plugin collection blockers are
   removed.
3. Keep generated build copies out of the active source checkout and quality scope.
4. Convert baseline reports into regression-only gates once stable artifacts exist.

## Follow-up Measurement

After the initial baseline, CR-847 removed the local generated
`src/services/query_service/build` tree and fixed the pytest 9 plugin/import-mode collection
blockers. `python -m pytest --collect-only -q` now reaches 3,575 collected tests and then stops at
the repository's governed mixed-runtime guard because db-direct integration tests and live-worker
E2E tests must run in separate invocations.

CR-848 removed the unused-symbol lint subset. `python -m ruff check . --select F401,F841
--statistics` is now clean, and full Ruff findings are down to 323: 250 `E501`, 72 `I001`, and 1
`E402`.

CR-849 normalized Alembic import ordering. `python -m ruff check alembic --select I001` is now
clean, and full Ruff findings are down to 283: 250 `E501`, 32 `I001`, and 1 `E402`.
