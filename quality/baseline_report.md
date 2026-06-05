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

CR-914 reduced analytics export job creation complexity by extracting reused-job response, dataset
collection, export result payload, export result metrics, and completed-job persistence helpers
inside `analytics_timeseries_service.py`. `create_export_job` now reports `A (4)` instead of
`B (8)` under Radon cyclomatic complexity, and the extracted export job creation helpers report
A-ranked complexity. `analytics_timeseries_service.py` still reports `C (0.00)` under Radon
maintainability, so the C-hotspot count remains 7.

CR-915 reduced analytics export job reservation complexity by extracting completed, in-flight,
freshness, and stale-threshold policy helpers inside `analytics_timeseries_service.py`.
`_reserve_export_job` now reports `A (5)` instead of `B (6)` under Radon cyclomatic complexity, and
the extracted export reservation helpers report A-ranked complexity. `analytics_timeseries_service.py`
still reports `C (0.00)` under Radon maintainability, so the C-hotspot count remains 7.

CR-916 reduced analytics export JSON serialization complexity by extracting Decimal, temporal,
list, and dictionary JSON conversion helpers inside `analytics_timeseries_service.py`. `_jsonable`
now reports `A (5)` instead of `B (7)` under Radon cyclomatic complexity, and the extracted export
serialization helpers report A-ranked complexity. `analytics_timeseries_service.py` still reports
`C (0.00)` under Radon maintainability, so the C-hotspot count remains 7.

CR-917 reduced analytics export NDJSON result complexity by extracting malformed-payload validation,
metadata/data row rendering, UTF-8 encoding, media type, content-encoding, and optional gzip
handling into `analytics_export_ndjson.py`. `get_export_result_ndjson` now reports `A (5)` instead
of `B (7)` under Radon cyclomatic complexity, and the extracted helper module reports A-ranked
maintainability. `analytics_timeseries_service.py` still reports `C (0.00)` under Radon
maintainability, so the C-hotspot count remains 7.

CR-918 reduced analytics export job policy coupling by extracting status normalization, result
endpoint construction, job response shaping, reused-job disposition, result payload construction,
JSON-safe conversion, and export result metric recording into `analytics_export_jobs.py`. The
helper module reports `A (50.45)` maintainability and A-ranked helper complexity.
`analytics_timeseries_service.py` shrank from 1,844 SLOC to 1,770 SLOC, but still reports
`C (0.00)` under Radon maintainability, so the C-hotspot count remains 7.

CR-919 reduced analytics page-token security-policy coupling by extracting deterministic cursor
payload serialization, deterministic envelope encoding, SHA-256 HMAC signing, constant-time
signature comparison, blank-token handling, and malformed/signature error classification into
`analytics_page_tokens.py`. The helper module reports `A (59.76)` maintainability and A-ranked
helper complexity. `analytics_timeseries_service.py` shrank from 1,770 SLOC to 1,751 SLOC, but
still reports `C (0.00)` under Radon maintainability, so the C-hotspot count remains 7.

CR-920 reduced analytics window policy coupling by extracting explicit-window bounding, supported
period start lookup, inception clamping, and invalid-window/period classification into
`analytics_windows.py`. The helper module reports `A (54.96)` maintainability and A-ranked helper
complexity. `analytics_timeseries_service.py` shrank from 1,751 SLOC to 1,707 SLOC, but still
reports `C (0.00)` under Radon maintainability, so the C-hotspot count remains 7.

CR-921 reduced analytics cash-flow policy coupling by extracting cash-flow DTO construction,
portfolio/reporting FX conversion checks, position-flow grouping, internal/external flow predicates,
and beginning-market-value repair rules into `analytics_cash_flows.py`. The helper module reports
`A (37.12)` maintainability and A-ranked helper complexity. `analytics_timeseries_service.py`
shrank from 1,707 SLOC to 1,590 SLOC, but still reports `C (0.00)` under Radon maintainability, so
the C-hotspot count remains 7.

CR-922 reduced analytics FX policy coupling by extracting portfolio/reporting FX map retrieval,
position/portfolio FX map retrieval, same-currency identity handling, and missing-rate
classification into `analytics_fx_rates.py`. The helper module reports `A (51.85)`
maintainability and A-ranked helper complexity. `analytics_timeseries_service.py` shrank from 1,590
SLOC to 1,582 SLOC, but still reports `C (0.00)` under Radon maintainability, so the C-hotspot
count remains 7.

CR-923 reduced analytics pagination and diagnostics coupling by extracting request-scope
fingerprint construction, cursor parsing, next-token payload construction, diagnostics assembly,
and stale-point counting into `analytics_pagination.py`. The helper module reports `A (43.97)`
maintainability and A-ranked helper complexity. `analytics_timeseries_service.py` shrank from 1,582
SLOC to 1,548 SLOC, but still reports `C (0.00)` under Radon maintainability, so the C-hotspot
count remains 7.

CR-924 reduced analytics quality and horizon coupling by extracting row quality labels,
data-quality coverage classification, portfolio-reference completeness classification, evidence
timestamp selection, and latest portfolio/position horizon bounding into `analytics_quality.py`. The
helper module reports `A (52.85)` maintainability and A-ranked helper complexity.
`analytics_timeseries_service.py` shrank from 1,548 SLOC to 1,536 SLOC, but still reports
`C (0.00)` under Radon maintainability, so the C-hotspot count remains 7.

CR-925 reduced analytics position-page scope coupling by extracting position page date ranges,
first-page date selection, security-id collection for page support reads, dimension filter
conversion, and prior-day EOD filtering into `analytics_position_pages.py`. The helper module
reports `A (58.69)` maintainability and A-ranked helper complexity.
`analytics_timeseries_service.py` shrank from 1,536 SLOC to 1,523 SLOC, but still reports
`C (0.00)` under Radon maintainability, so the C-hotspot count remains 7.

