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

CR-873 replaced the reprocessing job claim path's interpolated `ORDER BY` SQL with two explicit
static claim-query templates selected by job type. The Bandit baseline is down to 10 findings:
0 low, 10 medium, and 0 high. Security remains report-only until the remaining health-probe
bind-host findings are fixed or explicitly governed.

CR-874 centralized consumer health-probe bind-host selection in
`portfolio_common.health_server.health_probe_bind_host()`, routed all worker consumer managers
through the shared helper, and added focused configuration tests. The Bandit baseline is now clean:
0 findings across `src`. Security is ready for the next progressive CI ratchet that promotes
Bandit from report-only to an enforced quality-baseline gate.

CR-875 added `make quality-bandit-gate` and a dedicated quality-baseline Bandit security workflow
job. The clean Bandit baseline is now enforced in CI while the report-only workflow retains broader
security and dependency-audit visibility.

CR-876 cleaned the high-confidence Vulture findings under production source by marking intentional
callback parameters explicitly unused. It also added `make quality-vulture-source-gate` and a
dedicated quality-baseline Vulture source dead-code workflow job using
`python -m vulture src --exclude "*/tests/*" --min-confidence 80`. The production-source dead-code
baseline is now clean and enforced; the broader `src tests` Vulture report remains report-only
because many test fixture parameters still require a separate cleanup plan.

CR-877 scoped the report-only dependency-usage baseline to production source with
`python -m deptry src --extend-exclude "src/services/query_service/build"` so the workflow no
longer scans local virtual environments or generated query-service build output. The measured
production-source baseline is 928 `DEP003` findings across 485 scanned files. The dominant findings
are first-party module modeling (`portfolio_common`, `src`) and undeclared runtime packages such as
`sqlalchemy`, `fastapi`, and `pydantic`; deptry remains report-only until package metadata and
first-party boundaries are made truthful.

CR-878 made root dependency metadata truthful for the shared runtime dependency union, configured
deptry first-party package/module mapping, and governed runtime-only dependency exceptions for
packages required by packaging, DB drivers, migrations, or framework runtime behavior but not
directly imported by production source. The production-source command
`python -m deptry src --extend-exclude "src/services/query_service/build" --extend-exclude ".*/tests/"`
now reports no dependency issues and is enforced by `make quality-deptry-source-gate` plus a
dedicated quality-baseline Deptry source dependency workflow job.

CR-879 measured the source maintainability baseline with `python -m radon mi src -s`. Current
source has no D/E/F maintainability modules, but it still has C-ranked hotspots in
`portfolio_common/openapi_enrichment.py` and selected query-service repository/service modules.
The new `make quality-maintainability-gate` target uses `scripts/maintainability_gate.py` to parse
Radon JSON output and fail only when a production source module drops below C. The clean no-D/E/F
baseline is now enforced in the quality-baseline workflow while existing C hotspots remain visible
for follow-up refactor slices.

CR-880 reduced the advisory proposal simulation complexity hotspot by extracting helper boundaries
inside `advisory_engine.py`. `run_proposal_simulation` now reports `B (6)` under
`python -m radon cc src\services\query_service\app\advisory_simulation\advisory_engine.py -s`, and
the focused advisory simulation suite reports `29 passed`. Repository-wide Xenon complexity
enforcement remains report-only because
`src/services/calculators/cost_calculator_service/app/consumer.py:227 process_message` remains
F-ranked and `src/libs/portfolio-common/portfolio_common/transaction_domain/fx_linkage.py` remains
a D-ranked module.

CR-881 reduced the cost-calculator consumer complexity hotspot by extracting private helpers for
transaction preparation, cost-engine processing, persistence, cash-leg validation, bundle-A
diagnostics, and outbox emission. `CostCalculatorConsumer.process_message` now reports `C (11)`
under `python -m radon cc src\services\calculators\cost_calculator_service\app\consumer.py -s`,
and the focused cost-consumer suite reports `26 passed`. Repository-wide Xenon complexity
enforcement remains report-only because
`src/libs/portfolio-common/portfolio_common/transaction_domain/fx_linkage.py` remains a D-ranked
module.

