# lotus-core Quality Scorecard

Status: Initial scorecard baseline on 2026-06-02.

| Category | Current Baseline | Target Direction |
| --- | --- | --- |
| Python code size | 1,040 files / 213,290 lines under `src` and `tests` | Reduce generated/duplicated quality surface and split large modules |
| Ruff findings | 0 findings under `python -m ruff check . --statistics`; enforced by `make quality-ruff-gate` and the quality-baseline Ruff regression job | Keep Ruff lint regression-free while broader gates continue to ratchet |
| Ruff format | Clean and enforced by `make quality-ruff-format-gate` plus the quality-baseline Ruff format job after CR-866 | Keep Ruff formatting regression-free while broader gates continue to ratchet |
| Typecheck | Clean for the configured query-service DTO/router scope under `make typecheck`; enforced by the quality-baseline typecheck job after CR-869 | Expand typed source scope progressively without weakening the gate |
| Test collection | Full all-suite collection reaches the governed mixed-runtime guard; `make quality-unit-collection-gate` cleanly collects 2,964 runtime-safe unit tests and is enforced by the quality-baseline workflow after CR-1078 | Add further runtime-separated collection lanes only when they match the repo's test-manifest model |
| Coverage | `make coverage-gate` now passes after CR-969 with branch-aware combined unit + integration-lite coverage at 98% (`2,918` unit tests plus `121` integration-lite tests; threshold `98`) | Keep coverage gate regression-free and broaden runtime-separated coverage evidence for PR Merge Gate |
| Complexity | Broad source Xenon gate is clean and enforced after CR-882 with `make quality-complexity-gate`; CR-880 reduced advisory proposal simulation from F to B, CR-881 reduced the cost-calculator consumer from F to C, CR-882 reduced FX linkage from D to B, CR-885 reduced `get_load_run_progress` from D to A, CR-886 reduced `_apply_reconciliation_run_scope` from C to A, CR-887 reduced `_apply_valuation_job_scope` from B to A, CR-888 reduced `_apply_aggregation_job_scope` from B to A, CR-889 reduced `_apply_portfolio_control_stage_scope` from B to A, CR-890 reduced `_apply_reprocessing_job_scope` from B to A, CR-891 reduced `_apply_current_position_history_scope` from B to A, CR-892 reduced valuation and aggregation health summary methods from B to A, CR-893 reduced analytics export health summary from B to A, CR-894 reduced missing historical FX dependency summary from B to A, CR-895 reduced `get_lineage_keys` from B to A, removing the remaining B-ranked method from `operations_repository.py`, CR-896 reduced `list_latest_fx_rates` from B to A, CR-897 reduced `list_dpm_portfolio_universe_candidates` from B to A, CR-898 reduced operations runtime-state wrapper methods to A-ranked complexity, CR-899 reduced `get_position_timeseries` from E to C, CR-900 reduced `get_core_snapshot` from E to A, CR-901 reduced `_resolve_projected_positions` from E to A, CR-902 reduced `_resolve_baseline_positions` from D to A, CR-903 reduced `get_instrument_enrichment_bulk` from C to A, CR-904 reduced `_validated_simulation_session` from B to A, CR-905 reduced `_build_delta_section` from B to A, CR-906 removed the final B-ranked method from `core_snapshot_service.py`, CR-908 reduced `_portfolio_observation_rows` from D to A, CR-909 reduced `_effective_beginning_market_value` from C to A, CR-910 reduced `_latest_available_performance_date` from C to A, CR-911 reduced `_resolve_window` from C to A, CR-912 reduced `get_portfolio_timeseries` from C to A, CR-913 reduced `get_position_timeseries` from C to A, CR-914 reduced `create_export_job` from B to A, CR-915 reduced `_reserve_export_job` from B to A, CR-916 reduced `_jsonable` from B to A, CR-917 reduced `get_export_result_ndjson` from B to A, and CR-918 kept extracted analytics export job helpers A-ranked | Keep broad complexity regression-free while reducing remaining B/C hotspots by domain priority |
| Maintainability | No D/E/F source modules; enforced after CR-879 by `make quality-maintainability-gate`; CR-883 removed `openapi_enrichment.py` from the C-ranked hotspot list, CR-884 improved `reference_data_repository.py` from `C (4.26)` to `C (6.94)`, CR-896 improved it again to `C (7.55)`, CR-897 improved it again to `C (8.74)`, CR-898 improved `operations_service.py` from `C (5.44)` to `B (9.91)`, reducing the C-hotspot count from 8 to 7, CR-907 extracted an A-ranked `core_snapshot_calculations.py` module while reducing `core_snapshot_service.py` from 1,208 SLOC / 518 LLOC to 1,093 SLOC / 464 LLOC, CR-918 extracted A-ranked `analytics_export_jobs.py` while reducing `analytics_timeseries_service.py` from 1,844 SLOC to 1,770 SLOC, CR-919 extracted A-ranked `analytics_page_tokens.py` while reducing `analytics_timeseries_service.py` to 1,751 SLOC, CR-920 extracted A-ranked `analytics_windows.py` while reducing `analytics_timeseries_service.py` to 1,707 SLOC, CR-921 extracted A-ranked `analytics_cash_flows.py` while reducing `analytics_timeseries_service.py` to 1,590 SLOC, CR-922 extracted A-ranked `analytics_fx_rates.py` while reducing `analytics_timeseries_service.py` to 1,582 SLOC, CR-923 extracted A-ranked `analytics_pagination.py` while reducing `analytics_timeseries_service.py` to 1,548 SLOC, CR-924 extracted A-ranked `analytics_quality.py` while reducing `analytics_timeseries_service.py` to 1,536 SLOC, CR-925 extracted A-ranked `analytics_position_pages.py` while reducing `analytics_timeseries_service.py` to 1,523 SLOC, CR-926 extracted A-ranked `analytics_portfolio_pages.py` while reducing `analytics_timeseries_service.py` to 1,513 SLOC and improving it to `C (1.52)`, CR-927 extracted A-ranked `analytics_position_responses.py` while reducing `analytics_timeseries_service.py` to 1,424 SLOC and improving it to `C (3.48)`, CR-928 extracted A-ranked `analytics_export_execution.py` while reducing `analytics_timeseries_service.py` to 1,402 SLOC and improving it to `C (5.40)`, CR-929 extracted A-ranked `analytics_export_lifecycle.py` while keeping `analytics_timeseries_service.py` at 1,402 SLOC and improving it to `C (6.86)`, CR-930 extracted A-ranked `analytics_export_results.py` while reducing `analytics_timeseries_service.py` to 1,388 SLOC and improving it to `C (7.80)`, CR-931 removed stale analytics quality wrapper methods while reducing the active service to 1,325 SLOC and improving it to `B (9.21)`, CR-932 extracted A-ranked `core_snapshot_instrument_enrichment.py` while reducing `core_snapshot_service.py` to 1,067 SLOC, CR-933 extracted A-ranked `core_snapshot_baseline_metadata.py` while reducing `core_snapshot_service.py` to 1,018 SLOC and improving it to `C (2.18)`, CR-934 extracted A-ranked `core_snapshot_baseline_positions.py` while reducing `core_snapshot_service.py` to 896 SLOC and improving it to `C (6.12)`, CR-935 extracted A-ranked `core_snapshot_projected_positions.py` while reducing `core_snapshot_service.py` to 789 SLOC and improving it to `B (12.41)`, CR-936 extracted A-ranked `reference_data_query_helpers.py` while reducing `reference_data_repository.py` to 1,163 SLOC and improving it to `B (9.24)`, CR-937 extracted A-ranked `operations_health_queries.py` while reducing `operations_repository.py` from 2,684 SLOC to 2,522 SLOC, CR-938 extracted A-ranked `operations_missing_fx_queries.py` while reducing `operations_repository.py` to 2,456 SLOC, CR-939 extracted A-ranked `operations_lineage_queries.py` while reducing `operations_repository.py` to 2,388 SLOC, CR-940 extracted A-ranked `operations_position_scope_queries.py` while reducing `operations_repository.py` to 2,211 SLOC, CR-941 extracted A-ranked `operations_load_run_queries.py` while reducing `operations_repository.py` to 1,832 SLOC, CR-942 extracted A-ranked `operations_support_job_queries.py` while reducing `operations_repository.py` to 1,723 SLOC, CR-943 extracted A-ranked `operations_analytics_export_queries.py` while reducing `operations_repository.py` to 1,689 SLOC, CR-944 extracted A-ranked `operations_reconciliation_run_queries.py` while reducing `operations_repository.py` to 1,596 SLOC, CR-945 extracted A-ranked `operations_portfolio_control_queries.py` while reducing `operations_repository.py` to 1,538 SLOC and improving it to `C (0.21)`, CR-946 extracted A-ranked `operations_reprocessing_queries.py` while reducing `operations_repository.py` to 1,403 SLOC and improving it to `C (4.42)`, CR-947 extracted A-ranked `operations_reconciliation_finding_queries.py` while reducing `operations_repository.py` to 1,332 SLOC and improving it to `C (6.24)`, CR-948 expanded A-ranked support-job helpers while reducing `operations_repository.py` to 1,247 SLOC and improving it to `B (9.54)`, CR-952 extracted A-ranked instrument eligibility and DPM source-readiness DTO modules while reducing `reference_integration_dto.py` to 2,639 SLOC and improving it to `B (11.49)`, CR-961 extracted an A-ranked instrument eligibility DTO module while improving `reference_data_dto.py` to `B (9.31)`, CR-969 improved `ingestion_job_service.py` to `B (16.96)` with no remaining B-ranked service methods, CR-1035 extracted an A-ranked model-portfolio DTO module while improving `reference_data_dto.py` to `B (12.49)`, CR-1036 extracted an A-ranked support-reference DTO module while improving `reference_data_dto.py` to `B (14.29)`, CR-1037 extracted an A-ranked benchmark/index DTO module while improving `reference_data_dto.py` to `A (21.98)`, CR-1038 extracted an A-ranked mandate DTO module while improving `reference_data_dto.py` to `A (27.76)`, CR-1039 moved model-portfolio ingestion wrappers into the A-ranked model-portfolio DTO module while improving `reference_data_dto.py` to `A (28.88)`, CR-1040 extracted an A-ranked cashflow-planning DTO module while reducing `reference_data_dto.py` to a pure A (100.00) compatibility facade, CR-1041 extracted an A-ranked ingestion capacity/backlog DTO module while improving `ingestion_job_dto.py` to `A (27.87)`, CR-1042 extracted an A-ranked ingestion replay diagnostics DTO module while improving `ingestion_job_dto.py` to `A (32.33)` and reducing it to 730 SLOC, CR-1043 extracted an A-ranked ingestion operations diagnostics DTO module while improving `ingestion_job_dto.py` to `A (44.17)` and reducing it to 249 SLOC, and CR-1044 extracted an A-ranked ingestion lifecycle DTO module while reducing `ingestion_job_dto.py` to a pure A (100.00) compatibility facade at 38 SLOC, CR-1045 split transaction ingestion DTOs into a 4-SLOC compatibility facade plus typed model/request modules, CR-1046 reduced `reference_data_benchmark_dto.py` to a 16-SLOC compatibility facade, CR-1047 reduced `ingestion_job_operations_dto.py` to a 15-SLOC compatibility facade, CR-1048 reduced `reference_data_tax_dto.py` to a 6-SLOC compatibility facade with scoped-mypy-clean tax profile/rule-set modules, and CR-1049 reduced `reference_data_client_preference_dto.py` to a 10-SLOC compatibility facade with scoped-mypy-clean client restriction/sustainability preference modules; the active non-generated C-ranked source hotspot list is clear, with generated `query_service/build` copies tracked separately | Keep maintainability regression-free while reducing existing C hotspots by domain priority |
| Dead code | Production-source baseline clean and enforced after CR-876 by `make quality-vulture-source-gate` plus the quality-baseline Vulture source dead-code job; broader `src tests` Vulture report remains noisy with fixture-style test parameters | Keep production-source dead-code regression-free while reducing test-fixture Vulture noise in focused batches |
| Dependency usage | Production-source deptry baseline clean and enforced after CR-878 by `make quality-deptry-source-gate` plus the quality-baseline Deptry source dependency job | Keep source dependency hygiene regression-free while broader dependency audit remains report-only |
| Security | Bandit baseline clean and enforced after CR-875 by `make quality-bandit-gate` plus the quality-baseline Bandit security job | Keep Bandit regression-free while broader dependency-audit/security gates continue to ratchet |
| CI governance | PR Merge Gate and Main Releasability no longer pin the Node 20-deprecated `actions/cache@v4`, `actions/upload-artifact@v4`, `actions/download-artifact@v4`, or `docker/setup-buildx-action@v3`; CR-1079 pins the current major action versions and adds a unit regression test; CR-1087 removes the branch-protection API probe from the required PR auto-merge workflow and adds a regression test so the default workflow token is not used for an unavailable Administration-scope endpoint; CR-1088 isolated `db_direct` suites from live workers; CR-1089 refines `integration-all` to use DB-plus-Kafka infrastructure without live application workers; CR-1090 explicitly waits for the `kafka-topic-creator` one-shot service before Kafka tooling tests run | Keep action runtime warnings clean through workflow lint and pinned-version tests; keep db-direct suites isolated from live-worker runtime and prove Docker-backed integration composition in GitHub CI |
| Architecture boundaries | Existing strict architecture guard plus 2 kept import-linter contracts enforced by `make quality-import-boundary-gate` after CR-867 | Add focused import contracts as additional ownership boundaries stabilize |
| OpenAPI governance | Existing OpenAPI quality and API vocabulary gates promoted into the quality-baseline API governance job after CR-868 | Keep API governance regression-free while spectral remains report-only until a stable generated-spec artifact exists |
| Documentation | New top-level governance docs scaffolded; CR-847 records collection/build-artifact cleanup | Keep docs implementation-backed and current |