CR-926 reduced analytics portfolio-page scope coupling by extracting portfolio observation page
slicing, page-date row buckets, same-currency observation rates, missing cross-currency rate
classification, and portfolio next-page token payloads into `analytics_portfolio_pages.py`. The
helper module reports `A (46.28)` maintainability and A-ranked helper complexity.
`analytics_timeseries_service.py` shrank from 1,523 SLOC to 1,513 SLOC and improved from
`C (0.00)` to `C (1.52)` under Radon maintainability, while the C-hotspot count remains 7.

CR-927 reduced analytics position-response coupling by extracting position response DTO
construction, valuation-status distribution accumulation, same-security previous-EOD carry-forward
between valuation dates, dimension projection, and position/reporting currency value conversion into
`analytics_position_responses.py`. The helper module reports `A (49.05)` maintainability and
A-ranked helper complexity. `analytics_timeseries_service.py` shrank from 1,513 SLOC to 1,424 SLOC
and improved from `C (1.52)` to `C (3.48)` under Radon maintainability, while the C-hotspot count
remains 7.

CR-928 reduced analytics export execution coupling by extracting portfolio and position export page
traversal loops into `analytics_export_execution.py`. The helper module reports `A (51.47)`
maintainability and A-ranked helper complexity. `analytics_timeseries_service.py` shrank from 1,424
SLOC to 1,402 SLOC and improved from `C (3.48)` to `C (5.40)` under Radon maintainability, while
the C-hotspot count remains 7.

CR-929 reduced analytics export lifecycle coupling by extracting completed/inflight status
classification and stale running job freshness policy into `analytics_export_lifecycle.py`. The
helper module reports `A (62.35)` maintainability and A-ranked helper complexity.
`analytics_timeseries_service.py` remained 1,402 SLOC and improved from `C (5.40)` to `C (6.86)`
under Radon maintainability, while the C-hotspot count remains 7.

CR-930 reduced analytics export result coupling by extracting completed-result payload validation,
JSON result DTO construction, NDJSON result transport construction, and malformed-payload error
mapping into `analytics_export_results.py`. The helper module reports `A (62.17)` maintainability
and A-ranked helper complexity. `analytics_timeseries_service.py` shrank from 1,402 SLOC to 1,388
SLOC and improved from `C (6.86)` to `C (7.80)` under Radon maintainability, while the C-hotspot
count remains 7.

CR-931 removed stale analytics quality and performance-horizon wrapper methods from
`analytics_timeseries_service.py` after their policies were already extracted into
`analytics_quality.py`. The active service now calls the helper functions directly, shrank from
1,388 SLOC to 1,325 SLOC, and improved from `C (7.80)` to `B (9.21)` under Radon maintainability.
The generated `query_service/build` copy remains separate generated-surface debt and is not changed
by this slice.

CR-932 reduced core snapshot instrument-enrichment coupling by extracting requested security-id
normalization, returned-instrument lookup-map construction, ordered DTO record construction, and
unknown-security fallback into `core_snapshot_instrument_enrichment.py`. The helper module reports
`A (64.32)` maintainability and A-ranked helper complexity. `core_snapshot_service.py` shrank from
1,093 SLOC to 1,067 SLOC, but remains a C-ranked maintainability hotspot.

CR-933 reduced core snapshot baseline metadata coupling by extracting current-snapshot versus
historical-fallback freshness metadata, latest row/state timestamp selection, single snapshot epoch
selection, and empty-baseline epoch suppression into `core_snapshot_baseline_metadata.py`. The
helper module reports `A (58.44)` maintainability and A-ranked helper complexity.
`core_snapshot_service.py` shrank from 1,067 SLOC to 1,018 SLOC and improved from `C (0.00)` to
`C (2.18)`, but remains a C-ranked maintainability hotspot.

CR-934 reduced core snapshot baseline position mapping coupling by extracting deterministic row
iteration, quantity/security normalization, cash/zero filtering, current snapshot versus history
market-value selection, missing-instrument fallback payloads, and instrument payload construction
into `core_snapshot_baseline_positions.py`. The helper module reports `A (45.13)` maintainability
and A-ranked helper complexity. `core_snapshot_service.py` shrank from 1,018 SLOC to 896 SLOC and
improved from `C (2.18)` to `C (6.12)`, but remains a C-ranked maintainability hotspot.

CR-935 reduced core snapshot projected-position policy coupling by extracting baseline-to-projected
copying, missing projected security-id discovery, new projected instrument payload construction,
transaction quantity mutation, baseline unit-value reuse, positive new-position pricing
requirements, and cash/zero filtering into `core_snapshot_projected_positions.py`. The helper
module reports `A (42.61)` maintainability and A-ranked helper complexity.
`core_snapshot_service.py` shrank from 896 SLOC to 789 SLOC and improved from `C (6.12)` to
`B (12.41)`, removing it from the active C-ranked maintainability hotspot list. The generated
`query_service/build` copy remains separate generated-surface debt and is not changed by this
slice.

CR-936 reduced reference-data repository query-helper coupling by extracting effective-window
filtering, reference status normalization, canonical series ranking, latest-effective row ranking,
DPM mandate binding ranking, model portfolio target ranking, and instrument eligibility ranking
into `reference_data_query_helpers.py`. The helper module reports `A (61.46)` maintainability and
A-ranked helper complexity. `reference_data_repository.py` shrank from 1,278 SLOC to 1,163 SLOC
and improved from `C (8.74)` to `B (9.24)`, removing it from the active C-ranked maintainability
hotspot list. The generated `query_service/build` copy remains separate generated-surface debt and
is not changed by this slice.