CR-882 reduced the final current Xenon blocker by extracting pure helper boundaries inside
`fx_linkage.py`. `enrich_fx_transaction_metadata` now reports `B (7)` under
`python -m radon cc src\libs\portfolio-common\portfolio_common\transaction_domain\fx_linkage.py -s`,
and the focused FX linkage suite reports `5 passed`. `make quality-complexity-gate` now runs
`python -m xenon --max-absolute E --max-modules C --max-average A src` cleanly and is enforced in
the quality-baseline workflow.

CR-883 reduced the shared OpenAPI enrichment maintainability hotspot by extracting schema
example/description inference into `portfolio_common.openapi_examples`. `openapi_enrichment.py` now
reports `A (25.84)` and the new helper module reports `B (17.56)` under
`python -m radon mi src\libs\portfolio-common\portfolio_common\openapi_enrichment.py src\libs\portfolio-common\portfolio_common\openapi_examples.py -s`.
The current C-ranked maintainability list no longer includes `openapi_enrichment.py`.

CR-884 reduced reference-data coverage calculation debt by extracting pure benchmark and risk-free
coverage helpers into `reference_coverage_calculations.py`. `get_benchmark_coverage` now reports
`A (4)` instead of `C (11)` under Radon cyclomatic complexity, and
`reference_data_repository.py` improved from `C (4.26)` to `C (6.94)` under Radon
maintainability. The new helper module reports `A (50.34)`. This does not remove
`reference_data_repository.py` from the current C-ranked maintainability list; the C-hotspot count
remains 8.

CR-885 reduced the load-run progress operations repository hotspot by splitting scalar statement
construction, summary-row statement construction, valuation handoff SQL, and summary mapping into
named helpers. `get_load_run_progress` now reports `A (3)` instead of `D (27)` under Radon
cyclomatic complexity, and all extracted load-run helper methods report A-ranked complexity.
`operations_repository.py` remains `C (0.00)` under Radon maintainability, so the C-hotspot count
remains 8.

CR-886 reduced the reconciliation run filtering hotspot by splitting time, identity, and run
attribute filters into named helpers. `_apply_reconciliation_run_scope` now reports `A (2)` instead
of `C (11)` under Radon cyclomatic complexity, and the extracted reconciliation run scope helpers
all report A-ranked complexity. `operations_repository.py` remains `C (0.00)` under Radon
maintainability, so the C-hotspot count remains 8.

CR-887 reduced the valuation job filtering hotspot by splitting direct-lookup-aware actionable-job
filtering, valuation attributes, and valuation identity filters into named helpers.
`_apply_valuation_job_scope` now reports `A (3)` instead of `B (9)` under Radon cyclomatic
complexity, and the extracted valuation scope helpers all report A-ranked complexity.
`operations_repository.py` remains `C (0.00)` under Radon maintainability, so the C-hotspot count
remains 8.

CR-888 reduced the aggregation job filtering hotspot by splitting aggregation-date and
aggregation-identity filters into named helpers. `_apply_aggregation_job_scope` now reports
`A (3)` instead of `B (6)` under Radon cyclomatic complexity, and the extracted aggregation scope
helpers report A-ranked complexity. `operations_repository.py` remains `C (0.00)` under Radon
maintainability, so the C-hotspot count remains 8.

CR-889 reduced the portfolio-control stage filtering hotspot by splitting stage identity and
business-date filters into named helpers. `_apply_portfolio_control_stage_scope` now reports
`A (3)` instead of `B (6)` under Radon cyclomatic complexity, and the extracted portfolio-control
stage scope helpers report A-ranked complexity. `operations_repository.py` remains `C (0.00)`
under Radon maintainability, so the C-hotspot count remains 8.

CR-890 reduced the reprocessing job filtering hotspot by splitting payload security and job
identity filters into named helpers. `_apply_reprocessing_job_scope` now reports `A (3)` instead
of `B (6)` under Radon cyclomatic complexity, and the extracted reprocessing job scope helpers
report A-ranked complexity. `operations_repository.py` remains `C (0.00)` under Radon
maintainability, so the C-hotspot count remains 8.