## Before/After PR Scorecard

This table summarizes the evidence the final PR must carry forward. It is intentionally limited to
measured or explicitly documented improvement so the PR can distinguish completed hardening from
remaining merge-gate risk.

| Area | Baseline / Risk Before This Branch | Current Evidence After CR-1091 | Remaining PR Risk |
| --- | --- | --- | --- |
| Code health | Quality foundation existed, but the refactor started with broad format/lint/collection debt and active source maintainability hotspots to measure and reduce. | Ruff lint and format gates pass; complexity and maintainability gates pass; active non-generated C-ranked source hotspot list is clear; current measured source hotspot is `ingestion_job_service.py` `B (16.96)`; `reference_data_dto.py` improved to `A (100.00)`; CR-974 reduced the canonical FX validator from `E (37)` to `A (1)`; CR-975 reduced the canonical INTEREST validator from `D (29)` to `A (1)`; CR-976 reduced the canonical SELL validator from `C (14)` to `A (1)`; CR-977 reduced the canonical BUY validator from `C (14)` to `A (1)`; CR-978 reduced the canonical DIVIDEND validator from `D (21)` to `A (1)`; CR-979 reduced the CA Bundle A validator from `D (22)` to `A (2)`; CR-980 reduced adjustment cash-leg resolution from `C (11)` to `A (3)` and cash-leg construction from `B (9)` to `A (1)`; CR-981 reduced upstream cash-leg pairing validation from `C (12)` to `A (1)`; CR-982 reduced FX baseline processing from `C (14)` to `A (2)`; CR-983 reduced FX contract instrument construction from `C (13)` to `A (5)`; CR-984 leaves the FX linkage module fully A-ranked by complexity; CR-985 reduced BUY linkage enrichment from `B (6)` to `A (2)`; CR-986 reduced SELL linkage enrichment from `B (7)` to `A (2)`; CR-987 reduced INTEREST linkage enrichment from `B (6)` to `A (2)`; CR-988 reduced DIVIDEND linkage from `B (6)` to `A (2)`; CR-989 reduced CA Bundle A reconciliation from `B (8)` to `A (2)`; CR-990 reduced CA Bundle A dependency ordering from `B (8)` to `A (1)`; CR-991 through CR-1080 continue reducing measured B/C/D validation, runtime, repository, DTO, OpenAPI, supportability, consumer, calculator, ingestion upload, advisory simulation, and CI-enforcement hotspots; CR-1060 reduced `build_portfolio_readiness_response` from `D (23)` to `A (1)`, CR-1061 reduced `CapabilitiesService.get_integration_capabilities` from `D (29)` to `A (1)`, CR-1062 reduced `build_support_overview_response` from `D (23)` to `A (1)`, CR-1063 reduced `build_benchmark_market_series_response` from `D (23)` to `A (1)`, CR-1064 reduced `CashBalanceResolver.build_cash_account_balance_records` from `D (22)` to `A (2)`, CR-1065 reduced `ReportingRepository.get_latest_cash_account_ids` from `B (7)` to `A (2)`, CR-1066 reduced `market_reference_data_quality_status` from `C (11)` to `A (3)`, CR-1067 reduced `resolve_component_window_rows` from `C (11)` to `A (4)`, CR-1068 reduced `latest_reference_evidence_timestamp` from `B (6)` to `A (2)`, CR-1069 reduced `benchmark_market_series_point` from `C (19)` to `A (1)`, CR-1070 reduced `build_discretionary_mandate_binding_response` from `C (17)` to `A (2)`, CR-1071 reduced `build_portfolio_tax_lot_window_response` from `C (15)` to `A (2)`, CR-1072 reduced `build_market_data_coverage_response` from `C (18)` to `A (1)`, CR-1073 reduced `SimulationService.get_projected_positions` from `D (22)` to `A (2)`, CR-1074 reduced `UploadIngestionService.commit_upload` from `D (23)` to `A (1)` plus `_parse_xlsx` from `C (12)` to `A (4)` while leaving the upload ingestion service fully A-ranked by cyclomatic complexity, CR-1075 reduced `PositionCalculator.calculate_next_position` from `D (27)` to `A (2)`, CR-1076 reduced `ValuationConsumer.process_message` from `D (26)` to `B (7)`, CR-1077 reduced `_scan_state_issues` from `D (27)` to `A (1)`, CR-1078 enforces runtime-safe unit collection with 2,964 collected tests, and CR-1080 reduced `compute_suitability_result` from `C (16)` to `A (3)` plus `_governance_issue_for_instrument` from `C (11)` to `A (1)`. | Keep generated `query_service/build` copies tracked separately and prevent source hotspot regression before PR. |
| Architecture and modularity | Large services, repositories, and DTO modules carried concentrated logic and weak reviewability across analytics, core snapshot, operations, reference data, and ingestion surfaces. | Focused helper/module extractions moved query, DTO-family, analytics export, core snapshot, operations, and ingestion logic into A-ranked modules; `ingestion_job_service.py` is reduced to `B (16.96)` with no remaining B-ranked service methods; `reference_data_model_portfolio_definition_dto.py` now owns model-portfolio definition DTOs, `reference_data_model_portfolio_target_dto.py` owns model-portfolio target DTOs, and `reference_data_model_portfolio_dto.py` is now a compatibility facade; `reference_data_support_dto.py` owns classification taxonomy, cash-account, and look-through component DTOs as an A-ranked support-reference module; `reference_data_benchmark_definition_dto.py`, `reference_data_benchmark_composition_dto.py`, and `reference_data_benchmark_return_series_dto.py` now own benchmark definition, composition, and return-series DTOs as focused A-ranked modules; `reference_data_benchmark_records_dto.py` is now a compatibility facade; `reference_data_index_definition_dto.py`, `reference_data_index_price_series_dto.py`, `reference_data_index_return_series_dto.py`, and `reference_data_risk_free_series_dto.py` now own index and risk-free series DTOs as focused A-ranked modules; `reference_data_index_series_dto.py` and `reference_data_benchmark_dto.py` are compatibility facades; `reference_data_discretionary_mandate_dto.py` owns discretionary mandate binding DTOs, `reference_data_portfolio_benchmark_assignment_dto.py` owns portfolio benchmark assignment DTOs, and `reference_data_mandate_dto.py` is now a compatibility facade; `reference_data_cashflow_planning_dto.py` owns income-needs, liquidity-reserve, and planned-withdrawal DTOs as an A-ranked cashflow-planning module; `reference_data_tax_profile_dto.py` owns client tax profile DTOs, `reference_data_tax_rule_set_dto.py` owns client tax rule-set DTOs, and `reference_data_tax_dto.py` is now a compatibility facade; `reference_data_client_restriction_dto.py` owns client restriction DTOs, `reference_data_sustainability_preference_dto.py` owns sustainability preference DTOs, and `reference_data_client_preference_dto.py` is now a compatibility facade; `ingestion_job_capacity_dto.py` owns ingestion capacity and backlog breakdown response DTOs as an A-ranked operations diagnostics module; `ingestion_job_replay_dto.py` owns consumer DLQ, consumer-lag, DLQ replay, and replay-audit DTOs as an A-ranked replay diagnostics module; `ingestion_job_observability_dto.py` owns ingestion health, SLO, operating-band, policy, and error-budget DTOs as an A-ranked observability module; `ingestion_job_control_dto.py` owns reprocessing queue, stalled-job, retry, and ops-mode DTOs as an A-ranked control module; `ingestion_job_operations_dto.py` is now a compatibility facade; `ingestion_job_lifecycle_dto.py` owns job lifecycle, failure, record-status, and idempotency diagnostic DTOs as an A-ranked lifecycle module; CR-1061 splits integration capability policy resolution into typed feature, workflow, tenant override, and input-mode helpers while preserving the public capability response contract; CR-1062 splits support overview response assembly into explicit reprocessing, valuation, aggregation, analytics export, portfolio-evidence, and control field helpers while preserving the public support overview contract; CR-1063 splits benchmark market-series response assembly into explicit row-indexing, component point, returned-evidence, quality-summary, and page-metadata helpers while preserving the public market-series contract; CR-1064 splits cash-balance account record preparation into explicit master-row indexing, fallback ID resolution, master/fallback record input construction, instrument naming, account currency, and cash-account ID helpers while preserving the public cash balances contract; CR-1065 splits latest cash-account ID SQL assembly into explicit security normalization, ranked transaction subquery, latest-ID statement, and result mapping helpers while preserving repository behavior; CR-1066 splits market-reference quality status extraction and coverage-signal construction from the public quality helper while preserving shared classification policy; CR-1067 splits benchmark component-window grouping, ordering, supersession end-date inference, window-overlap filtering, and row projection from the public component-window helper while preserving returned fields and ordering; CR-1068 splits reference-evidence timestamp field policy and row timestamp extraction from the public evidence helper while preserving multi-row-group max timestamp behavior; CR-1069 splits benchmark market-series point metadata precedence, requested decimal fields, and requested optional values from the public mapper while preserving response shape; CR-1070 splits discretionary mandate supportability, review schedule, rebalance-band, and lineage assembly from the public DPM binding response builder while preserving supportability precedence and response shape; CR-1071 splits portfolio tax-lot record mapping, missing-security detection, supportability/data-quality policy, page metadata, and lineage assembly from the public tax-lot window response builder while preserving pagination and response shape; CR-1072 splits market-data price/fx coverage mapping, supportability classification, quality status, and lineage assembly from the public market-data coverage response builder while preserving response shape; CR-1073 splits simulation session projection baseline resolution, change normalization, new-security projection, instrument enrichment, change application, and response row construction from the public projected-positions method while preserving response shape and read ordering; CR-1074 splits upload row normalization, XLSX row parsing, commit guardrails, entity publish dispatch, typed publish helpers, and commit response construction from the upload ingestion service while preserving preview and commit behavior; CR-1075 splits position-update transaction-family dispatch, BUY/SELL cost-basis policy, cash-position deltas, transfer and corporate-action handling, FX contract lifecycle updates, spin-off basis handling, and flat-position cost-basis cleanup from the public position-calculation method while preserving transaction-spec behavior; CR-1076 splits valuation consumer event-session orchestration, position-state lookup, reference-data validation, snapshot valuation, FX-missing failure handling, terminal job completion, no-position skip handling, and valuation-to-timeseries outbox publication from the Kafka handler while preserving worker side effects. | Final PR narrative must explain the architectural pattern and remaining generated-surface debt without claiming complete platform-wide modularity. |
| OpenAPI and API governance | API governance needed to remain measurable and CI-visible while refactoring preserved behavior. | `make openapi-gate`, `make api-vocabulary-gate`, `make no-alias-gate`, and `make monetary-float-guard` pass in the current evidence snapshot; CR-1014 left every `openapi_examples.py` function A-ranked; CR-1018 left every `openapi_enrichment.py` function A-ranked while preserving parameter, request, response, and error-example enrichment behavior; CR-1063 keeps the benchmark market-series response contract stable while isolating page metadata, quality summary, normalization status, and runtime metadata assembly behind A-ranked helpers; CR-1064 keeps the cash balances response contract stable while isolating master cash-account rows, fallback IDs, zero-balance master accounts, FX conversion inputs, sorting, and runtime metadata behind A-ranked helpers. | Spectral remains report-only until the generated-spec artifact and quality contract are stable enough for enforcement. |
| Tests and coverage | Full all-suite collection was blocked by governed mixed-runtime constraints, and coverage evidence needed a runtime-separated gate rather than an unbounded local rerun. | `make warning-gate` passes with 2,918 unit tests, 9 deselected, and 0 warnings; `make coverage-gate` passes with 98% combined unit + integration-lite coverage after 2,918 unit tests and 121 integration-lite tests; CR-1081 adds focused coverage for position-history correction reprocessing signals and keeps non-Docker position-calculator behavior green with 46 tests; CR-1083 keeps runtime-scope unit guard tests green with 12 tests while fixing a Docker-backed Integration Full scheduler regression exposed by Main Releasability run `27459725250`; CR-1086 keeps cost-engine cash expense semantics green with 54 focused tests and position-calculator behavior green with 47 tests while fixing the Main Releasability run `27464050698` MWR E2E cash expense failure path, including cash `FEE` booked-cost and position-quantity alignment with explicit fee components; CR-1088 prevented live-worker interference in direct integration tests; CR-1089 adds a unit guard that manifest-declared `db_direct` suites use isolated DB-only or DB-plus-Kafka infrastructure with `integration-all` explicitly keeping Kafka without workers; CR-1090 adds a one-shot compose-service wait so `kafka-topic-creator` completes before Kafka tooling tests run; CR-1091 aligns the dual-leg settlement E2E proof with the governed internal cash-book settlement contract by asserting neutralized cash-book market value, retained cash quantity, and stock/cash internal flows netting to zero. | Keep runtime-separated test lanes as PR truth; do not represent the mixed-runtime collection guard as a full all-suite pass. Docker-backed repository, scheduler integration, Kafka integration, and E2E proof must come from GitHub CI because local Docker Desktop is unavailable in this workspace. |
| Security and dependency hygiene | Security posture needed measurable gates beyond source-only linting and report-only dependency checks. | `make quality-bandit-gate` passes with 0 Bandit issues across `src`; `make quality-deptry-source-gate` passes; `make security-audit` passes with dependency consistency clean and no known vulnerabilities, with 2 governed ignores; CR-971 reduced source-data security profile validation from `D (25)` to `A (4)`; CR-973 leaves enterprise readiness policy fully A-ranked by complexity. | PR should list the governed pip-audit ignores explicitly and keep dependency-audit evidence current on the final commit. |
| Observability and operations | Ingestion and operational diagnostics had concentrated logic that was harder to test, review, and support. | CR-953 through CR-969 extracted focused ingestion status, SLO, backlog, capacity, reprocessing, replay audit, consumer-lag, health-summary, and idempotency diagnostics helpers with direct tests for representative operational behavior; CR-972 reduced shared outbox dispatcher batch orchestration from `E (33)` to `A (2)` while preserving metrics and delivery accounting; CR-1060 split portfolio readiness supportability composition into A-ranked reason-family and response-assembly helpers while preserving bounded metric labels and readiness behavior; CR-1061 split integration capability policy resolution into A-ranked helpers while preserving consumer, tenant, workflow, feature, and supported-input-mode behavior; CR-1062 split support overview response assembly into A-ranked operational-domain field helpers while preserving backlog age, control blocking, reconciliation, and publish-allowed behavior; CR-1081 preserves earliest dirty position-state watermarks while touching already-lagging correction rows so valuation scheduler correlation can re-arm completed valuation jobs after corrected position history is written. | Runtime-level observability claims still need to stay scoped to diagnostics modularity, supportability-builder refactoring, integration capability policy modularity, support overview modularity, outbox helper refactoring, and correction-signal hardening unless additional service bring-up evidence is captured. |
| Documentation and CI measurement | The branch needed baseline measurement, incremental evidence, and a reviewable trail rather than cosmetic cleanup claims. | The quality scorecard, refactor report, baseline evidence, and CR-849 through CR-1091 ledger entries record measurable gate, maintainability, operational, CI-governance, and fix-forward movement; GitHub `Remote Feature Lane` run `27458485134` passed for `b4555b7d`; CR-1082 adds workflow-scope Node 24 JavaScript action runtime opt-in across all workflows with a unit test enforcing the setting, and the passed Feature Lane log showed the opt-in present without matching `Node.js 20` warning text; CR-1083 records the Main Releasability `27459725250` Integration Full failure and the targeted scheduler eligibility fix-forward evidence; Remote Feature Lane run `27460894329` passed for `84857360`; CR-1084 and CR-1085 record advisory valuation complexity reductions with focused test and lint evidence; CR-1086 records the Main Releasability `27464050698` MWR E2E failure and the targeted cash expense cost-engine fix-forward evidence; CR-1087 records the PR #403 required auto-merge permission failure and workflow fix-forward evidence; CR-1088 records the Main Releasability `27468473911` Integration Full failure and the db-direct suite isolation fix-forward evidence; CR-1089 records the Main Releasability `27469924560` Integration Full Kafka infrastructure follow-up failure and targeted fix-forward evidence; CR-1090 records the PR #405 review-blocking Kafka topic readiness race and focused helper/test fix-forward evidence; CR-1091 records the Main Releasability `27471662345` E2E Full cash-book settlement contract mismatch and focused E2E assertion correction. | The final PR must refresh this row again if later commits are added before opening or merge; PR Merge Gate/Main Releasability remain the source of truth for the fuller Docker-backed E2E lanes. |