CR-937 reduced operations repository health-query coupling by extracting integer/latency
row-value normalization, support-job health thresholds, support-job aggregate and oldest-open
selectors, support-job health result shaping, analytics-export aggregate and oldest-open selectors,
and analytics-export health result shaping into `operations_health_queries.py`. The helper module
reports `A (49.26)` maintainability and A-ranked helper complexity. `operations_repository.py`
shrank from 2,684 SLOC to 2,522 SLOC, but remains `C (0.00)` under Radon maintainability and needs
additional focused extractions before it can leave the active C-ranked hotspot list.

CR-938 reduced operations repository missing-historical-FX diagnostic coupling by extracting the
base transaction query, aggregate missing-count and transaction-date range query, deterministic
sample query, sample-record normalization, and summary DTO construction into
`operations_missing_fx_queries.py`. The helper module reports `A (55.27)` maintainability and
A-ranked helper complexity. `operations_repository.py` shrank from 2,522 SLOC to 2,456 SLOC, but
remains `C (0.00)` under Radon maintainability and needs additional focused extractions before it
can leave the active C-ranked hotspot list.

CR-939 reduced operations repository lineage query coupling by extracting latest artifact-date
correlated subqueries, lineage artifact-gap classification, lineage priority ordering, and
lineage-key select construction into `operations_lineage_queries.py`. The helper module reports
`A (58.81)` maintainability and A-ranked helper complexity. `operations_repository.py` shrank from
2,456 SLOC to 2,388 SLOC, but remains `C (0.00)` under Radon maintainability and needs additional
focused extractions before it can leave the active C-ranked hotspot list.

CR-940 reduced operations repository position-scope query coupling by extracting load-run artifact
and job filtering, portfolio/security/epoch evidence filtering, current position-history scope
construction, current epoch snapshot scope construction, and latest transaction-date statement
construction into `operations_position_scope_queries.py`. The helper module reports `A (38.78)`
maintainability and A-ranked helper complexity. `operations_repository.py` shrank from 2,388 SLOC
to 2,211 SLOC, but remains `C (0.00)` under Radon maintainability and needs additional focused
extractions before it can leave the active C-ranked hotspot list.

CR-941 reduced operations repository load-run progress coupling by extracting scalar statement
construction, valuation and aggregation summary statement construction, valuation-to-position
timeseries handoff diagnostics, and `LoadRunProgressSummary` row shaping into
`operations_load_run_queries.py`. The helper module reports `A (44.96)` maintainability and
A-ranked helper complexity. `operations_repository.py` shrank from 2,211 SLOC to 1,832 SLOC, but
remains `C (0.00)` under Radon maintainability and needs additional focused extractions before it
can leave the active C-ranked hotspot list.

CR-942 reduced operations repository support-job scope coupling by extracting valuation and
aggregation job identity filters, business-date filters, security filters, status filters, and
composed job-scope helpers into `operations_support_job_queries.py`. The helper module reports
`A (43.44)` maintainability and A-ranked helper complexity. `operations_repository.py` shrank from
1,832 SLOC to 1,723 SLOC, but remains `C (0.00)` under Radon maintainability and needs additional
focused extractions before it can leave the active C-ranked hotspot list.

CR-943 reduced operations repository analytics-export scope coupling by extracting
analytics-export status normalization, stale/open job priority ordering, and composed job-scope
filtering into `operations_analytics_export_queries.py`. The helper module reports `A (55.97)`
maintainability and A-ranked helper complexity. `operations_repository.py` shrank from 1,723 SLOC
to 1,689 SLOC, but remains `C (0.00)` under Radon maintainability and needs additional focused
extractions before it can leave the active C-ranked hotspot list.

CR-944 reduced operations repository reconciliation-run scope coupling by extracting
reconciliation-run status normalization, failed/replay priority ordering, as-of filtering, identity
filtering, attribute filtering, and composed run-scope helpers into
`operations_reconciliation_run_queries.py`. The helper module reports `A (47.04)` maintainability
and A-ranked helper complexity. `operations_repository.py` shrank from 1,689 SLOC to 1,596 SLOC,
but remains `C (0.00)` under Radon maintainability and needs additional focused extractions before
it can leave the active C-ranked hotspot list.

CR-945 reduced operations repository portfolio-control scope coupling by extracting
portfolio-control status normalization, failed/replay priority ordering, identity filtering,
business-date filtering, and composed stage-scope helpers into
`operations_portfolio_control_queries.py`. The helper module reports `A (53.89)` maintainability
and A-ranked helper complexity. `operations_repository.py` shrank from 1,596 SLOC to 1,538 SLOC
and improved from `C (0.00)` to `C (0.21)`, but remains a C-ranked maintainability hotspot.

CR-946 reduced operations repository reprocessing scope coupling by extracting reprocessing status
normalization, stale-key priority ordering, reset-watermark job portfolio eligibility, payload
expression extraction, key filtering, and job filtering into `operations_reprocessing_queries.py`.
The helper module reports `A (43.47)` maintainability and A-ranked helper complexity.
`operations_repository.py` shrank from 1,538 SLOC to 1,403 SLOC and improved from `C (0.21)` to
`C (4.42)`, but remains a C-ranked maintainability hotspot.

CR-947 reduced operations repository reconciliation-finding query coupling by extracting run/as-of
filtering, finding/security/transaction filters, severity-priority ordering, summary select
construction, aggregate/top-blocking summary selection, and `ReconciliationFindingSummary` row
shaping into `operations_reconciliation_finding_queries.py`. The helper module reports `A (50.89)`
maintainability and A-ranked helper complexity. `operations_repository.py` shrank from 1,403 SLOC
to 1,332 SLOC and improved from `C (4.42)` to `C (6.24)`, but remains a C-ranked
maintainability hotspot.