CR-891 reduced the current position history filtering hotspot by splitting security expression
resolution, normalized security filtering, and history-date/as-of filtering into named helpers.
`_apply_current_position_history_scope` now reports `A (1)` instead of `B (6)` under Radon
cyclomatic complexity, and the extracted position-history scope helpers report A-ranked
complexity. `operations_repository.py` remains `C (0.00)` under Radon maintainability, so the
C-hotspot count remains 8.

CR-892 reduced duplicated support-job health summary orchestration by extracting shared threshold,
aggregate-result selection, row-mapping, and execution helpers for valuation and aggregation jobs.
`get_valuation_job_health_summary` and `get_aggregation_job_health_summary` now both report
`A (1)` instead of `B (6)` under Radon cyclomatic complexity, and the extracted support-job health
helpers report A-ranked complexity. `operations_repository.py` remains `C (0.00)` under Radon
maintainability, so the C-hotspot count remains 8.

CR-893 reduced analytics export health summary orchestration by extracting aggregate, oldest-open
lookup, result-selection, row-mapping, and execution helpers. `get_analytics_export_job_health_summary`
now reports `A (1)` instead of `B (6)` under Radon cyclomatic complexity, and the extracted
analytics export health helpers report A-ranked complexity. `operations_repository.py` remains
`C (0.00)` under Radon maintainability, so the C-hotspot count remains 8.

CR-894 reduced missing historical FX dependency summary orchestration by extracting transaction
base-scope SQL, aggregate SQL, sample SQL, sample-record mapping, and summary assembly helpers.
`get_missing_historical_fx_dependency_summary` now reports `A (1)` instead of `B (6)` under Radon
cyclomatic complexity, and the extracted missing-FX helpers report A-ranked complexity.
`operations_repository.py` remains `C (0.00)` under Radon maintainability, so the C-hotspot count
remains 8.

CR-895 reduced lineage key query orchestration by extracting correlated latest-date subqueries,
artifact-gap policy, lineage priority policy, and result projection helpers. `get_lineage_keys`
now reports `A (4)` instead of `B (6)` under Radon cyclomatic complexity, and the extracted
lineage helpers report A-ranked complexity. This removes the remaining B-ranked method from
`operations_repository.py`; the module still reports `C (0.00)` under Radon maintainability, so
the C-hotspot count remains 8.

CR-896 reduced reference FX-rate query debt by extracting FX pair normalization and latest-rate SQL
construction into `reference_fx_queries.py`. `list_latest_fx_rates` now reports `A (3)` instead of
`B (6)` under Radon cyclomatic complexity, and `reference_data_repository.py` improved from
`C (6.94)` to `C (7.55)` under Radon maintainability. The new FX query helper module reports
`A (60.98)`. This does not remove `reference_data_repository.py` from the current C-ranked
maintainability list; the C-hotspot count remains 8.

CR-897 reduced DPM portfolio-universe query debt by extracting DPM source eligibility predicates,
canonical mandate-binding ranking, cursor pagination, and limit SQL construction into
`reference_dpm_queries.py`. `list_dpm_portfolio_universe_candidates` now reports `A (1)` instead
of `B (6)` under Radon cyclomatic complexity, and `reference_data_repository.py` improved from
`C (7.55)` to `C (8.74)` under Radon maintainability. The new DPM query helper module reports
`A (53.24)`. This does not remove `reference_data_repository.py` from the current C-ranked
maintainability list; the C-hotspot count remains 8.

CR-898 reduced operations-service runtime-state debt by extracting source-data product runtime
metadata, reconciliation status aggregation, analytics export normalization, stale-running
detection, and export operational-state classification into `operations_runtime_state.py`.
`OperationsService._evidence_product_runtime_metadata`, `OperationsService._aggregate_statuses`,
and `OperationsService._get_analytics_export_operational_state` now each report `A (1)` under
Radon cyclomatic complexity. `operations_service.py` improved from `C (5.44)` to `B (9.91)` under
Radon maintainability, and the new runtime-state helper module reports `A (46.40)`. This removes
`operations_service.py` from the current C-ranked maintainability list and reduces the C-hotspot
count from 8 to 7.