## Current PR Evidence Snapshot

Local evidence captured on 2026-06-05 after CR-1034:

- `make quality-ruff-gate` => passed
- `make quality-ruff-format-gate` => passed; 1,156 files already formatted
- `make quality-bandit-gate` => passed; Bandit reported 0 issues across `src` and scanned
  116,177 lines of code
- `make quality-import-boundary-gate` => passed; 2 import-linter contracts kept
- `make quality-vulture-source-gate` => passed
- `make quality-deptry-source-gate` => passed; no dependency issues found
- `make openapi-gate` => passed
- `make api-vocabulary-gate` => passed
- `make typecheck` => passed; 48 source files checked
- `make no-alias-gate` => passed
- `make monetary-float-guard` => passed; 2 findings, 17 allowlisted
- `make quality-complexity-gate` => passed
- `make quality-maintainability-gate` => passed; no source modules exceed C rank
- `make warning-gate` => passed; 2,918 unit tests, 9 deselected, 0 warnings
- `make security-audit` => passed; dependency consistency clean and pip-audit reported no known
  vulnerabilities, with 2 governed ignores
- `make coverage-gate` => passed; combined unit + integration-lite coverage `98%` at threshold
  `98` after 2,918 unit tests and 121 integration-lite tests
- GitHub `Remote Feature Lane` run `27412118165` => passed for `01eccd11`
- GitHub `Remote Feature Lane` run `26995543519` => passed for `89d051ef`
- Current measured source hotspot: `ingestion_job_service.py` `B (16.96)`;
  `reference_data_dto.py` is now `A (100.00)`, and the active non-generated C-ranked source
  hotspot list is clear.
- CR-1047 focused evidence: event-replay OpenAPI contract tests passed with 10 tests; ingestion
  guardrail and operating-band tests passed with 22 tests; scoped ingestion operations DTO mypy,
  Python Ruff lint, Python Ruff format, and `make lint` checks passed;
  `ingestion_job_operations_dto.py` moved from 498 SLOC at `A (37.66)` to a 15-SLOC
  `A (100.00)` compatibility facade,
  `ingestion_job_observability_dto.py` reports `A (49.01)`, and
  `ingestion_job_control_dto.py` reports `A (47.35)` while preserving public imports and OpenAPI
  schema names.
- CR-1048 focused evidence: reference-data DTO and ingestion OpenAPI contract tests passed with 65
  tests; scoped tax DTO mypy, Python Ruff lint, and Python Ruff format checks passed;
  `reference_data_tax_dto.py` moved from 190 SLOC at `A (29.60)` to a 6-SLOC
  `A (100.00)` compatibility facade, `reference_data_tax_profile_dto.py` reports `A (41.82)`,
  and `reference_data_tax_rule_set_dto.py` reports `A (37.58)` while preserving public imports,
  validation behavior, and OpenAPI schema names.
- CR-1049 focused evidence: reference-data DTO and ingestion OpenAPI contract tests passed with 65
  tests; scoped client preference DTO mypy, Python Ruff lint, and Python Ruff format checks passed;
  `reference_data_client_preference_dto.py` moved from 142 SLOC at `A (32.04)` to a 10-SLOC
  `A (100.00)` compatibility facade, `reference_data_client_restriction_dto.py` reports
  `A (42.42)`, and `reference_data_sustainability_preference_dto.py` reports `A (40.79)` while
  preserving public imports, validation behavior, and OpenAPI schema names.
- CR-1050 focused evidence: reference-data DTO and ingestion OpenAPI contract tests passed with 65
  tests; scoped cashflow planning DTO mypy, Python Ruff lint, and Python Ruff format checks passed;
  `reference_data_cashflow_planning_dto.py` moved from 190 SLOC at `A (31.18)` to a 15-SLOC
  `A (100.00)` compatibility facade, `reference_data_income_needs_dto.py` reports `A (45.42)`,
  `reference_data_liquidity_reserve_dto.py` reports `A (45.44)`, and
  `reference_data_planned_withdrawal_dto.py` reports `A (49.30)` while preserving public imports,
  validation behavior, currency normalization, and OpenAPI schema names.
- CR-1051 focused evidence: reference-data DTO and ingestion OpenAPI contract tests passed with 65
  tests; scoped mandate DTO mypy, Python Ruff lint, and Python Ruff format checks passed;
  `reference_data_mandate_dto.py` moved from 240 SLOC at `A (39.16)` to a 10-SLOC
  `A (100.00)` compatibility facade, `reference_data_discretionary_mandate_dto.py` reports
  `A (42.80)`, and `reference_data_portfolio_benchmark_assignment_dto.py` reports `A (57.85)`
  while preserving public imports, validation behavior, and OpenAPI schema names.
- CR-1052 focused evidence: reference-data DTO and ingestion OpenAPI contract tests passed with 65
  tests; scoped model-portfolio DTO mypy, Python Ruff lint, and Python Ruff format checks passed;
  `reference_data_model_portfolio_dto.py` moved from 229 SLOC at `A (39.13)` to a 6-SLOC
  `A (100.00)` compatibility facade, `reference_data_model_portfolio_definition_dto.py` reports
  `A (52.32)`, and `reference_data_model_portfolio_target_dto.py` reports `A (46.09)` while
  preserving public imports, validation behavior, base-currency normalization, and OpenAPI schema
  names.
- CR-1053 focused evidence: reference-data DTO and ingestion OpenAPI contract tests passed with 65
  tests; scoped index/risk-free DTO mypy, Python Ruff lint, and Python Ruff format checks passed;
  `reference_data_index_series_dto.py` moved from 243 SLOC at `A (37.52)` to a 12-SLOC
  `A (100.00)` compatibility facade, `reference_data_index_definition_dto.py` reports
  `A (51.44)`, `reference_data_index_price_series_dto.py` reports `A (56.99)`,
  `reference_data_index_return_series_dto.py` reports `A (56.48)`, and
  `reference_data_risk_free_series_dto.py` reports `A (54.44)` while preserving public imports,
  validation behavior, currency normalization, OpenAPI schema names, and temporal-vocabulary
  allowlist strictness for the moved legacy `source_timestamp` fields.
- CR-1056 focused evidence: reference-data DTO and ingestion OpenAPI contract tests passed with 65
  tests; scoped tax rule-set DTO mypy, Python Ruff lint, and Python Ruff format checks passed;
  `_validate_tax_rule_evidence` improved from `B (6)` to `A (2)`, and
  `reference_data_tax_rule_set_dto.py` improved from `A (37.58)` to `A (38.36)` while preserving
  validation behavior, public imports, schema component names, and API route shape.
- CR-1057 focused evidence: reference-data DTO and ingestion OpenAPI contract tests passed with 65
  tests; scoped tax profile DTO mypy, Python Ruff lint, and Python Ruff format checks passed;
  `_validate_unknown_tax_status_detail` improved from `B (6)` to `A (3)`, and
  `reference_data_tax_profile_dto.py` improved from `A (41.82)` to `A (42.63)` while preserving
  validation behavior, public imports, schema component names, and API route shape.
- CR-1058 focused evidence: reference-data DTO and ingestion OpenAPI contract tests passed with 65
  tests; scoped client restriction DTO mypy, Python Ruff lint, and Python Ruff format checks passed;
  `_validate_scoped_restriction_values` improved from `B (6)` to `A (3)`, and
  `reference_data_client_restriction_dto.py` improved from `A (42.42)` to `A (43.00)` while
  preserving validation behavior, public imports, schema component names, and API route shape.
- CR-1059 focused evidence: reference-data DTO and ingestion OpenAPI contract tests passed with 65
  tests; scoped model-portfolio target DTO mypy, Python Ruff lint, and Python Ruff format checks
  passed; `ModelPortfolioTargetRecord` improved from `B (6)` to `A (2)` and `validate_bands`
  improved from `A (5)` to `A (1)` while preserving validation behavior, public imports, schema
  component names, and API route shape.
- CR-1060 focused evidence: portfolio readiness builder and operations-service tests passed with 61
  tests; scoped portfolio readiness mypy, Python Ruff lint, and Python Ruff format checks passed;
  `build_portfolio_readiness_response` improved from `D (23)` to `A (1)`,
  `_portfolio_supportability_summary` improved from `B (7)` to `A (2)`, and every function in
  `portfolio_readiness_builder.py` now reports A-ranked complexity while preserving readiness
  bucket behavior, blocking reasons, missing-FX payload shape, bounded metric labels, and response
  field values.
- CR-1061 focused evidence: capability-service unit tests passed with 11 tests; scoped capability
  service mypy, Python Ruff lint, and Python Ruff format checks passed;
  `CapabilitiesService.get_integration_capabilities` improved from `D (29)` to `A (1)`, the
  `CapabilitiesService` class improved from `C (11)` to `A (4)`, and every function in
  `capabilities_service.py` now reports A-ranked complexity while preserving feature flags, tenant
  overrides, workflow derivation, policy versions, input-mode behavior, and lazy DB engine posture.