CR-948 reduced operations repository support-job SQL helper coupling by extracting actionable
valuation-job filtering, superseding valuation-epoch detection, latest valuation-job lateral
selection, support-job priority ordering, and reusable security-id expression use into
`operations_support_job_queries.py` and `operations_position_scope_queries.py`. The expanded
support helper reports `A (35.97)` maintainability and A-ranked helper complexity.
`operations_repository.py` shrank from 1,332 SLOC to 1,247 SLOC and improved from `C (6.24)` to
`B (9.54)`, removing it from the active source C-ranked maintainability hotspot list. Generated
`query_service/build` copies remain separate generated-surface debt and are not changed by this
slice.

CR-949 reduced query-service reference integration DTO coupling by extracting the
transaction-cost curve and benchmark market-series DTO families into
`reference_integration_transaction_cost_dto.py` and
`reference_integration_benchmark_market_series_dto.py`, with compatibility re-exports from the
original module. The extracted modules report `A (37.79)` and `A (38.91)` maintainability.
`reference_integration_dto.py` shrank from 3,637 SLOC to 3,264 SLOC and improved from `C (0.00)`
to `C (1.33)`, but remains a C-ranked maintainability hotspot requiring further DTO-family
extractions.

CR-950 reduced query-service reference integration DTO coupling by extracting the market-data
coverage DTO family into `reference_integration_market_data_coverage_dto.py`, with compatibility
re-exports from the original module before DPM readiness DTOs. The extracted module reports
`A (35.77)` maintainability. `reference_integration_dto.py` shrank from 3,264 SLOC to 3,078 SLOC
and improved from `C (1.33)` to `C (4.62)`, but remains a C-ranked maintainability hotspot.

CR-951 reduced query-service reference integration DTO coupling by extracting the portfolio
tax-lot window DTO family into `reference_integration_portfolio_tax_lot_dto.py`, with
compatibility re-exports from the original module after shared paging DTOs are defined. The
extracted module reports `A (41.65)` maintainability. `reference_integration_dto.py` shrank from
3,078 SLOC to 2,922 SLOC and improved from `C (4.62)` to `C (6.70)`, but remains a C-ranked
maintainability hotspot.

CR-952 reduced query-service reference integration DTO coupling by extracting the instrument
eligibility and DPM source-readiness DTO families into
`reference_integration_instrument_eligibility_dto.py` and
`reference_integration_dpm_source_readiness_dto.py`, with compatibility re-exports from the
original module. The extracted modules report `A (41.20)` and `A (42.75)` maintainability.
`reference_integration_dto.py` shrank from 2,922 SLOC to 2,639 SLOC and improved from `C (6.70)`
to `B (11.49)`, removing it from the active non-generated C-ranked source hotspot list.

CR-953 reduced ingestion job record-status coupling by extracting failed-record-key normalization
and endpoint-specific replayable-key extraction into `ingestion_record_status.py`.
`get_job_record_status` improved from `C (20)` to `A (4)`, while the helper module reports
`A (59.21)` maintainability. `ingestion_job_service.py` shrank from 1,656 SLOC to 1,633 SLOC and
remains a C-ranked maintainability hotspot requiring additional focused extractions.

CR-954 reduced ingestion operating-band policy coupling by extracting operating-band policy,
signal, decision, and classification helpers into `ingestion_operating_band.py`. The extracted
classifier moved out of the service and now reports `B (7)` in an `A (50.49)` helper module.
`ingestion_job_service.py` shrank from 1,633 SLOC to 1,545 SLOC and remains a C-ranked
maintainability hotspot requiring additional focused extractions.

CR-955 reduced ingestion SLO status coupling by extracting DB aggregate/fallback snapshot loading
and threshold response assembly into `ingestion_slo_status.py`. `get_slo_status` improved from
`C (17)` to `A (3)`, while the helper module reports `A (42.76)` maintainability.
`ingestion_job_service.py` shrank from 1,545 SLOC to 1,477 SLOC and remains a C-ranked
maintainability hotspot requiring additional focused extractions.

CR-956 reduced ingestion backlog breakdown coupling by extracting grouped row normalization,
ordering, concentration-share calculation, and response assembly into `ingestion_backlog_breakdown.py`.
`get_backlog_breakdown` improved from `C (13)` to `A (3)`, while the helper module reports
`A (51.73)` maintainability. `ingestion_job_service.py` shrank from 1,477 SLOC to 1,419 SLOC and
improved from `C (0.00)` to `C (0.81)`, but remains a C-ranked maintainability hotspot.

CR-957 reduced ingestion job listing coupling by extracting filter, cursor lookup, statement
building, and page-slicing helpers into `ingestion_job_listing.py`. `list_jobs` improved from
`C (11)` to `A (4)`, removing the final C-ranked method from `ingestion_job_service.py`. The
service reports `C (2.32)` maintainability, while the helper module reports `A (46.25)`.

CR-958 reduced reference-data tax rule validation coupling by extracting effective-window,
threshold-pair, and bounded-evidence helpers inside `reference_data_dto.py`.
`ClientTaxRuleSetRecord.validate_rule` improved from `C (12)` to `A (1)`, removing the only
C-ranked method from `reference_data_dto.py`. The module remains `C (0.00)` because of size and
remaining B-ranked DTO classes/validators.

CR-959 reduced reference-data tax DTO coupling by extracting the client tax profile and tax
rule-set DTO family into `reference_data_tax_dto.py`, with compatibility re-exports from
`reference_data_dto.py`. The extracted module reports `A (29.60)` maintainability.
`reference_data_dto.py` shrank from 1,686 SLOC to 1,511 SLOC and improved from `C (0.00)` to
`C (1.05)`, but remains an active C-ranked maintainability hotspot requiring additional DTO-family
extractions.

CR-960 reduced reference-data client preference DTO coupling by extracting the client restriction
and sustainability preference DTO family into `reference_data_client_preference_dto.py`, with
compatibility assignments from `reference_data_dto.py`. The extracted module reports `A (32.04)`
maintainability. `reference_data_dto.py` shrank from 1,511 SLOC to 1,376 SLOC and improved from
`C (1.05)` to `C (6.43)`, but remains an active C-ranked maintainability hotspot requiring
additional DTO-family extractions.