CR-899 reduced position-timeseries orchestration complexity by extracting page support-input reads,
page scope resolution, previous-EOD continuity inputs, position row assembly, and FX-rate guard
helpers inside `analytics_timeseries_service.py`. `get_position_timeseries` now reports `C (15)`
instead of `E (37)` under Radon cyclomatic complexity, and the extracted row-assembly helpers all
report A-ranked complexity. `analytics_timeseries_service.py` still reports `C (0.00)` under Radon
maintainability, so the C-hotspot count remains 7.

CR-900 reduced core snapshot orchestration complexity by extracting currency context resolution,
simulation projection/session validation, section population, governance resolution,
fingerprinting, and response construction helpers inside `core_snapshot_service.py`.
`get_core_snapshot` now reports `A (4)` instead of `E (39)` under Radon cyclomatic complexity, and
the newly extracted orchestration helpers all report A-ranked complexity. `core_snapshot_service.py`
still reports `C (0.00)` under Radon maintainability, so the C-hotspot count remains 7.

CR-901 reduced core snapshot projected-position complexity by extracting baseline copy, simulation
change normalization, missing-instrument seeding, quantity-delta application, baseline/priced
valuation, market-to-portfolio FX, and output filtering helpers inside `core_snapshot_service.py`.
`_resolve_projected_positions` now reports `A (2)` instead of `E (34)` under Radon cyclomatic
complexity, and the extracted projected-position helpers report A-ranked complexity.
`core_snapshot_service.py` still reports `C (0.00)` under Radon maintainability, so the C-hotspot
count remains 7.

CR-902 reduced core snapshot baseline-position complexity by extracting current snapshot/history
row selection, row-to-entry mapping, cash/zero filtering, market-value selection,
instrument/no-instrument payload construction, and freshness metadata helpers inside
`core_snapshot_service.py`. `_resolve_baseline_positions` now reports `A (3)` instead of `D (28)`
under Radon cyclomatic complexity, and the extracted baseline-position helpers report A-ranked
complexity. This removes the remaining D-ranked method from `core_snapshot_service.py`, but the
module still reports `C (0.00)` under Radon maintainability, so the C-hotspot count remains 7.

CR-903 reduced core snapshot instrument-enrichment complexity by extracting request identifier
normalization, enrichment lookup-map construction, and per-security DTO mapping helpers inside
`core_snapshot_service.py`. `get_instrument_enrichment_bulk` now reports `A (2)` instead of
`C (13)` under Radon cyclomatic complexity, and the extracted instrument-enrichment helpers report
A-ranked complexity. This removes the remaining C-ranked method from `core_snapshot_service.py`,
but the module still reports `C (0.00)` under Radon maintainability, so the C-hotspot count
remains 7.

CR-904 reduced core snapshot simulation-validation complexity by extracting required simulation
options, required session lookup, portfolio ownership validation, and expected-version validation
helpers inside `core_snapshot_service.py`. `_validated_simulation_session` now reports `A (1)`
instead of `B (6)` under Radon cyclomatic complexity, and the extracted simulation-validation
helpers report A-ranked complexity. `core_snapshot_service.py` still reports `C (0.00)` under
Radon maintainability, so the C-hotspot count remains 7.

CR-905 reduced core snapshot delta-section complexity by extracting delta security-id selection,
delta value extraction, weight calculation, and record construction helpers inside
`core_snapshot_service.py`. `_build_delta_section` now reports `A (2)` instead of `B (10)` under
Radon cyclomatic complexity, and the extracted delta-section helpers report A-ranked complexity.
`core_snapshot_service.py` still reports `C (0.00)` under Radon maintainability, so the C-hotspot
count remains 7.