- CR-1062 focused evidence: support overview builder and operations-service tests passed with 59
  tests; scoped support overview mypy, Python Ruff lint, and Python Ruff format checks passed;
  `build_support_overview_response` improved from `D (23)` to `A (1)`, and every function in
  `support_overview_builder.py` now reports A-ranked complexity while preserving reprocessing,
  valuation, aggregation, analytics export, portfolio evidence, control blocking, reconciliation,
  and publish-allowed response fields.
- CR-1063 focused evidence: benchmark market-series service tests passed with 18 tests; scoped
  benchmark market-series mypy, Python Ruff lint, and Python Ruff format checks passed;
  `build_benchmark_market_series_response` improved from `D (23)` to `A (1)`, and every function
  in `benchmark_market_series.py` now reports A-ranked complexity while preserving page-scoped
  component series, FX normalization status, quality summary, runtime metadata, evidence counts,
  and next-page token behavior.
- CR-1064 focused evidence: cash-balance service tests passed with 9 tests; scoped cash-balance
  mypy, Python Ruff lint, and Python Ruff format checks passed;
  `CashBalanceResolver.build_cash_account_balance_records` improved from `D (22)` to `A (2)`, and
  every function in `cash_balance_service.py` now reports A-ranked complexity while preserving
  master cash-account rows, fallback cash-account IDs, zero-balance accounts, sequential FX
  conversion inputs, sorting, and runtime metadata behavior.
- CR-1065 focused evidence: reporting repository and cash-balance service tests passed with 23
  tests; scoped reporting repository mypy, Python Ruff lint, and Python Ruff format checks passed;
  `ReportingRepository.get_latest_cash_account_ids` improved from `B (7)` to `A (2)`, and every
  function in `reporting_repository.py` now reports A-ranked complexity while preserving
  settlement-cash security normalization, latest transaction ranking, account-ID filtering, and
  fallback cash-account mapping behavior.
- CR-1066 focused evidence: reference-data helper and integration-service tests passed with 110
  tests; scoped reference-data helper mypy, Python Ruff lint, and Python Ruff format checks passed;
  `market_reference_data_quality_status` improved from `C (11)` to `A (3)` while preserving
  accepted, estimated, blocked, stale, missing-status, and required-count classification behavior.
- CR-1067 focused evidence: reference-data helper and integration-service tests passed with 112
  tests; scoped reference-data helper mypy, Python Ruff lint, and Python Ruff format checks passed;
  `resolve_component_window_rows` improved from `C (11)` to `A (4)` and the module remains
  A-ranked maintainability while preserving superseded effective-end inference, earlier explicit
  end dates, non-overlapping window filtering, returned metadata fields, and result ordering.
- CR-1068 focused evidence: reference-data helper and integration-service tests passed with 114
  tests; scoped reference-data helper mypy, Python Ruff lint, and Python Ruff format checks passed;
  `latest_reference_evidence_timestamp` improved from `B (6)` to `A (2)` and the module remains
  A-ranked maintainability while preserving observed/source/assignment/updated/created timestamp
  field handling, multi-row-group max timestamp behavior, and missing/non-datetime filtering.
- CR-1069 focused evidence: reference-data mapper and benchmark market-series tests passed with 34
  tests; scoped reference-data mapper mypy, Python Ruff lint, and Python Ruff format checks passed;
  `benchmark_market_series_point` improved from `C (19)` to `A (1)`, and every function in
  `reference_data_mappers.py` now reports A-ranked complexity while preserving selected-field
  suppression, price-row metadata precedence, decimal normalization, and component/fx field
  behavior.
- CR-1070 focused evidence: discretionary mandate binding tests passed with 10 tests; scoped
  discretionary mandate binding mypy, Python Ruff lint, and Python Ruff format checks passed;
  `build_discretionary_mandate_binding_response` improved from `C (17)` to `A (2)`, the module
  reports `A (40.24)` maintainability, and the extracted supportability helpers preserve inactive
  authority, missing policy-pack priority, missing review data, overdue-review degradation,
  rebalance-band defaults, lineage, and runtime metadata behavior.
- CR-1071 focused evidence: portfolio tax-lot window tests passed with 12 tests; scoped tax-lot
  window mypy, Python Ruff lint, and Python Ruff format checks passed;
  `build_portfolio_tax_lot_window_response` improved from `C (15)` to `A (2)`, the module reports
  `A (35.88)` maintainability, and the extracted helpers preserve page-token scope, partial-page
  degradation, complete ready-page status, missing requested-security reporting, empty portfolio
  unavailability, lineage, and runtime metadata behavior.
- CR-1072 focused evidence: market-data coverage tests passed with 8 tests; scoped market-data
  coverage mypy, Python Ruff lint, and Python Ruff format checks passed;
  `build_market_data_coverage_response` improved from `C (18)` to `A (1)`, the module reports
  `A (38.12)` maintainability, and the extracted helpers preserve price and FX coverage mapping,
  missing/stale supportability precedence, resolved count reporting, lineage, and runtime metadata
  behavior.
- CR-1073 focused evidence: simulation service tests passed with 31 tests; scoped simulation
  service mypy, Python Ruff lint, and Python Ruff format checks passed;
  `SimulationService.get_projected_positions` improved from `D (22)` to `A (2)`, the module
  reports `A (29.73)` maintainability, and the extracted helpers preserve session lookup,
  baseline snapshot/history fallback, read ordering, security normalization, new-security
  projection, instrument enrichment, non-positive filtering, sorted response rows, and summary
  behavior.
- CR-1074 focused evidence: upload ingestion service tests passed with 5 tests; scoped upload
  service mypy, Python Ruff lint, and Python Ruff format checks passed;
  `UploadIngestionService.commit_upload` improved from `D (23)` to `A (1)`, `_parse_xlsx`
  improved from `C (12)` to `A (4)`, every function in `upload_ingestion_service.py` reports
  A-ranked cyclomatic complexity, and the module reports `A (25.69)` maintainability while
  preserving CSV/XLSX preview, partial-upload rejection, partial commit, empty-file rejection,
  entity publish routing, published/skipped row counts, and commit response shape.
- CR-1075 focused evidence: position calculator tests passed with 46 tests and transaction-spec
  characterization tests passed with 33 tests; scoped position logic mypy, Python Ruff lint, and
  Python Ruff format checks passed; `PositionCalculator.calculate_next_position` improved from
  `D (27)` to `A (2)`, `position_logic.py` reports `A (24.96)` maintainability, and the extracted
  helpers preserve BUY/SELL net-cost behavior, cash-position flow behavior, adjustment direction
  handling, FX cash settlement, FX contract open/close lifecycle, transfer and corporate-action
  quantity updates, spin-off basis handling, flat-position cost-basis reset, and transaction-spec
  characterization behavior.
- CR-1076 focused evidence: valuation consumer tests passed with 7 tests; scoped valuation
  consumer mypy, Python Ruff lint, and Python Ruff format checks passed;
  `ValuationConsumer.process_message` improved from `D (26)` to `B (7)`, and
  `valuation_consumer.py` reports `A (32.50)` maintainability while preserving Kafka delivery
  idempotency identity, correlation propagation, same-currency valuation without FX lookup,
  missing-position skip handling, missing-FX failed snapshot behavior, unexpected-error DLQ
  handling, and lost-job-ownership side-effect suppression.
- CR-1077 focused evidence: advisory simulation suitability scanner tests passed with 6 tests;
  scoped Python Ruff lint and format checks passed; `_scan_state_issues` improved from `D (27)` to
  `A (1)`, and `suitability.py` reports `B (18.89)` maintainability while preserving issue keys,
  severity ordering, evidence attachment, and recommended-gate behavior.
- CR-1078 focused evidence: `make quality-unit-collection-gate` collected 2,964 runtime-safe unit
  tests locally, and `.github/workflows/quality-baseline.yml` now enforces the same unit collection
  lane so syntax/import regressions fail without violating the repo's mixed-runtime collection
  guard for db-direct integration and live-worker E2E tests.
- CR-1079 focused evidence: workflow YAML parsing passed; no deprecated
  `actions/cache@v4`, `actions/upload-artifact@v4`, `actions/download-artifact@v4`, or
  `docker/setup-buildx-action@v3` pins remain under `.github/workflows`; PR Merge Gate and Main
  Releasability now use the available current major pins; and
  `tests/unit/test_ci_workflow_action_versions.py` passed with 2 tests.
- CR-1080 focused evidence: advisory suitability scanner and advisory proposal simulation tests
  passed with 35 tests; scoped Python Ruff lint and format checks passed;
  `compute_suitability_result` improved from `C (16)` to `A (3)`,
  `_governance_issue_for_instrument` improved from `C (11)` to `A (1)`, and
  `suitability.py` remains B-ranked at `B (18.34)` while preserving issue keys, severity policy,
  issue ordering, evidence wiring, and recommended-gate behavior.
- CR-1081 focused evidence: non-Docker position-calculator tests passed with 46 tests; scoped
  Python Ruff lint and format checks passed; Docker-backed `position_state_repository` tests and
  the MWR E2E could not run locally because Docker Desktop is unavailable, so GitHub CI remains the
  source of truth for that runtime proof.
- CR-1082 focused evidence: workflow YAML parsing passed for 5 workflows;
  `tests/unit/test_ci_workflow_action_versions.py` passed with 3 tests; scoped Python Ruff lint and
  format checks passed; all workflows now declare `FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: "true"`.
- CR-1083 focused evidence: Main Releasability run `27459725250` passed every lane except
  Integration Full, which failed
  `test_find_and_claim_eligible_jobs_claims_first_day_without_portfolio_history`; the fix-forward
  branch compiles `timeseries_repository_base.py`, passes scoped Python Ruff lint and format
  checks, passes `git diff --check`, keeps runtime-scope unit guard tests green with 12 tests, and
  passes `make warning-gate` locally with 2,958 tests, 10 deselected, and 0 warnings. Remote
  Feature Lane run `27460894329` passed for `84857360`; the exact Integration Full regression
  remains PR Merge Gate/Main Releasability proof because Docker Desktop is unavailable locally.
- CR-1084 focused evidence: advisory valuation and advisory simulation service tests passed with
  17 tests; scoped Python Ruff lint and format checks passed; `build_simulated_state` improved from
  `D (21)` to `A (2)`, and scoped Radon complexity and maintainability measurements passed while
  preserving the public `SimulatedState` shape.
- CR-1085 focused evidence: advisory valuation and advisory simulation service tests passed with
  17 tests; scoped Python Ruff lint and format checks passed; `ValuationService.value_position`
  improved from `C (13)` to `A (4)`, `ValuationService` improved from `C (14)` to `A (5)`, and
  scoped Radon complexity and maintainability measurements passed while preserving trusted
  base-currency authority behavior and calculated valuation behavior.
- CR-1055 focused evidence: reference-data DTO and ingestion OpenAPI contract tests passed with 65
  tests; scoped instrument-eligibility DTO mypy, Python Ruff lint, and Python Ruff format checks
  passed; `InstrumentEligibilityProfileRecord` improved from `B (8)` to `A (2)` and its
  effective-window/shelf-permission validator improved from `B (7)` to `A (1)` while preserving
  validation behavior, public imports, schema component names, and API route shape.
- CR-1054 focused evidence: reference-data DTO and ingestion OpenAPI contract tests passed with 65
  tests; scoped benchmark-record DTO mypy, Python Ruff lint, and Python Ruff format checks passed;
  `reference_data_benchmark_records_dto.py` moved from 207 SLOC at `A (40.91)` to a 13-SLOC
  `A (100.00)` compatibility facade, `reference_data_benchmark_definition_dto.py` reports
  `A (50.64)`, `reference_data_benchmark_composition_dto.py` reports `A (56.85)`, and
  `reference_data_benchmark_return_series_dto.py` reports `A (56.48)` while preserving public
  imports, validation behavior, currency normalization, OpenAPI schema names, and
  temporal-vocabulary allowlist strictness for the moved legacy `source_timestamp` fields.
- CR-1046 focused evidence: reference-data DTO tests passed with 35 tests; benchmark/index/risk-free
  ingestion router tests passed with 49 tests; ingestion OpenAPI contract tests passed with 30 tests;
  benchmark/reference DTO mypy, scoped Python Ruff lint/format, temporal-vocabulary guard, temporal guard unit tests, and `make lint` passed;
  `reference_data_benchmark_dto.py` moved from 444 SLOC at `A (30.27)` to a 16-SLOC
  `A (100.00)` compatibility facade, `reference_data_benchmark_records_dto.py` reports
  `A (40.91)`, and `reference_data_index_series_dto.py` reports `A (37.52)` while
  preserving public imports, route behavior, and OpenAPI schema names.
- CR-1045 focused evidence: transaction model tests passed with 14 tests; transaction-spec
  characterization tests passed with 23 tests; ingestion OpenAPI contract tests passed with 30 tests;
  transaction DTO mypy, scoped Python Ruff lint/format, and `make lint` passed;
  `transaction_dto.py` moved from 678 SLOC to a 4-SLOC `A (100.00)` compatibility facade,
  `transaction_model_dto.py` reports `A (42.85)`, `transaction_ingestion_request_dto.py` reports
  `A (100.00)`, and the extracted model uses explicit constrained Decimal aliases while
  preserving public imports and OpenAPI schema names.