CR-961 reduced reference-data instrument eligibility DTO coupling by extracting the instrument
eligibility profile DTO family into `reference_data_instrument_eligibility_dto.py`, with
compatibility assignments from `reference_data_dto.py`. The extracted module reports `A (40.98)`
maintainability. `reference_data_dto.py` shrank from 1,376 SLOC to 1,282 SLOC and improved from
`C (6.43)` to `B (9.31)`, removing it from the active non-generated C-ranked source hotspot list.

CR-962 reduced ingestion capacity-status coupling by extracting capacity group derivation and
capacity response loading into `ingestion_capacity_status.py`. `get_capacity_status` improved from
`B (9)` to `A (1)`, while the helper module reports `A (43.64)` maintainability.
`ingestion_job_service.py` shrank from 1,420 SLOC to 1,304 SLOC and improved from `C (2.32)` to
`C (5.70)`, but remains the remaining active non-generated C-ranked source hotspot.

CR-963 reduced ingestion error-budget status coupling by extracting default and loaded
error-budget response assembly into `ingestion_error_budget_status.py`. `get_error_budget_status`
improved from `B (9)` to `A (1)`, while the helper module reports `A (47.37)` maintainability.
`ingestion_job_service.py` shrank from 1,304 SLOC to 1,207 SLOC and improved from `C (5.70)` to
`C (8.17)`, but remains the remaining active non-generated C-ranked source hotspot.

CR-964 reduced ingestion retry guardrail coupling by extracting deterministic retry-policy
enforcement into `ingestion_retry_guardrails.py`. `assert_retry_allowed_for_records` improved from
`B (9)` to `A (1)`, while the helper module reports `A (59.19)` maintainability.
`ingestion_job_service.py` shrank from 1,207 SLOC to 1,200 SLOC and improved from `C (8.17)` to
`B (9.82)`, clearing the active non-generated C-ranked source hotspot list.

CR-965 reduced ingestion reprocessing queue-health coupling by extracting SQL aggregation and
queue response assembly into `ingestion_reprocessing_queue_health.py`.
`get_reprocessing_queue_health` improved from `B (7)` to `A (1)`, while the helper module reports
`A (51.01)` maintainability. `ingestion_job_service.py` shrank from 1,200 SLOC to 1,137 SLOC and
improved from `B (9.82)` to `B (11.79)`.

CR-966 reduced ingestion replay-audit list coupling by extracting optional filter construction,
bounded ordering, database reads, and DTO mapping into `ingestion_replay_audits.py`.
`list_replay_audits` improved from `B (7)` to `A (1)`, while the helper module reports
`A (72.80)` maintainability. `ingestion_job_service.py` shrank from 1,137 SLOC to 1,116 SLOC and
improved from `B (11.79)` to `B (12.63)`.

CR-967 reduced ingestion consumer-lag coupling by extracting DLQ aggregate loading, lag severity
classification, backlog summary stitching, and response assembly into `ingestion_consumer_lag.py`.
`get_consumer_lag` improved from `B (6)` to `A (1)`, while the helper module reports
`A (55.85)` maintainability. `ingestion_job_service.py` shrank from 1,116 SLOC to 1,077 SLOC and
improved from `B (12.63)` to `B (13.77)`.

CR-968 reduced ingestion health-summary coupling by extracting aggregate counts, oldest-backlog
lookup, backlog total calculation, and response assembly into `ingestion_health_summary.py`.
`get_health_summary` improved from `B (6)` to `A (1)`, while the helper module reports
`A (60.46)` maintainability. `ingestion_job_service.py` shrank from 1,077 SLOC to 1,045 SLOC and
improved from `B (13.77)` to `B (15.15)`.

CR-969 reduced ingestion idempotency-diagnostics coupling by extracting aggregate loading, endpoint
normalization, collision detection, and response assembly into
`ingestion_idempotency_diagnostics.py`. `get_idempotency_diagnostics` improved from `B (7)` to
`A (1)`, while the helper module reports `A (59.15)` maintainability. `ingestion_job_service.py`
shrank from 1,045 SLOC to 990 SLOC and improved from `B (15.15)` to `B (16.96)`, with no
B-ranked methods remaining in the service.

CR-970 reduced shared event supportability catalog validation complexity by extracting focused
validators for schema models, unique-name recording, event definitions, governance flags,
source/evidence links, evidence bundles, source-data products, supportability surfaces, direct
Kafka topics, and direct-topic headers. `validate_event_supportability_catalog` improved from
`E (39)` to `A (5)`, all extracted helper functions report A-ranked complexity, and
`event_supportability.py` remains `A (26.87)` maintainability.

CR-971 reduced source-data security profile validation complexity by extracting focused validators
for profile-name recording, classification allowlists, tenant and entitlement scope requirements,
operator-only policy, audit mapping, retention mapping, route-family compatibility, PII-field
checks, and catalog coverage. `_validate_source_data_security_profiles` improved from `D (25)` to
`A (4)`, all touched helper functions report A-ranked complexity, and `source_data_security.py`
remains `A (29.23)` maintainability.

CR-972 reduced shared outbox dispatcher batch orchestration complexity by extracting focused
helpers for event publishing, flush-result accounting, delivery-result classification, success
persistence, retryable failure persistence, terminal failure persistence, delivery callback
creation, event headers, event payloads, and callback-less failure accounting.
`OutboxDispatcher._process_batch_sync` improved from `E (33)` to `A (2)`, all dispatcher methods
and outbox helper functions report A-ranked complexity, and `outbox_dispatcher.py` remains
`A (40.41)` maintainability.

