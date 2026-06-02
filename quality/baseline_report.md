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
2. Ruff is now repository-clean under the current root config; the next risk is keeping that clean
   state enforced on every pull request.
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
4. Convert baseline reports into regression-only gates once stable artifacts exist. Ruff is the
   first converted gate because CR-855 made it repository-clean.

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

CR-850 normalized import ordering for governance scripts, tools, and shared supportability helpers.
Full Ruff findings are down to 271: 250 `E501`, 20 `I001`, and 1 `E402`.

CR-851 normalized the remaining app and test import-order findings. `python -m ruff check .
--select I001 --statistics` is now clean, and full Ruff findings are down to 251: 250 `E501` and
1 `E402`.

CR-852 removed the final `E402` import-position finding from Alembic metadata bootstrap while
preserving the required path setup order. Full Ruff findings are down to 250, all `E501`.

CR-853 started the line-length ratchet on active non-Alembic code and tests. Full Ruff findings are
down to 218, all `E501`.

CR-854 normalized line length in a first bounded Alembic migration batch. Full Ruff findings are
down to 172, all `E501`.

CR-855 normalized line length in the remaining Alembic migration hotspots. `python -m ruff check
. --statistics` is now clean, establishing Ruff as a candidate regression gate instead of a
report-only debt inventory.

CR-856 added a dedicated Ruff regression gate to the quality-baseline workflow and a repo-native
`make quality-ruff-gate` target. The broader quality workflow remains report-only for checks whose
baselines are not yet clean.

CR-857 started the Ruff format ratchet with a bounded Alembic formatting batch. Repository-wide
`ruff format --check .` debt is down from 154 to 141 files while the Ruff lint regression gate
remains clean.

CR-858 continued the Ruff format ratchet across bounded operational scripts, tools, and their
focused script/tool tests. Repository-wide `ruff format --check .` debt is down from 141 to 125
files while the Ruff lint regression gate remains clean.

CR-859 continued the Ruff format ratchet across bounded `portfolio_common` shared-library helpers.
Repository-wide `ruff format --check .` debt is down from 125 to 110 files while the Ruff lint
regression gate remains clean.

CR-860 continued the Ruff format ratchet across a bounded calculator and runtime-service batch.
Repository-wide `ruff format --check .` debt is down from 110 to 90 files while the Ruff lint
regression gate remains clean.

CR-861 continued the Ruff format ratchet across a bounded ingestion and pipeline-orchestrator batch.
Repository-wide `ruff format --check .` debt is down from 90 to 68 files while the Ruff lint
regression gate remains clean.

CR-862 continued the Ruff format ratchet across a bounded query-service and query-control-plane
batch. Repository-wide `ruff format --check .` debt is down from 68 to 52 files while the Ruff lint
regression gate remains clean.

CR-863 continued the Ruff format ratchet across a bounded timeseries and valuation-orchestrator
batch. Repository-wide `ruff format --check .` debt is down from 52 to 40 files while the Ruff lint
regression gate remains clean.

CR-864 continued the Ruff format ratchet across bounded shared test support, persistence repository
integration collection, portfolio-common unit tests, and local stack contract tests.
Repository-wide `ruff format --check .` debt is down from 40 to 21 files while the Ruff lint
regression gate remains clean.

CR-865 completed the Ruff format ratchet across the remaining E2E workflow tests and
query-service advisory-simulation unit tests. Repository-wide `ruff format --check .` is now clean
across 1,070 files, making Ruff format suitable for the next enforced quality gate.

CR-866 added `make quality-ruff-format-gate` and a dedicated quality-baseline workflow job that
runs `python -m ruff format --check .`. Ruff lint and Ruff format are now both enforced clean
baselines; the remaining quality tools stay report-only until their baselines are made truthful and
stable.

CR-867 corrected the `.importlinter` contracts to enforce the intended architecture boundaries
instead of over-broad indirect dependency rules, added `scripts/import_boundary_gate.py`, and
promoted import-linter to an enforced quality-baseline job. The import boundary gate currently keeps
2 contracts: query-service routers do not directly import repositories, and FastAPI dependencies in
`portfolio_common` remain limited to approved HTTP/cross-cutting modules.

CR-868 promoted the existing clean OpenAPI quality and API vocabulary gates into a dedicated
quality-baseline API governance job. `python scripts/openapi_quality_gate.py` passes across the
registered API services, and `python scripts/api_vocabulary_inventory.py --validate-only` validates
the governed vocabulary inventory.

CR-869 promoted the clean configured mypy baseline into a dedicated quality-baseline typecheck job
and removed a stale unused `[mypy-tests.*]` section from `mypy.ini`. `make typecheck` now reports
success without unused-config noise for the configured query-service DTO/router scope.

CR-869 also measured the local Bandit security baseline. `python -m bandit -r src -c pyproject.toml`
currently reports 17 findings: 5 low, 11 medium, and 1 high. Security remains report-only until
those findings are fixed or explicitly governed.

CR-870 removed MD5 from query-service request fingerprint generation by consolidating core snapshot
and analytics export fingerprints onto the shared SHA-256 helper. The Bandit baseline is down to 16
findings: 5 low, 11 medium, and 0 high. Security remains report-only until the remaining findings
are fixed or explicitly governed.

CR-871 replaced production `assert` guards in operations routing, analytics export creation, and
core snapshot simulation handling with explicit runtime guards and focused tests. The Bandit
baseline is down to 12 findings: 1 low, 11 medium, and 0 high.

CR-872 replaced string-based enterprise readiness integer setting attribute lookup with explicit
typed settings access for secret-rotation and write-payload policy knobs. The Bandit baseline is
down to 11 findings: 0 low, 11 medium, and 0 high. Security remains report-only until the remaining
medium findings are fixed or explicitly governed.