- CR-1044 focused evidence: ingestion guardrail tests passed with 18 tests; ingestion OpenAPI
  contract tests passed with 30 tests; event-replay OpenAPI contract tests passed with 10 tests;
  lifecycle DTO mypy, scoped Python Ruff lint/format, and `make lint` passed;
  `ingestion_job_dto.py` improved from `A (44.17)` to `A (100.00)`,
  `ingestion_job_lifecycle_dto.py` reports `A (46.58)`, and the aggregate ingestion-job DTO
  module shrank from 249 SLOC to 38 SLOC while preserving public imports and OpenAPI schema names.
- CR-1043 focused evidence: ingestion guardrail tests passed with 18 tests; ingestion OpenAPI
  contract tests passed with 30 tests; event-replay OpenAPI contract tests passed with 10 tests;
  operations DTO mypy, scoped Python Ruff lint/format, and `make lint` passed;
  `ingestion_job_dto.py` improved from `A (32.33)` to `A (44.17)`,
  `ingestion_job_operations_dto.py` reports `A (37.66)`, and the aggregate ingestion-job DTO
  module shrank from 730 SLOC to 249 SLOC while preserving public imports and OpenAPI schema names.
- CR-1042 focused evidence: DLQ/replay guardrail tests passed with 18 tests; event-replay
  OpenAPI contract tests passed with 10 tests; replay DTO mypy and scoped Python Ruff lint/format
  and `make lint` passed; `ingestion_job_dto.py` improved from `A (27.87)` to `A (32.33)`,
  `ingestion_job_replay_dto.py` reports `A (43.08)`, and the aggregate ingestion-job DTO module
  shrank from 936 SLOC to 730 SLOC while preserving public imports and OpenAPI schema names.
- CR-1041 focused evidence: ingestion capacity/backlog service tests passed with 4 tests;
  ingestion main app contract tests passed with 30 tests; capacity DTO mypy and scoped Python
  Ruff lint/format and `make lint` passed; `ingestion_job_dto.py` improved from `A (25.62)` to `A (27.87)`,
  `ingestion_job_capacity_dto.py` reports `A (50.80)`, and the aggregate ingestion-job DTO module
  shrank from 1,120 SLOC to 936 SLOC while preserving public imports and OpenAPI schema names.
- CR-1040 focused evidence: reference-data DTO tests passed with 35 tests; ingestion main app
  contract tests passed with 30 tests; temporal-vocabulary guard and guard unit tests passed;
  cashflow-planning-module mypy, scoped Python Ruff lint/format, and `make lint` passed;
  `reference_data_dto.py`
  improved from `A (28.88)` to `A (100.00)`, `reference_data_cashflow_planning_dto.py`
  reports `A (31.18)`, and the aggregate DTO module shrank from 249 SLOC to 73 SLOC while
  preserving public imports, OpenAPI schema names, and ingestion request behavior.
- CR-1039 focused evidence: reference-data DTO tests passed with 35 tests; ingestion main app
  contract tests passed with 30 tests; temporal-vocabulary guard and guard unit tests passed;
  model-portfolio-module mypy, scoped Python Ruff lint/format, and `make lint` passed;
  `reference_data_dto.py`
  improved from `A (27.76)` to `A (28.88)`, `reference_data_model_portfolio_dto.py` remains
  A-ranked at `A (39.13)`, and the aggregate DTO module shrank from 302 SLOC to 249 SLOC while
  preserving public imports, OpenAPI schema names, and ingestion request behavior.
- CR-1038 focused evidence: reference-data DTO tests passed with 35 tests; ingestion main app
  contract tests passed with 30 tests; temporal-vocabulary guard and guard unit tests passed;
  mandate-module mypy, scoped Python Ruff lint/format, and `make lint` passed; `reference_data_dto.py`
  improved from `A (21.98)` to `A (27.76)`, `reference_data_mandate_dto.py` reports
  `A (39.16)`, and the aggregate DTO module shrank from 529 SLOC to 302 SLOC while preserving
  public imports, OpenAPI schema names, and ingestion request behavior.
- CR-1037 focused evidence: reference-data DTO tests passed with 35 tests; ingestion main app
  contract tests passed with 30 tests; temporal-vocabulary guard and guard unit tests passed;
  benchmark-module mypy, scoped Python Ruff lint/format, and `make lint` passed;
  `reference_data_dto.py` improved from `B (14.29)` to `A (21.98)`,
  `reference_data_benchmark_dto.py` reports `A (30.27)`, and the aggregate DTO module shrank from
  947 SLOC to 529 SLOC while preserving public imports, OpenAPI schema names, and ingestion
  request behavior.
- CR-1036 focused evidence: reference-data DTO tests passed with 35 tests; scoped Ruff lint,
  format, support-module mypy, temporal-vocabulary guard, temporal guard unit tests, and
  `make lint` passed; `reference_data_dto.py` improved from `B (12.49)` to `B (14.29)`,
  `reference_data_support_dto.py` reports `A (43.83)`, and the aggregate DTO module shrank from
  1,119 SLOC to 947 SLOC while preserving public imports and ingestion request behavior.
- CR-1035 focused evidence: reference-data DTO tests passed with 35 tests; scoped Ruff lint,
  format, and extracted-module mypy checks passed; `reference_data_dto.py` improved from
  `B (9.31)` to `B (12.49)`, `reference_data_model_portfolio_dto.py` reports `A (41.43)`,
  and the aggregate DTO module shrank from 1,282 SLOC to 1,119 SLOC while preserving public
  imports and ingestion request behavior.
- CR-1033 focused evidence: cost calculator consumer tests passed with 27 tests; scoped Ruff lint
  and format checks passed; `CostCalculatorConsumer._transform_event_for_engine` improved from
  `B (9)` to `A (2)`, and `consumer.py` remains A-ranked maintainability at `A (22.19)`.
- CR-1034 focused evidence: cost calculator consumer tests passed with 28 tests; scoped Ruff lint
  and format checks passed; `CostCalculatorConsumer._record_bundle_a_reconciliation_diagnostics`
  improved from `B (9)` to `A (3)`, and `consumer.py` remains A-ranked maintainability at
  `A (20.93)`.
- CR-970 focused evidence: event supportability tests passed with 19 tests; scoped Ruff lint and
  format checks passed; `validate_event_supportability_catalog` improved from `E (39)` to
  `A (5)` and all event-supportability helper functions are A-ranked.
- CR-971 focused evidence: source-data security tests passed with 23 tests; scoped Ruff lint and
  format checks passed; `_validate_source_data_security_profiles` improved from `D (25)` to
  `A (4)` and all touched source-data security helper functions are A-ranked.
- CR-972 focused evidence: outbox dispatcher unit tests passed with 6 tests; scoped Ruff lint and
  format checks passed; `_process_batch_sync` improved from `E (33)` to `A (2)` and all dispatcher
  methods/outbox helpers are A-ranked. DB-backed outbox integration tests were attempted but could
  not start locally because Docker Desktop/daemon was unavailable.
- CR-973 focused evidence: enterprise readiness shared/query-service/control-plane tests passed
  with 62 tests; scoped Ruff lint and format checks passed; `validate_enterprise_runtime_config`
  improved from `C (14)` to `A (5)`, `authorize_request` improved from `C (18)` to `A (4)`, and
  all enterprise readiness functions/classes/methods are A-ranked.
- CR-974 focused evidence: FX validation/linkage/contract-instrument tests passed with 22 tests;
  scoped Ruff lint and format checks passed; `validate_fx_transaction` improved from `E (37)` to
  `A (1)` and all FX validation functions/classes are A-ranked.
- CR-975 focused evidence: interest/control-code/currency tests passed with 27 tests; scoped Ruff
  lint and format checks passed; `validate_interest_transaction` improved from `D (29)` to
  `A (1)` and all INTEREST validation functions/classes are A-ranked.
- CR-976 focused evidence: sell/linkage/control-code/currency tests passed with 21 tests; scoped
  Ruff lint and format checks passed; `validate_sell_transaction` improved from `C (14)` to
  `A (1)` and all SELL validation functions/classes are A-ranked.
- CR-977 focused evidence: buy/linkage/control-code/currency tests passed with 19 tests; scoped
  Ruff lint and format checks passed; `validate_buy_transaction` improved from `C (14)` to
  `A (1)` and all BUY validation functions/classes are A-ranked.
- CR-978 focused evidence: dividend/linkage/control-code/currency tests passed with 23 tests;
  scoped Ruff lint and format checks passed; `validate_dividend_transaction` improved from
  `D (21)` to `A (1)` and all DIVIDEND validation functions/classes are A-ranked.
- CR-979 focused evidence: CA Bundle A validation/reconciliation/ordering tests passed with 14
  tests; scoped Ruff lint and format checks passed; `validate_ca_bundle_a_transaction` improved
  from `D (22)` to `A (2)` and all CA Bundle A validation functions/classes are A-ranked.
- CR-980 focused evidence: adjustment cash-leg and dual-leg pairing tests passed with 7 tests;
  scoped Ruff lint and format checks passed; `_resolve_adjustment_amount_and_direction` improved
  from `C (11)` to `A (3)`, `build_auto_generated_adjustment_cash_leg` improved from `B (9)` to
  `A (1)`, and all adjustment cash-leg functions/classes are A-ranked.
- CR-981 focused evidence: dual-leg pairing and adjustment cash-leg tests passed with 7 tests;
  scoped Ruff lint and format checks passed; `validate_upstream_cash_leg_pairing` improved from
  `C (12)` to `A (1)` and all dual-leg pairing functions/classes are A-ranked.
- CR-982 focused evidence: FX baseline/validation/linkage/contract-instrument tests passed with
  24 tests; scoped Ruff lint and format checks passed; `build_fx_processed_event` improved from
  `C (14)` to `A (2)` and all FX baseline processing functions are A-ranked.
- CR-983 focused evidence: FX contract-instrument/baseline/validation/linkage tests passed with
  24 tests; scoped Ruff lint and format checks passed; `build_fx_contract_instrument_event`
  improved from `C (13)` to `A (5)` and all FX contract instrument functions are A-ranked.
- CR-984 focused evidence: FX linkage/validation/contract-instrument/baseline tests passed with
  24 tests; scoped Ruff lint and format checks passed; `enrich_fx_transaction_metadata` improved
  from `B (7)` to `A (2)`, `_resolve_fx_contract_id` improved from `B (6)` to `A (4)`, and
  `_resolve_contract_lifecycle_transaction_ids` improved from `B (7)` to `A (3)`.
- CR-985 focused evidence: BUY linkage/validation/control-code tests passed with 14 tests; scoped
  Ruff lint and format checks passed; `enrich_buy_transaction_metadata` improved from `B (6)` to
  `A (2)` and all BUY linkage functions are A-ranked.
- CR-986 focused evidence: SELL linkage/validation/control-code tests passed with 16 tests; scoped
  Ruff lint and format checks passed; `enrich_sell_transaction_metadata` improved from `B (7)` to
  `A (2)` and all SELL linkage functions are A-ranked.
- CR-987 focused evidence: INTEREST linkage/validation/control-code tests passed with 24 tests;
  scoped Ruff lint and format checks passed; `enrich_interest_transaction_metadata` improved from
  `B (6)` to `A (2)` and all INTEREST linkage functions are A-ranked.
- CR-988 focused evidence: DIVIDEND linkage/validation/control-code tests passed with 18 tests;
  scoped Ruff lint and format checks passed; `enrich_dividend_transaction_metadata` improved from
  `B (6)` to `A (2)` and all DIVIDEND linkage functions are A-ranked.
- CR-989 focused evidence: CA Bundle A reconciliation/validation/ordering tests passed with 14
  tests; scoped Ruff lint and format checks passed; `evaluate_ca_bundle_a_reconciliation`
  improved from `B (8)` to `A (2)` and all CA Bundle A reconciliation functions/classes are
  A-ranked.
- CR-990 focused evidence: CA Bundle A ordering/reconciliation/validation tests passed with 14
  tests; scoped Ruff lint and format checks passed; `ca_bundle_a_dependency_rank` improved from
  `B (8)` to `A (1)` and all CA Bundle A ordering functions are A-ranked.
- CR-991 focused evidence: analytics cashflow semantics/query-service tests passed with 30 tests;
  scoped Ruff lint and format checks passed; `classify_analytics_cash_flow` improved from
  `B (10)` to `A (3)` and all analytics cashflow semantics functions are A-ranked.
- CR-992 focused evidence: market reference quality tests passed with 21 tests; scoped Ruff lint
  and format checks passed; `classify_market_reference_point` improved from `B (8)` to `A (1)`
  and all market reference quality functions/classes are A-ranked.
- CR-993 focused evidence: reconciliation and market reference quality tests passed with 48 tests;
  scoped Ruff lint and format checks passed; `classify_reconciliation_status` improved from
  `B (9)` to `A (2)`, `classify_data_quality_coverage` improved from `B (7)` to `A (1)`, and all
  reconciliation quality functions/classes are A-ranked.