CR-973 reduced enterprise readiness runtime policy complexity by extracting focused helpers for
runtime issue collection, secret-rotation validation, authorization enablement, capability-rule
requirements, header normalization, required-header checks, service identity checks, capability
parsing, feature-flag lookup, redaction, capability-rule normalization, and path-template matching.
`validate_enterprise_runtime_config` improved from `C (14)` to `A (5)`, `authorize_request`
improved from `C (18)` to `A (4)`, and every enterprise readiness function/class/method now
reports A-ranked complexity.

CR-974 reduced canonical FX transaction validation complexity by extracting focused helpers for
normalized control codes, control-code validation, component identity, zero quantity/price policy,
settlement-date policy, currency-pair policy, quote convention policy, positive amount/rate
policy, strict metadata, cash settlement components, contract identifiers, swap structure,
optional policy modes, and realized P&L fields. `validate_fx_transaction` improved from `E (37)`
to `A (1)`, every FX validation function/class reports A-ranked complexity, and
`fx_validation.py` remains `A (27.02)` maintainability.

CR-975 reduced canonical INTEREST transaction validation complexity by extracting focused helpers
for transaction-type validation, settlement-date presence, zero quantity/price policy, gross
amount policy, interest direction, nonnegative deductions, net interest reconciliation, currency
fields, date ordering, strict metadata, cash-entry policy, settlement cash-account requirements,
and external cash-link requirements. `validate_interest_transaction` improved from `D (29)` to
`A (1)`, every INTEREST validation function/class reports A-ranked complexity, and
`interest_validation.py` remains `A (33.41)` maintainability.

CR-976 reduced canonical SELL transaction validation complexity by extracting focused helpers for
transaction-type validation, settlement-date presence, positive quantity policy, positive
gross-amount policy, currency fields, date ordering, strict linkage metadata, and strict policy
metadata. `validate_sell_transaction` improved from `C (14)` to `A (1)`, every SELL validation
function/class reports A-ranked complexity, and `sell_validation.py` remains `A (42.80)`
maintainability.

CR-977 reduced canonical BUY transaction validation complexity by extracting focused helpers for
transaction-type validation, settlement-date presence, positive quantity policy, positive
gross-amount policy, currency fields, date ordering, strict linkage metadata, and strict policy
metadata. `validate_buy_transaction` improved from `C (14)` to `A (1)`, every BUY validation
function/class reports A-ranked complexity, and `buy_validation.py` remains `A (42.80)`
maintainability.

CR-978 reduced canonical DIVIDEND transaction validation complexity by extracting focused helpers
for transaction-type validation, settlement-date presence, zero quantity, zero price, positive
gross-amount policy, currency fields, date ordering, strict linkage metadata, strict policy
metadata, cash-entry policy, auto-generated cash-entry requirements, and upstream-provided
cash-entry requirements. `validate_dividend_transaction` improved from `D (21)` to `A (1)`, every
DIVIDEND validation function/class reports A-ranked complexity, and `dividend_validation.py`
remains `A (37.73)` maintainability.

CR-979 reduced CA Bundle A transaction validation complexity by extracting focused helpers for
transaction-type validation, parent event reference validation, linkage identifier validation,
source instrument validation, target instrument validation, cash-consideration link orchestration,
cash-link presence, and cash-link consistency. `validate_ca_bundle_a_transaction` improved from
`D (22)` to `A (2)`, every CA Bundle A validation function/class reports A-ranked complexity, and
`ca_bundle_a_validation.py` remains `A (38.16)` maintainability.

CR-980 reduced adjustment cash-leg helper complexity by extracting focused helpers for adjustment
resolver dispatch, BUY/SELL/DIVIDEND/INTEREST amount policy, net interest resolution, interest
movement direction, AUTO_GENERATE eligibility assertion, cash-account resolution, cash-instrument
resolution, generated linkage metadata, and adjustment cash-leg event assembly.
`_resolve_adjustment_amount_and_direction` improved from `C (11)` to `A (3)`,
`build_auto_generated_adjustment_cash_leg` improved from `B (9)` to `A (1)`, every adjustment
cash-leg function/class reports A-ranked complexity, and `adjustment_cash_leg.py` remains
`A (37.29)` maintainability.

CR-981 reduced upstream cash-leg pairing validation complexity by extracting focused helpers for
product-leg cash-entry mode, portfolio matching, external cash transaction ID matching, cash-leg
transaction type, cash-leg gross amount, economic event ID, and linked transaction group ID.
`validate_upstream_cash_leg_pairing` improved from `C (12)` to `A (1)`, every dual-leg pairing
function/class reports A-ranked complexity, and `dual_leg_pairing.py` remains `A (56.95)`
maintainability.

CR-982 reduced FX baseline processing complexity by extracting focused helpers for decimal
defaulting, base FX processing update assembly, realized P&L mode dispatch, zero realized P&L
update assembly, upstream-provided realized P&L update assembly, and total P&L fallback
resolution. `build_fx_processed_event` improved from `C (14)` to `A (2)`, every FX baseline
processing function reports A-ranked complexity, and `fx_baseline_processing.py` remains
`A (65.60)` maintainability.

CR-983 reduced FX contract instrument construction complexity by extracting focused helpers for
FX contract ID resolution, contract currency normalization, pair label resolution, display-name
construction, and final `InstrumentEvent` assembly. `build_fx_contract_instrument_event` improved
from `C (13)` to `A (5)`, every FX contract instrument function reports A-ranked complexity, and
`fx_contract_instrument.py` remains `A (51.08)` maintainability.

CR-984 reduced FX linkage enrichment complexity by extracting focused helpers for contract ID
decision predicates, open/close lifecycle transaction IDs, FX metadata update assembly, core
linkage update fields, contract linkage update fields, instrument lifecycle update fields, and FX
processing mode update fields. `enrich_fx_transaction_metadata` improved from `B (7)` to `A (2)`,
`_resolve_fx_contract_id` improved from `B (6)` to `A (4)`, and
`_resolve_contract_lifecycle_transaction_ids` improved from `B (7)` to `A (3)`. Every FX linkage
function reports A-ranked complexity, and `fx_linkage.py` remains `A (42.62)` maintainability.