CR-906 reduced core snapshot data-quality classification complexity by extracting the
current-snapshot completeness predicate inside `core_snapshot_service.py`.
`_snapshot_data_quality_status` now reports `A (4)` instead of `B (6)` under Radon cyclomatic
complexity. `core_snapshot_service.py` now has no B-or-worse methods under Radon cyclomatic
complexity, but it still reports `C (0.00)` under Radon maintainability, so the C-hotspot count
remains 7.

CR-907 reduced core snapshot service module size by extracting market-value total, position weight
assignment, and delta-section construction helpers into `core_snapshot_calculations.py`. The new
calculation module reports `A (43.88)` under Radon maintainability and no B-or-worse methods under
Radon cyclomatic complexity. `core_snapshot_service.py` shrank from 1,208 SLOC / 518 LLOC to 1,093
SLOC / 464 LLOC, but it still reports `C (0.00)` under Radon maintainability, so the C-hotspot
count remains 7.

CR-908 reduced analytics portfolio-observation complexity by extracting page scope, support-input
reads, row bucketing, per-date observation assembly, FX rate guards, and next-page token helpers
inside `analytics_timeseries_service.py`. `_portfolio_observation_rows` now reports `A (2)`
instead of `D (22)` under Radon cyclomatic complexity, and the extracted portfolio-observation
helpers report A-ranked complexity. `analytics_timeseries_service.py` still reports `C (0.00)`
under Radon maintainability, so the C-hotspot count remains 7.

CR-909 reduced analytics beginning-market-value policy complexity by extracting prior-EOD
continuity, internal cash-book settlement, previous-EOD repair, and new internally funded position
predicates inside `analytics_timeseries_service.py`. `_effective_beginning_market_value` now
reports `A (5)` instead of `C (17)` under Radon cyclomatic complexity, and the extracted policy
predicates report A-ranked complexity. `analytics_timeseries_service.py` still reports `C (0.00)`
under Radon maintainability, so the C-hotspot count remains 7.

CR-910 reduced analytics latest-performance-horizon complexity by extracting observed-date
promotion, portfolio candidate selection, available horizon collection, and as-of-date bounding
helpers inside `analytics_timeseries_service.py`. `_latest_available_performance_date` now reports
`A (1)` instead of `C (12)` under Radon cyclomatic complexity, and the extracted horizon helpers
report A-ranked complexity. `analytics_timeseries_service.py` still reports `C (0.00)` under Radon
maintainability, so the C-hotspot count remains 7.

CR-911 reduced analytics window-resolution complexity by extracting explicit-window bounding,
period-start selection, and inception-date clamping helpers inside
`analytics_timeseries_service.py`. `_resolve_window` now reports `A (2)` instead of `C (11)` under
Radon cyclomatic complexity, and the extracted window-resolution helpers report A-ranked
complexity. `analytics_timeseries_service.py` still reports `C (0.00)` under Radon maintainability,
so the C-hotspot count remains 7.

CR-912 reduced analytics portfolio-timeseries orchestration complexity by extracting request-scope
fingerprinting, page-token cursor validation, and diagnostics construction helpers inside
`analytics_timeseries_service.py`. `get_portfolio_timeseries` now reports `A (4)` instead of
`C (11)` under Radon cyclomatic complexity, and the extracted portfolio-timeseries helpers report
A-ranked complexity. `analytics_timeseries_service.py` still reports `C (0.00)` under Radon
maintainability, so the C-hotspot count remains 7.

CR-913 reduced analytics position-timeseries orchestration complexity by extracting request-scope
fingerprinting, cursor validation, dimension-filter projection, snapshot-epoch resolution,
next-page token, and diagnostics helpers inside `analytics_timeseries_service.py`.
`get_position_timeseries` now reports `A (4)` instead of `C (15)` under Radon cyclomatic
complexity, and the extracted position-timeseries helpers report A-ranked complexity. This removes
the final C-ranked method from `analytics_timeseries_service.py`; the module still reports
`C (0.00)` under Radon maintainability, so the C-hotspot count remains 7.