- CR-994 focused evidence: ingestion evidence tests passed with 18 tests; scoped Ruff lint and
  format checks passed; `classify_ingestion_outcome` improved from `B (6)` to `A (1)` and all
  ingestion evidence functions/classes are A-ranked.
- CR-995 focused evidence: reconstruction identity tests passed with 12 tests; scoped Ruff lint and
  format checks passed; `_canonical_scope_payload` improved from `B (7)` to `A (1)` and all
  reconstruction identity functions/classes are A-ranked.
- CR-996 focused evidence: shared DB helper tests passed with 7 tests; scoped Ruff lint and format
  checks passed; `_normalize_database_url_scheme` improved from `B (6)` to `A (2)` and all shared
  DB helper functions are A-ranked.
- CR-997 focused evidence: Kafka admin tests passed with 3 tests; scoped Ruff lint and format
  checks passed; `ensure_topics_exist` improved from `B (6)` to `A (3)` and all Kafka admin helper
  functions/classes are A-ranked.
- CR-998 focused evidence: shared config tests passed with 16 tests; scoped Ruff lint and format
  checks passed; `_env_int` improved from `B (7)` to `A (1)` and all extracted integer parsing
  helpers are A-ranked.
- CR-999 focused evidence: shared config tests passed with 18 tests; scoped Ruff lint and format
  checks passed; `_coerce_consumer_config_value` improved from `C (16)` to `A (4)`, all extracted
  consumer coercion helpers are A-ranked, and `get_kafka_consumer_runtime_overrides` remains
  `B (7)` as the next separate runtime override loading slice.
- CR-1000 focused evidence: shared config tests passed with 18 tests; scoped Ruff lint and format
  checks passed; `get_kafka_consumer_runtime_overrides` improved from `B (7)` to `A (1)`, and all
  extracted consumer runtime override loading helpers are A-ranked while preserving the final
  merged heartbeat/session relationship validation boundary.
- CR-1001 focused evidence: Kafka consumer tests passed with 23 tests; scoped Ruff lint and format
  checks passed; `classify_dlq_reason_code` improved from `C (12)` to `A (5)`, extracted classifier
  helpers are A-ranked, and direct taxonomy tests cover validation, data-integrity, timeout,
  authorization, and unclassified outcomes.
- CR-1002 focused evidence: Kafka consumer tests passed with 26 tests; scoped Ruff lint and format
  checks passed; `BaseConsumer._message_correlation_context` improved from `B (7)` to `A (3)`,
  extracted correlation selection helpers are A-ranked, and direct tests cover current context,
  header-before-fallback, and explicit fallback preference behavior.
- CR-1003 focused evidence: Kafka consumer tests passed with 26 tests; scoped Ruff lint and format
  checks passed; `BaseConsumer._send_to_dlq_async` improved from `B (10)` to `A (5)`, and all
  extracted DLQ payload/header/publish/delivery/key helpers are A-ranked while preserving DLQ
  payload, flush, audit, and failure semantics.
- CR-1004 focused evidence: Kafka consumer tests passed with 28 tests; scoped Ruff lint and format
  checks passed; `BaseConsumer.shutdown` improved from `B (8)` to `A (3)`, and all extracted
  shutdown helpers are A-ranked while direct tests prove wakeup failure continuation and close
  failure logging.
- CR-1005 focused evidence: Kafka consumer tests passed with 28 tests; scoped Ruff lint and format
  checks passed; `BaseConsumer.run` improved from `C (18)` to `C (13)`, and all extracted run-loop
  commit-policy helpers are A-ranked while preserving existing commit and non-commit tests.
- CR-1006 focused evidence: Kafka consumer tests passed with 30 tests; scoped Ruff lint and format
  checks passed; `BaseConsumer.run` improved from `C (13)` to `A (5)`, `_process_polled_message`
  reports `A (4)`, and direct tests cover fatal and non-fatal consumer poll-error behavior.
- CR-1007 focused evidence: runtime supervision tests passed with 7 tests; scoped Ruff lint and
  format checks passed; `wait_for_shutdown_or_task_failure` improved from `C (15)` to `A (5)`, all
  extracted failure-attribution helpers are A-ranked, and `shutdown_runtime_components` remains
  `C (18)` as the next separate teardown hotspot.
- CR-1008 focused evidence: runtime supervision tests passed with 7 tests; scoped Ruff lint and
  format checks passed; `shutdown_runtime_components` improved from `C (18)` to `A (1)`, every
  function in `runtime_supervision.py` reports A-ranked cyclomatic complexity, and the module
  remains A-ranked maintainability at `A (51.77)`.
- CR-1009 focused evidence: OpenAPI enrichment tests passed with 6 tests; scoped Ruff lint and
  format checks passed; `infer_example` improved from `C (11)` to `A (3)`, `infer_description`
  improved from `C (14)` to `A (2)`, and direct tests pin example and description precedence.
- CR-1010 focused evidence: OpenAPI enrichment tests passed with 6 tests; scoped Ruff lint and
  format checks passed; `_infer_number_example` improved from `B (8)` to `A (3)`,
  `_infer_string_like_example` improved from `B (8)` to `A (4)`, `make openapi-gate` passed, and
  `openapi_examples.py` improved from `B (16.35)` to `B (17.47)` maintainability.
- CR-1011 focused evidence: OpenAPI enrichment tests passed with 6 tests; scoped Ruff lint and
  format checks passed; `_typed_example` improved from `B (6)` to `A (3)`, `make openapi-gate`
  passed, and `openapi_examples.py` improved from `B (17.47)` to `B (17.91)` maintainability.
- CR-1012 focused evidence: OpenAPI enrichment tests passed with 8 tests; scoped Ruff lint and
  format checks passed; `_build_union_example` improved from `B (8)` to `A (4)`, `make openapi-gate`
  passed, and direct allOf/oneOf tests pin existing generated example behavior.
- CR-1013 focused evidence: OpenAPI enrichment tests passed with 10 tests; scoped Ruff lint and
  format checks passed; `_build_object_example` improved from `B (7)` to `A (4)`, `make openapi-gate`
  passed, and direct tests pin current empty-property fallback behavior.
- CR-1014 focused evidence: OpenAPI enrichment tests passed with 12 tests; scoped Ruff lint and
  format checks passed; `build_schema_example` improved from `B (10)` to `A (4)`, `make openapi-gate`
  passed, and every function in `openapi_examples.py` reports A-ranked cyclomatic complexity.
- CR-1015 focused evidence: reprocessing repository tests passed with 7 tests; scoped Ruff lint and
  format checks passed; `ReprocessingRepository.reprocess_transactions_by_ids` improved from
  `C (11)` to `A (4)`, and every function/class/method in `reprocessing_repository.py` reports
  A-ranked cyclomatic complexity.
- CR-1016 focused evidence: valuation repository worker-metric tests passed with 18 tests; scoped
  Ruff lint and format checks passed; `ValuationRepositoryBase.find_and_reset_stale_jobs` improved
  from `C (14)` to `A (2)`, all stale reset helpers are A-ranked, and broad complexity and
  maintainability gates passed.
- CR-1017 focused evidence: scoped Ruff lint passed; valuation repository worker-metric tests
  passed with 18 tests; `ValuationRepositoryBase.find_contiguous_snapshot_dates` improved from
  `B (8)` to `A (3)`; `valuation_snapshot_contiguity.py` reports `A (41.06)` maintainability;
  PostgreSQL dialect statement compilation passed with and without first-open-date rows; local
  Docker-backed contiguous-snapshot integration tests were attempted but setup failed before
  application code because Docker Desktop was unavailable.
- CR-1018 focused evidence: OpenAPI enrichment tests passed with 12 tests; scoped Ruff lint and
  format checks passed; `make openapi-gate`, `make quality-complexity-gate`, and
  `make quality-maintainability-gate` passed; every function in `openapi_enrichment.py` reports
  A-ranked cyclomatic complexity and the module remains A-ranked maintainability at `A (24.28)`.
- CR-1019 focused evidence: valuation price tests passed with 6 tests; scoped Ruff lint and format
  checks passed; `make quality-complexity-gate` and `make quality-maintainability-gate` passed;
  `resolve_valuation_unit_price` improved from `B (9)` to `A (2)`, every function in
  `valuation_prices.py` reports A-ranked cyclomatic complexity, and the module remains A-ranked
  maintainability at `A (50.48)`.
- CR-1020 focused evidence: reprocessing job repository tests passed with 18 tests; scoped Ruff
  lint and format checks passed; `make quality-complexity-gate` and
  `make quality-maintainability-gate` passed; `ReprocessingJobRepository.find_and_reset_stale_jobs`
  improved from `B (8)` to `A (2)`, every function/class/method in
  `reprocessing_job_repository.py` reports A-ranked cyclomatic complexity, and the module remains
  A-ranked maintainability at `A (42.85)`.
- CR-1021 focused evidence: transaction fee component tests passed with 5 tests; scoped Ruff lint
  and format checks passed; `make quality-complexity-gate` and
  `make quality-maintainability-gate` passed; `resolve_transaction_trade_fee` improved from
  `B (7)` to `A (2)`, every function in `transaction_fee_components.py` reports A-ranked
  cyclomatic complexity, and the module remains A-ranked maintainability at `A (47.90)`.
- CR-1022 focused evidence: Kafka utility tests passed with 7 tests; scoped Ruff lint and format
  checks passed; `make quality-complexity-gate` and `make quality-maintainability-gate` passed;
  `KafkaProducer.publish_message` improved from `B (6)` to `A (3)`, every function/class/method
  in `kafka_utils.py` reports A-ranked cyclomatic complexity, and the module remains A-ranked
  maintainability at `A (57.38)`.
- CR-1023 focused evidence: valuation job repository tests passed with 6 tests; scoped Ruff lint
  and format checks passed; `make quality-complexity-gate` and
  `make quality-maintainability-gate` passed; `ValuationJobRepository.upsert_jobs` improved from
  `B (7)` to `A (4)`, every function/class/method in `valuation_job_repository.py` reports
  A-ranked cyclomatic complexity, and the module remains A-ranked maintainability at `A (47.61)`.
- CR-1024 focused evidence: timeseries repository tests passed with 30 tests; scoped Ruff lint and
  format checks passed; `make quality-complexity-gate` and `make quality-maintainability-gate`
  passed; `TimeseriesRepositoryBase.find_and_reset_stale_jobs` improved from `B (9)` to `A (2)`,
  every stale aggregation job reset helper reports A-ranked cyclomatic complexity, and
  `timeseries_repository_base.py` remains A-ranked maintainability at `A (19.49)`.
- CR-1025 focused evidence: timeseries repository tests passed with 30 tests; scoped Ruff lint and
  format checks passed; `make quality-complexity-gate` and `make quality-maintainability-gate`
  passed; `TimeseriesRepositoryBase.upsert_position_timeseries` and
  `TimeseriesRepositoryBase.upsert_portfolio_timeseries` both improved from `B (6)` to `A (2)`,
  every function/class/method in `timeseries_repository_base.py` reports A-ranked cyclomatic
  complexity, and the module remains A-ranked maintainability at `A (19.94)`.
- CR-1026 focused evidence: cashflow transaction consumer tests passed with 21 tests; scoped Ruff
  lint and format checks passed; `make quality-complexity-gate` and
  `make quality-maintainability-gate` passed; `CashflowCalculatorConsumer._process_message_with_retry`
  improved from `D (24)` to `B (8)`, all extracted helpers report A-ranked cyclomatic complexity,
  and `transaction_consumer.py` remains A-ranked maintainability at `A (37.29)`.
- CR-1027 focused evidence: cashflow transaction consumer tests passed with 21 tests; scoped Ruff
  lint and format checks passed; `make quality-complexity-gate` and
  `make quality-maintainability-gate` passed; `CashflowCalculatorConsumer._get_rule_for_transaction`
  improved from `B (7)` to `A (3)`, all cache lookup helpers report A-ranked cyclomatic
  complexity, and `transaction_consumer.py` remains A-ranked maintainability at `A (36.32)`.
- CR-1028 focused evidence: cashflow transaction consumer tests passed with 21 tests; scoped Ruff
  lint and format checks passed; `make quality-complexity-gate` and
  `make quality-maintainability-gate` passed;
  `CashflowCalculatorConsumer._process_validated_cashflow_event` improved from `B (7)` to
  `A (4)`, all extracted decision helpers report A-ranked cyclomatic complexity, and
  `transaction_consumer.py` remains A-ranked maintainability at `A (34.42)`.
- CR-1029 focused evidence: cashflow transaction consumer tests passed with 21 tests; scoped Ruff
  lint and format checks passed; `make quality-complexity-gate` and
  `make quality-maintainability-gate` passed;
  `CashflowCalculatorConsumer._process_message_with_retry` improved from `B (8)` to `A (2)`,
  every function/class/method in `transaction_consumer.py` reports A-ranked cyclomatic complexity,
  and the module remains A-ranked maintainability at `A (33.48)`.