CR-985 reduced BUY linkage enrichment complexity by extracting focused helpers for BUY transaction
eligibility, BUY linkage ID resolution, BUY policy ID resolution, and BUY metadata update
assembly. `enrich_buy_transaction_metadata` improved from `B (6)` to `A (2)`, every BUY linkage
function reports A-ranked complexity, and `buy_linkage.py` remains `A (73.51)` maintainability.

CR-986 reduced SELL linkage enrichment complexity by extracting focused helpers for SELL
transaction eligibility, SELL linkage ID resolution, SELL policy ID resolution, cost-basis policy
selection, and SELL metadata update assembly. `enrich_sell_transaction_metadata` improved from
`B (7)` to `A (2)`, every SELL linkage function reports A-ranked complexity, and
`sell_linkage.py` remains `A (67.86)` maintainability.

CR-987 reduced INTEREST linkage enrichment complexity by extracting focused helpers for INTEREST
transaction eligibility, INTEREST linkage ID resolution, INTEREST policy ID resolution, and
INTEREST metadata update assembly. `enrich_interest_transaction_metadata` improved from `B (6)` to
`A (2)`, every INTEREST linkage function reports A-ranked complexity, and `interest_linkage.py`
remains `A (71.82)` maintainability.

CR-988 reduced DIVIDEND linkage enrichment complexity by extracting focused helpers for DIVIDEND
transaction eligibility, DIVIDEND linkage ID resolution, DIVIDEND policy ID resolution, and
DIVIDEND metadata update assembly. `enrich_dividend_transaction_metadata` improved from `B (6)` to
`A (2)`, every DIVIDEND linkage function reports A-ranked complexity, and `dividend_linkage.py`
remains `A (71.82)` maintainability.

CR-989 reduced CA Bundle A reconciliation complexity by extracting a focused reconciliation
accumulator plus helpers for event accumulation, source-leg accumulation, target-leg accumulation,
and reconciliation status resolution. `evaluate_ca_bundle_a_reconciliation` improved from
`B (8)` to `A (2)`, every CA Bundle A reconciliation function/class reports A-ranked complexity,
and `ca_bundle_a_reconciliation.py` remains `A (39.54)` maintainability.

CR-990 reduced CA Bundle A dependency ordering complexity by replacing repeated source-out,
target-in, cash-consideration, rights-stage, and refund rank branches with explicit rank-type sets
and a deterministic dependency-rank lookup. `ca_bundle_a_dependency_rank` improved from `B (8)` to
`A (1)`, every CA Bundle A ordering function reports A-ranked complexity, and
`ca_bundle_a_ordering.py` remains `A (89.61)` maintainability.

CR-991 reduced analytics cashflow semantics classifier complexity by replacing repeated fixed
classification branches with a typed static semantics map and a focused transfer-flow helper.
`classify_analytics_cash_flow` improved from `B (10)` to `A (3)`, every analytics cashflow
semantics function reports A-ranked complexity, and `analytics_cashflow_semantics.py` remains
`A (74.86)` maintainability.

CR-992 reduced market reference point classifier complexity by extracting explicit
pre-observation and observed-status maps plus a focused point-status helper.
`classify_market_reference_point` improved from `B (8)` to `A (1)`, every market reference quality
function/class reports A-ranked complexity, and `market_reference_quality.py` remains `A (36.36)`
maintainability.

CR-993 reduced reconciliation quality classifier complexity by extracting validation helpers,
status-decision helpers, a run-status classification map, and small blocking/partial predicates.
`classify_reconciliation_status` improved from `B (9)` to `A (2)`,
`classify_data_quality_coverage` improved from `B (7)` to `A (1)`, every reconciliation quality
function/class reports A-ranked complexity, and `reconciliation_quality.py` remains `A (33.27)`
maintainability.

CR-994 reduced ingestion outcome classifier complexity by extracting count validation,
terminal-failure counting, partial-outcome detection, and valid-outcome classification helpers.
`classify_ingestion_outcome` improved from `B (6)` to `A (1)`, every ingestion evidence
function/class reports A-ranked complexity, and `ingestion_evidence.py` remains `A (37.92)`
maintainability.

CR-995 reduced reconstruction identity scope payload complexity by extracting reconstruction scope
validation and transaction-window validation helpers. `_canonical_scope_payload` improved from
`B (7)` to `A (1)`, every reconstruction identity function/class reports A-ranked complexity, and
`reconstruction_identity.py` remains `A (44.37)` maintainability.

CR-996 reduced database URL scheme normalization complexity by extracting legacy-postgres,
async-driver, sync-driver, and scheme-replacement helpers. `_normalize_database_url_scheme`
improved from `B (6)` to `A (2)`, every shared DB helper function reports A-ranked complexity, and
`db.py` remains `A (66.86)` maintainability.

CR-997 reduced Kafka topic verification complexity by extracting admin-client construction,
required-topic verification, existing-topic metadata lookup, and missing-topic calculation helpers.
`ensure_topics_exist` improved from `B (6)` to `A (3)`, every Kafka admin helper function/class
reports A-ranked complexity, and `kafka_admin.py` remains `A (88.15)` maintainability.

CR-998 reduced shared config integer environment parsing complexity by extracting safe-default,
environment-loading, and minimum-enforcement helpers. `_env_int` improved from `B (7)` to
`A (1)`, each extracted integer parsing helper reports A-ranked complexity, and `config.py`
remains `A (35.12)` maintainability.