- CR-1030 focused evidence: cashflow logic tests passed with 35 tests; scoped Ruff lint and format
  checks passed; `make quality-complexity-gate` and `make quality-maintainability-gate` passed;
  `CashflowLogic.calculate` improved from `C (18)` to `A (2)`, and `cashflow_logic.py` remains
  A-ranked maintainability at `A (52.17)`.
- CR-1031 focused evidence: cashflow logic tests passed with 35 tests; scoped Ruff lint and format
  checks passed; `make quality-complexity-gate` and `make quality-maintainability-gate` passed;
  `_signed_cashflow_amount` improved from `B (7)` to `A (4)`, every function/class/method in
  `cashflow_logic.py` reports A-ranked cyclomatic complexity, and the module remains A-ranked
  maintainability at `A (52.93)`.
- CR-1032 focused evidence: cost calculator consumer tests passed with 26 tests; scoped Ruff lint
  and format checks passed; `make quality-complexity-gate` and
  `make quality-maintainability-gate` passed; `CostCalculatorConsumer.process_message` improved
  from `C (11)` to `A (2)`, and `consumer.py` remains A-ranked maintainability at `A (22.35)`.

## Incremental Maintainability Updates

- CR-949 extracted A-ranked `reference_integration_transaction_cost_dto.py` and
  `reference_integration_benchmark_market_series_dto.py`, reducing
  `reference_integration_dto.py` from 3,637 SLOC to 3,264 SLOC and improving it from `C (0.00)`
  to `C (1.33)`. The module remains an active C-ranked hotspot requiring further DTO-family
  extractions.
- CR-950 extracted A-ranked `reference_integration_market_data_coverage_dto.py`, reducing
  `reference_integration_dto.py` from 3,264 SLOC to 3,078 SLOC and improving it from `C (1.33)`
  to `C (4.62)`. The module remains an active C-ranked hotspot.
- CR-951 extracted A-ranked `reference_integration_portfolio_tax_lot_dto.py`, reducing
  `reference_integration_dto.py` from 3,078 SLOC to 2,922 SLOC and improving it from `C (4.62)`
  to `C (6.70)`. The module remains an active C-ranked hotspot.
- CR-952 extracted A-ranked `reference_integration_instrument_eligibility_dto.py` and
  `reference_integration_dpm_source_readiness_dto.py`, reducing `reference_integration_dto.py`
  from 2,922 SLOC to 2,639 SLOC and improving it from `C (6.70)` to `B (11.49)`. This removes
  `reference_integration_dto.py` from the active non-generated C-ranked source hotspot list.
- CR-953 extracted A-ranked `ingestion_record_status.py`, reducing
  `IngestionJobService.get_job_record_status` from `C (20)` to `A (4)` and shrinking
  `ingestion_job_service.py` from 1,656 SLOC to 1,633 SLOC. The service remains an active C-ranked
  maintainability hotspot requiring additional focused extractions.
- CR-954 extracted A-ranked `ingestion_operating_band.py`, moving the C-ranked operating-band
  classifier out of `ingestion_job_service.py` and reducing the service from 1,633 SLOC to 1,545
  SLOC. The service remains an active C-ranked maintainability hotspot requiring additional focused
  extractions.
- CR-955 extracted A-ranked `ingestion_slo_status.py`, reducing
  `IngestionJobService.get_slo_status` from `C (17)` to `A (3)` and shrinking the service from
  1,545 SLOC to 1,477 SLOC. The service remains an active C-ranked maintainability hotspot
  requiring additional focused extractions.
- CR-956 extracted A-ranked `ingestion_backlog_breakdown.py`, reducing
  `IngestionJobService.get_backlog_breakdown` from `C (13)` to `A (3)` and shrinking the service
  from 1,477 SLOC to 1,419 SLOC. The service improves to `C (0.81)` but remains an active
  C-ranked maintainability hotspot.
- CR-957 extracted A-ranked `ingestion_job_listing.py`, reducing `IngestionJobService.list_jobs`
  from `C (11)` to `A (4)` and removing the final C-ranked method from the service. The service
  improves to `C (2.32)` but remains an active C-ranked maintainability hotspot.
- CR-958 extracted tax-rule validation helpers inside `reference_data_dto.py`, reducing
  `ClientTaxRuleSetRecord.validate_rule` from `C (12)` to `A (1)` and removing the only C-ranked
  method from the module. `reference_data_dto.py` remains an active C-ranked maintainability
  hotspot because of size and remaining B-ranked DTO classes/validators.
- CR-959 extracted A-ranked `reference_data_tax_dto.py` for the client tax profile and tax
  rule-set DTO family, reducing `reference_data_dto.py` from 1,686 SLOC to 1,511 SLOC and
  improving it from `C (0.00)` to `C (1.05)`. The original module remains an active C-ranked
  hotspot requiring further DTO-family extractions.
- CR-960 extracted A-ranked `reference_data_client_preference_dto.py` for the client restriction
  and sustainability preference DTO family, reducing `reference_data_dto.py` from 1,511 SLOC to
  1,376 SLOC and improving it from `C (1.05)` to `C (6.43)`. The original module remains an
  active C-ranked hotspot requiring further DTO-family extractions.
- CR-961 extracted A-ranked `reference_data_instrument_eligibility_dto.py` for the DPM instrument
  eligibility DTO family, reducing `reference_data_dto.py` from 1,376 SLOC to 1,282 SLOC and
  improving it from `C (6.43)` to `B (9.31)`. This removes `reference_data_dto.py` from the
  active non-generated C-ranked source hotspot list.
- CR-962 extracted A-ranked `ingestion_capacity_status.py`, reducing
  `IngestionJobService.get_capacity_status` from `B (9)` to `A (1)` and shrinking
  `ingestion_job_service.py` from 1,420 SLOC to 1,304 SLOC. The service improves from `C (2.32)`
  to `C (5.70)` and remains the remaining active non-generated C-ranked source hotspot.
- CR-963 extracted A-ranked `ingestion_error_budget_status.py`, reducing
  `IngestionJobService.get_error_budget_status` from `B (9)` to `A (1)` and shrinking
  `ingestion_job_service.py` from 1,304 SLOC to 1,207 SLOC. The service improves from `C (5.70)`
  to `C (8.17)` and remains the remaining active non-generated C-ranked source hotspot.
- CR-964 extracted A-ranked `ingestion_retry_guardrails.py`, reducing
  `IngestionJobService.assert_retry_allowed_for_records` from `B (9)` to `A (1)` and improving
  `ingestion_job_service.py` from `C (8.17)` to `B (9.82)`. This clears the active
  non-generated C-ranked source hotspot list.
- CR-965 extracted A-ranked `ingestion_reprocessing_queue_health.py`, reducing
  `IngestionJobService.get_reprocessing_queue_health` from `B (7)` to `A (1)` and improving
  `ingestion_job_service.py` from `B (9.82)` to `B (11.79)`.
- CR-966 extracted A-ranked `ingestion_replay_audits.py`, reducing
  `IngestionJobService.list_replay_audits` from `B (7)` to `A (1)` and improving
  `ingestion_job_service.py` from `B (11.79)` to `B (12.63)`.
- CR-967 extracted A-ranked `ingestion_consumer_lag.py`, reducing
  `IngestionJobService.get_consumer_lag` from `B (6)` to `A (1)` and improving
  `ingestion_job_service.py` from `B (12.63)` to `B (13.77)`.
- CR-968 extracted A-ranked `ingestion_health_summary.py`, reducing
  `IngestionJobService.get_health_summary` from `B (6)` to `A (1)` and improving
  `ingestion_job_service.py` from `B (13.77)` to `B (15.15)`.
- CR-969 extracted A-ranked `ingestion_idempotency_diagnostics.py`, reducing
  `IngestionJobService.get_idempotency_diagnostics` from `B (7)` to `A (1)` and improving
  `ingestion_job_service.py` from `B (15.15)` to `B (16.96)` with no remaining B-ranked service methods.
- CR-970 split shared event supportability catalog validation into focused helper validators,
  reducing `validate_event_supportability_catalog` from `E (39)` to `A (5)` while keeping all
  extracted helper functions A-ranked and `event_supportability.py` at `A (26.87)` maintainability.
- CR-971 split source-data security profile validation into focused helper validators, reducing
  `_validate_source_data_security_profiles` from `D (25)` to `A (4)` while keeping all touched
  helper functions A-ranked and `source_data_security.py` at `A (29.23)` maintainability.
- CR-972 split shared outbox dispatcher batch orchestration into focused helper validators,
  reducing `OutboxDispatcher._process_batch_sync` from `E (33)` to `A (2)` while keeping all
  dispatcher methods/outbox helper functions A-ranked and `outbox_dispatcher.py` at `A (40.41)`
  maintainability.
- CR-973 split enterprise readiness runtime policy into focused helper validators, reducing
  `EnterpriseReadinessRuntime.validate_enterprise_runtime_config` from `C (14)` to `A (5)` and
  `EnterpriseReadinessRuntime.authorize_request` from `C (18)` to `A (4)` while leaving the full
  module A-ranked by cyclomatic complexity.
- CR-974 split canonical FX transaction validation into focused helper validators, reducing
  `validate_fx_transaction` from `E (37)` to `A (1)` while leaving the full FX validation module
  A-ranked by cyclomatic complexity and `A (27.02)` maintainability.
- CR-975 split canonical INTEREST transaction validation into focused helper validators, reducing
  `validate_interest_transaction` from `D (29)` to `A (1)` while leaving the full INTEREST
  validation module A-ranked by cyclomatic complexity and `A (33.41)` maintainability.
- CR-976 split canonical SELL transaction validation into focused helper validators, reducing
  `validate_sell_transaction` from `C (14)` to `A (1)` while leaving the full SELL validation
  module A-ranked by cyclomatic complexity and `A (42.80)` maintainability.
- CR-977 split canonical BUY transaction validation into focused helper validators, reducing
  `validate_buy_transaction` from `C (14)` to `A (1)` while leaving the full BUY validation
  module A-ranked by cyclomatic complexity and `A (42.80)` maintainability.
- CR-978 split canonical DIVIDEND transaction validation into focused helper validators, reducing
  `validate_dividend_transaction` from `D (21)` to `A (1)` while leaving the full DIVIDEND
  validation module A-ranked by cyclomatic complexity and `A (37.73)` maintainability.
- CR-979 split CA Bundle A transaction validation into focused helper validators, reducing
  `validate_ca_bundle_a_transaction` from `D (22)` to `A (2)` while leaving the full CA Bundle A
  validation module A-ranked by cyclomatic complexity and `A (38.16)` maintainability.
- CR-980 split adjustment cash-leg generation into focused helper validators, reducing
  `_resolve_adjustment_amount_and_direction` from `C (11)` to `A (3)` and
  `build_auto_generated_adjustment_cash_leg` from `B (9)` to `A (1)` while leaving the full
  adjustment cash-leg module A-ranked by cyclomatic complexity and `A (37.29)` maintainability.
- CR-981 split upstream cash-leg pairing validation into focused helper validators, reducing
  `validate_upstream_cash_leg_pairing` from `C (12)` to `A (1)` while leaving the full dual-leg
  pairing module A-ranked by cyclomatic complexity and `A (56.95)` maintainability.
- CR-982 split FX baseline processing into focused helper validators, reducing
  `build_fx_processed_event` from `C (14)` to `A (2)` while leaving the full FX baseline
  processing module A-ranked by cyclomatic complexity and `A (65.60)` maintainability.
- CR-983 split FX contract instrument construction into focused helper validators, reducing
  `build_fx_contract_instrument_event` from `C (13)` to `A (5)` while leaving the full FX contract
  instrument module A-ranked by cyclomatic complexity and `A (51.08)` maintainability.
- CR-984 split FX linkage enrichment into focused helper validators, reducing
  `enrich_fx_transaction_metadata` from `B (7)` to `A (2)`, `_resolve_fx_contract_id` from
  `B (6)` to `A (4)`, and `_resolve_contract_lifecycle_transaction_ids` from `B (7)` to `A (3)`
  while leaving the full FX linkage module A-ranked by cyclomatic complexity and `A (42.62)`
  maintainability.
- CR-985 split BUY linkage enrichment into focused helper validators, reducing
  `enrich_buy_transaction_metadata` from `B (6)` to `A (2)` while leaving the full BUY linkage
  module A-ranked by cyclomatic complexity and `A (73.51)` maintainability.
- CR-986 split SELL linkage enrichment into focused helper validators, reducing
  `enrich_sell_transaction_metadata` from `B (7)` to `A (2)` while leaving the full SELL linkage
  module A-ranked by cyclomatic complexity and `A (67.86)` maintainability.
- CR-987 split INTEREST linkage enrichment into focused helper validators, reducing
  `enrich_interest_transaction_metadata` from `B (6)` to `A (2)` while leaving the full INTEREST
  linkage module A-ranked by cyclomatic complexity and `A (71.82)` maintainability.
- CR-988 split DIVIDEND linkage enrichment into focused helper validators, reducing
  `enrich_dividend_transaction_metadata` from `B (6)` to `A (2)` while leaving the full DIVIDEND
  linkage module A-ranked by cyclomatic complexity and `A (71.82)` maintainability.