CR-999 reduced Kafka consumer config value coercion complexity by extracting type-specific
coercion, integer parsing, positive-integer enforcement, and `auto.offset.reset` normalization
helpers. `_coerce_consumer_config_value` improved from `C (16)` to `A (4)`, each extracted
consumer coercion helper reports A-ranked complexity, and `config.py` remains `A (34.38)`
maintainability.

CR-1000 reduced Kafka consumer runtime override loading complexity by extracting defaults loading,
group override loading, group sanitization, and group-context helpers.
`get_kafka_consumer_runtime_overrides` improved from `B (7)` to `A (1)`, the extracted runtime
override loading helpers report A-ranked complexity, and `config.py` remains `A (33.36)`
maintainability.

CR-1001 reduced Kafka consumer DLQ reason classification complexity by replacing repeated branch
token checks with explicit ordered token groups and focused matching helpers.
`classify_dlq_reason_code` improved from `C (12)` to `A (5)`, direct taxonomy tests now cover
validation, data-integrity, timeout, authorization, and unclassified outcomes, and
`kafka_consumer.py` remains `A (38.68)` maintainability.

CR-1002 reduced Kafka consumer message-correlation context complexity by extracting current/header/
fallback selection helpers. `BaseConsumer._message_correlation_context` improved from `B (7)` to
`A (3)`, direct tests now prove existing-context preservation, header-before-fallback precedence,
and explicit fallback preference, and `kafka_consumer.py` remains `A (37.37)` maintainability.

CR-1003 reduced Kafka consumer DLQ publication complexity by extracting payload, header, publish,
delivery-confirmation, and key-decoding helpers. `BaseConsumer._send_to_dlq_async` improved from
`B (10)` to `A (5)`, the extracted DLQ publication helpers report A-ranked complexity, and
`kafka_consumer.py` remains `A (34.02)` maintainability.

CR-1004 reduced Kafka consumer shutdown complexity by extracting shutdown log-context, consumer
wakeup, consumer close, and DLQ producer flush helpers. `BaseConsumer.shutdown` improved from
`B (8)` to `A (3)`, tests now prove wakeup failure continuation and close failure logging, and
`kafka_consumer.py` remains `A (31.86)` maintainability.

CR-1005 reduced Kafka consumer run-loop commit policy complexity by extracting
successful-processing commit, successful-DLQ-publication commit, DLQ-publication-failure logging,
and message log-context helpers. `BaseConsumer.run` improved from `C (18)` to `C (13)`, the
extracted commit-policy helpers report A-ranked complexity, and `kafka_consumer.py` remains
`A (31.23)` maintainability. The run loop remains a C-ranked orchestration hotspot for a separate
follow-up slice.

CR-1006 reduced Kafka consumer run-loop orchestration complexity by extracting poll-error handling,
per-message processing, sync/async dispatch, retryable and terminal processing-error handling, and
processing metrics helpers. `BaseConsumer.run` improved from `C (13)` to `A (5)`,
`_process_polled_message` reports `A (4)`, direct tests now cover fatal and non-fatal consumer poll
errors, and `kafka_consumer.py` remains `A (28.49)` maintainability.

CR-1007 reduced runtime supervision failure attribution complexity by extracting completed-task
selection, exception-task selection, cancelled-task selection, and runtime-error construction
helpers. `wait_for_shutdown_or_task_failure` improved from `C (15)` to `A (5)`, the extracted
failure-attribution helpers report A-ranked complexity, and `runtime_supervision.py` remains
`A (56.39)` maintainability. `shutdown_runtime_components` remains a separate C-ranked teardown
hotspot for a later slice.

CR-1008 reduced runtime supervision teardown complexity by extracting consumer shutdown,
stop-callback execution, server exit signaling, runtime-task awaiting, timeout logging, timed-out
task-name extraction, pending-task cancellation, and teardown error logging helpers.
`shutdown_runtime_components` improved from `C (18)` to `A (1)`, every function in
`runtime_supervision.py` now reports A-ranked cyclomatic complexity, and the module remains
`A (51.77)` maintainability.

CR-1009 reduced shared OpenAPI inference policy complexity by extracting known-key examples, enum
examples, typed examples, formatted examples, rule-based description selection, and description
predicate/formatter helpers. `infer_example` improved from `C (11)` to `A (3)`,
`infer_description` improved from `C (14)` to `A (2)`, and direct OpenAPI enrichment tests now pin
example and description precedence.

CR-1010 reduced shared OpenAPI example classifier complexity by replacing repeated numeric and
string-like token checks with explicit token-rule tables and focused token-matching helpers.
`_infer_number_example` improved from `B (8)` to `A (3)`, `_infer_string_like_example` improved
from `B (8)` to `A (4)`, and `openapi_examples.py` improved from `B (16.35)` to `B (17.47)`
maintainability.

CR-1011 reduced shared OpenAPI typed-example dispatch complexity by replacing repeated type
branches with static and dynamic typed-example maps plus focused array, integer, and number builder
helpers. `_typed_example` improved from `B (6)` to `A (3)`, and `openapi_examples.py` improved
from `B (17.47)` to `B (17.91)` maintainability.

CR-1012 reduced shared OpenAPI union example builder complexity by extracting union variant lookup,
union-key dispatch, and non-empty allOf normalization helpers. `_build_union_example` improved from
`B (8)` to `A (4)`, with direct allOf and oneOf tests pinning existing generated example behavior.

CR-1013 reduced shared OpenAPI object example builder complexity by extracting schema-property,
required-property, property-example, and property-inclusion helpers. `_build_object_example`
improved from `B (7)` to `A (4)`, with direct tests pinning the existing generic fallback behavior
for empty object properties.

CR-1014 reduced shared OpenAPI schema example orchestration complexity by extracting candidate
selection, structured-schema, fallback-example, and fallback property-name helpers.
`build_schema_example` improved from `B (10)` to `A (4)`, leaving every function in
`openapi_examples.py` A-ranked by cyclomatic complexity.