- CR-989 split CA Bundle A reconciliation into focused helper validators, reducing
  `evaluate_ca_bundle_a_reconciliation` from `B (8)` to `A (2)` while leaving the full CA Bundle A
  reconciliation module A-ranked by cyclomatic complexity and `A (39.54)` maintainability.
- CR-990 split CA Bundle A dependency ordering into explicit rank-type sets and a deterministic
  dependency-rank lookup, reducing `ca_bundle_a_dependency_rank` from `B (8)` to `A (1)` while
  leaving the full CA Bundle A ordering module A-ranked by cyclomatic complexity and `A (89.61)`
  maintainability.
- CR-991 split analytics cashflow semantics classification into a typed static semantics map and
  focused transfer-flow helper, reducing `classify_analytics_cash_flow` from `B (10)` to `A (3)`
  while leaving the full analytics cashflow semantics module A-ranked by cyclomatic complexity and
  `A (74.86)` maintainability.
- CR-992 split market reference point classification into explicit pre-observation and
  observed-status maps plus a focused point-status helper, reducing
  `classify_market_reference_point` from `B (8)` to `A (1)` while leaving the full market reference
  quality module A-ranked by cyclomatic complexity and `A (36.36)` maintainability.
- CR-993 split reconciliation quality classification into validation helpers, status-decision
  helpers, a run-status classification map, and small blocking/partial predicates, reducing
  `classify_reconciliation_status` from `B (9)` to `A (2)` and
  `classify_data_quality_coverage` from `B (7)` to `A (1)` while leaving the full reconciliation
  quality module A-ranked by cyclomatic complexity and `A (33.27)` maintainability.
- CR-994 split ingestion outcome classification into count validation, terminal-failure counting,
  partial-outcome detection, and valid-outcome classification helpers, reducing
  `classify_ingestion_outcome` from `B (6)` to `A (1)` while leaving the full ingestion evidence
  module A-ranked by cyclomatic complexity and `A (37.92)` maintainability.
- CR-995 split reconstruction identity scope payload construction into reconstruction scope
  validation and transaction-window validation helpers, reducing `_canonical_scope_payload` from
  `B (7)` to `A (1)` while leaving the full reconstruction identity module A-ranked by cyclomatic
  complexity and `A (44.37)` maintainability.
- CR-996 split shared database URL scheme normalization into legacy-postgres, async-driver,
  sync-driver, and scheme-replacement helpers, reducing `_normalize_database_url_scheme` from
  `B (6)` to `A (2)` while leaving the full shared DB helper module A-ranked by cyclomatic
  complexity and `A (66.86)` maintainability.
- CR-997 split Kafka topic verification into admin-client construction, required-topic
  verification, existing-topic metadata lookup, and missing-topic calculation helpers, reducing
  `ensure_topics_exist` from `B (6)` to `A (3)` while leaving the full Kafka admin module A-ranked
  by cyclomatic complexity and `A (88.15)` maintainability.
- CR-998 split shared config integer environment parsing into safe-default, environment-loading,
  and minimum-enforcement helpers, reducing `_env_int` from `B (7)` to `A (1)` while leaving
  `config.py` A-ranked maintainability at `A (35.12)`.
- CR-999 split Kafka consumer config value coercion into type-specific coercion, integer parsing,
  positive-integer enforcement, and `auto.offset.reset` normalization helpers, reducing
  `_coerce_consumer_config_value` from `C (16)` to `A (4)` while leaving `config.py` A-ranked
  maintainability at `A (34.38)`.
- CR-1000 split Kafka consumer runtime override loading into defaults loading, group override
  loading, group sanitization, and group-context helpers, reducing
  `get_kafka_consumer_runtime_overrides` from `B (7)` to `A (1)` while leaving `config.py`
  A-ranked maintainability at `A (33.36)`.
- CR-1001 split Kafka consumer DLQ reason classification into explicit ordered token groups and
  focused matching helpers, reducing `classify_dlq_reason_code` from `C (12)` to `A (5)` while
  leaving `kafka_consumer.py` A-ranked maintainability at `A (38.68)`.
- CR-1002 split Kafka consumer message-correlation context selection into current/header/fallback
  resolution helpers, reducing `BaseConsumer._message_correlation_context` from `B (7)` to
  `A (3)` while leaving `kafka_consumer.py` A-ranked maintainability at `A (37.37)`.
- CR-1003 split Kafka consumer DLQ publication into payload, header, publish,
  delivery-confirmation, and key-decoding helpers, reducing `BaseConsumer._send_to_dlq_async` from
  `B (10)` to `A (5)` while leaving `kafka_consumer.py` A-ranked maintainability at `A (34.02)`.
- CR-1004 split Kafka consumer shutdown into shutdown log-context, wakeup, close, and DLQ producer
  flush helpers, reducing `BaseConsumer.shutdown` from `B (8)` to `A (3)` while leaving
  `kafka_consumer.py` A-ranked maintainability at `A (31.86)`.
- CR-1005 split Kafka consumer run-loop commit policy into successful-processing commit,
  successful-DLQ-publication commit, DLQ-publication-failure logging, and message log-context
  helpers, reducing `BaseConsumer.run` from `C (18)` to `C (13)` while leaving `kafka_consumer.py`
  A-ranked maintainability at `A (31.23)`.
- CR-1006 split Kafka consumer run-loop orchestration into poll-error handling, per-message
  processing, sync/async dispatch, retryable/terminal processing-error handling, and metrics
  helpers, reducing `BaseConsumer.run` from `C (13)` to `A (5)` while leaving
  `kafka_consumer.py` A-ranked maintainability at `A (28.49)`.
- CR-1007 split runtime supervision failure attribution into completed-task selection,
  exception-task selection, cancelled-task selection, and runtime-error construction helpers,
  reducing `wait_for_shutdown_or_task_failure` from `C (15)` to `A (5)` while leaving
  `runtime_supervision.py` A-ranked maintainability at `A (56.39)`.
- CR-1008 split runtime supervision teardown into consumer shutdown, stop-callback execution,
  server exit signaling, runtime-task awaiting, timeout handling, task-name extraction,
  pending-task cancellation, and teardown error logging helpers, reducing
  `shutdown_runtime_components` from `C (18)` to `A (1)` and leaving every function in
  `runtime_supervision.py` A-ranked by cyclomatic complexity.
- CR-1009 split shared OpenAPI inference into known-key examples, enum examples, typed examples,
  formatted examples, rule-based description selection, and description predicate/formatter
  helpers, reducing `infer_example` from `C (11)` to `A (3)` and `infer_description` from
  `C (14)` to `A (2)`.
- CR-1010 split shared OpenAPI numeric and string-like example classification into explicit
  token-rule tables and token-matching helpers, reducing `_infer_number_example` from `B (8)` to
  `A (3)`, `_infer_string_like_example` from `B (8)` to `A (4)`, and improving
  `openapi_examples.py` maintainability from `B (16.35)` to `B (17.47)`.
- CR-1011 split shared OpenAPI typed-example dispatch into static and dynamic typed-example maps
  plus focused array, integer, and number builders, reducing `_typed_example` from `B (6)` to
  `A (3)` and improving `openapi_examples.py` maintainability from `B (17.47)` to `B (17.91)`.
- CR-1012 split shared OpenAPI union example generation into union variant lookup, union-key
  dispatch, and non-empty allOf normalization helpers, reducing `_build_union_example` from
  `B (8)` to `A (4)` with direct allOf and oneOf tests.
- CR-1013 split shared OpenAPI object example generation into schema-property, required-property,
  property-example, and property-inclusion helpers, reducing `_build_object_example` from `B (7)`
  to `A (4)` with direct tests pinning current empty-property fallback behavior.
- CR-1014 split shared OpenAPI schema example orchestration into candidate selection,
  structured-schema, fallback-example, and fallback property-name helpers, reducing
  `build_schema_example` from `B (10)` to `A (4)` and leaving every `openapi_examples.py`
  function A-ranked by cyclomatic complexity.
- CR-1015 split shared reprocessing replay orchestration into ordered-id, ordered-query, fetch,
  no-match logging, correlation-header, publish, publish-failure, and flush verification helpers,
  reducing `ReprocessingRepository.reprocess_transactions_by_ids` from `C (11)` to `A (4)` and
  leaving every `reprocessing_repository.py` function/class/method A-ranked by cyclomatic
  complexity.
- CR-1016 split shared valuation stale-job reset orchestration into stale-row retrieval, stale-row
  grouping, stale-job ID classification, superseded update construction, failed update
  construction, reset update construction, and shared processing-state update predicate helpers,
  reducing `ValuationRepositoryBase.find_and_reset_stale_jobs` from `C (14)` to `A (2)`.
- CR-1017 split shared valuation snapshot-contiguity query construction into a dedicated
  `valuation_snapshot_contiguity.py` module for first-open-date table construction, date-series
  generation, snapshot/history reconciliation, gap detection, latest-snapshot fallback, optional
  join construction, and row mapping, reducing
  `ValuationRepositoryBase.find_contiguous_snapshot_dates` from `B (8)` to `A (3)`.
- CR-1018 split shared OpenAPI enrichment helpers for operation discovery, parameter example
  eligibility, explicit schema-example extraction, media-content example eligibility, and error
  response detection, leaving every function in `openapi_enrichment.py` A-ranked by cyclomatic
  complexity.
- CR-1019 split shared valuation price policy helpers for bond percent-quote normalization
  eligibility, product-type normalization, legacy percent-quote detection, and ratio-based
  multiplier selection, reducing `resolve_valuation_unit_price` from `B (9)` to `A (2)`.
- CR-1020 split shared reprocessing stale-job reset helpers for stale-row retrieval, over-limit
  and retryable classification, failed/reset update construction, and shared processing-state
  update predicates, reducing `ReprocessingJobRepository.find_and_reset_stale_jobs` from `B (8)`
  to `A (2)`.
- CR-1021 split shared transaction fee policy helpers for optional fee validation, component
  presence detection, component totaling, component validation, and non-negative amount
  enforcement, reducing `resolve_transaction_trade_fee` from `B (7)` to `A (2)`.
- CR-1022 split shared Kafka producer publish helpers for publish-header construction, key
  encoding, delivery-report callback construction, outbox-id extraction/decoding, delivery
  success/failure handling, delivery log context, message-key representation, and guarded
  delivery-callback notification, reducing `KafkaProducer.publish_message` from `B (6)` to
  `A (3)`.
- CR-1023 split shared valuation job upsert helpers for eligible job filtering, upsert execution,
  insert value construction, conflict update values, conflict update predicates, and staged upsert
  logging, reducing `ValuationJobRepository.upsert_jobs` from `B (7)` to `A (4)`.
- CR-1024 split shared timeseries stale aggregation job reset helpers for stale-row retrieval,
  over-limit and retryable stale-job classification, failed update construction, reset update
  construction, shared processing-state update predicates, failed-job marking, and retryable-job
  reset, reducing `TimeseriesRepositoryBase.find_and_reset_stale_jobs` from `B (9)` to `A (2)`.
- CR-1025 split shared position and portfolio timeseries upsert helpers for statement-specific
  construction, shared insert-value extraction, shared conflict-update values, and PostgreSQL
  conflict-update assembly, reducing both upsert methods from `B (6)` to `A (2)`.
- CR-1026 split cashflow calculator consumer message processing into transaction-scoped
  processing, idempotency claim helpers, stale replay detection, semantic duplicate claiming,
  transaction contract validation, non-cash lifecycle classification, required rule lookup,
  cashflow calculation staging, and `CashflowCalculatedEvent` construction, reducing
  `_process_message_with_retry` from `D (24)` to `B (8)`.
- CR-1027 split cashflow calculator rule-cache lookup into fresh-cache lookup, direct cache lookup,
  stale/missing cache refresh, and missing-rule reload helpers, reducing
  `_get_rule_for_transaction` from `B (7)` to `A (3)`.
- CR-1028 split cashflow calculator validated-event processing into physical/stale-replay
  early-stop helpers, epoch/semantic-duplicate early-stop helpers, and cashflow staging or
  non-cash lifecycle skip helpers, reducing `_process_validated_cashflow_event` from `B (7)` to
  `A (4)`.
- CR-1029 split cashflow calculator retry/DLQ wrapper processing into message metadata, decoded
  event processing, and cashflow processing error-classification helpers, reducing
  `_process_message_with_retry` from `B (8)` to `A (2)`.
- CR-1030 split cashflow calculation into base amount, interest amount,
  classification/direction sign, interest sign, adjustment sign, and transfer sign helpers,
  reducing `CashflowLogic.calculate` from `C (18)` to `A (2)`.
- CR-1031 split cashflow sign dispatch into an explicit classification sign-factor map and focused
  classification sign helper, reducing `_signed_cashflow_amount` from `B (7)` to `A (4)`.
- CR-1032 split cost calculator process-message handling into message metadata, valid cost-event
  processing, process-message error classification, and failure metric helpers, reducing
  `CostCalculatorConsumer.process_message` from `C (11)` to `A (2)`.
