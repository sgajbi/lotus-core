# lotus-core Quality Scorecard

Status: Initial scorecard baseline on 2026-06-02.

| Category | Current Baseline | Target Direction |
| --- | --- | --- |
| Python code size | 1,040 files / 213,290 lines under `src` and `tests` | Reduce generated/duplicated quality surface and split large modules |
| Ruff findings | 0 findings under `python -m ruff check . --statistics`; enforced by `make quality-ruff-gate` and the quality-baseline Ruff regression job | Keep Ruff lint regression-free while broader gates continue to ratchet |
| Ruff format | Clean and enforced by `make quality-ruff-format-gate` plus the quality-baseline Ruff format job after CR-866 | Keep Ruff formatting regression-free while broader gates continue to ratchet |
| Typecheck | Clean for the configured query-service DTO/router scope under `make typecheck`; enforced by the quality-baseline typecheck job after CR-869 | Expand typed source scope progressively without weakening the gate |
| Test collection | 3,575 collected; import/plugin blockers fixed; full all-suite collection stops at governed mixed-runtime guard | Run runtime-separated collection lanes cleanly |
| Coverage | `make coverage-gate` now passes after CR-969 with branch-aware combined unit + integration-lite coverage at 98% (`2,918` unit tests plus `121` integration-lite tests; threshold `98`) | Keep coverage gate regression-free and broaden runtime-separated coverage evidence for PR Merge Gate |
| Complexity | Broad source Xenon gate is clean and enforced after CR-882 with `make quality-complexity-gate`; CR-880 reduced advisory proposal simulation from F to B, CR-881 reduced the cost-calculator consumer from F to C, CR-882 reduced FX linkage from D to B, CR-885 reduced `get_load_run_progress` from D to A, CR-886 reduced `_apply_reconciliation_run_scope` from C to A, CR-887 reduced `_apply_valuation_job_scope` from B to A, CR-888 reduced `_apply_aggregation_job_scope` from B to A, CR-889 reduced `_apply_portfolio_control_stage_scope` from B to A, CR-890 reduced `_apply_reprocessing_job_scope` from B to A, CR-891 reduced `_apply_current_position_history_scope` from B to A, CR-892 reduced valuation and aggregation health summary methods from B to A, CR-893 reduced analytics export health summary from B to A, CR-894 reduced missing historical FX dependency summary from B to A, CR-895 reduced `get_lineage_keys` from B to A, removing the remaining B-ranked method from `operations_repository.py`, CR-896 reduced `list_latest_fx_rates` from B to A, CR-897 reduced `list_dpm_portfolio_universe_candidates` from B to A, CR-898 reduced operations runtime-state wrapper methods to A-ranked complexity, CR-899 reduced `get_position_timeseries` from E to C, CR-900 reduced `get_core_snapshot` from E to A, CR-901 reduced `_resolve_projected_positions` from E to A, CR-902 reduced `_resolve_baseline_positions` from D to A, CR-903 reduced `get_instrument_enrichment_bulk` from C to A, CR-904 reduced `_validated_simulation_session` from B to A, CR-905 reduced `_build_delta_section` from B to A, CR-906 removed the final B-ranked method from `core_snapshot_service.py`, CR-908 reduced `_portfolio_observation_rows` from D to A, CR-909 reduced `_effective_beginning_market_value` from C to A, CR-910 reduced `_latest_available_performance_date` from C to A, CR-911 reduced `_resolve_window` from C to A, CR-912 reduced `get_portfolio_timeseries` from C to A, CR-913 reduced `get_position_timeseries` from C to A, CR-914 reduced `create_export_job` from B to A, CR-915 reduced `_reserve_export_job` from B to A, CR-916 reduced `_jsonable` from B to A, CR-917 reduced `get_export_result_ndjson` from B to A, and CR-918 kept extracted analytics export job helpers A-ranked | Keep broad complexity regression-free while reducing remaining B/C hotspots by domain priority |
| Maintainability | No D/E/F source modules; enforced after CR-879 by `make quality-maintainability-gate`; CR-883 removed `openapi_enrichment.py` from the C-ranked hotspot list, CR-884 improved `reference_data_repository.py` from `C (4.26)` to `C (6.94)`, CR-896 improved it again to `C (7.55)`, CR-897 improved it again to `C (8.74)`, CR-898 improved `operations_service.py` from `C (5.44)` to `B (9.91)`, reducing the C-hotspot count from 8 to 7, CR-907 extracted an A-ranked `core_snapshot_calculations.py` module while reducing `core_snapshot_service.py` from 1,208 SLOC / 518 LLOC to 1,093 SLOC / 464 LLOC, CR-918 extracted A-ranked `analytics_export_jobs.py` while reducing `analytics_timeseries_service.py` from 1,844 SLOC to 1,770 SLOC, CR-919 extracted A-ranked `analytics_page_tokens.py` while reducing `analytics_timeseries_service.py` to 1,751 SLOC, CR-920 extracted A-ranked `analytics_windows.py` while reducing `analytics_timeseries_service.py` to 1,707 SLOC, CR-921 extracted A-ranked `analytics_cash_flows.py` while reducing `analytics_timeseries_service.py` to 1,590 SLOC, CR-922 extracted A-ranked `analytics_fx_rates.py` while reducing `analytics_timeseries_service.py` to 1,582 SLOC, CR-923 extracted A-ranked `analytics_pagination.py` while reducing `analytics_timeseries_service.py` to 1,548 SLOC, CR-924 extracted A-ranked `analytics_quality.py` while reducing `analytics_timeseries_service.py` to 1,536 SLOC, CR-925 extracted A-ranked `analytics_position_pages.py` while reducing `analytics_timeseries_service.py` to 1,523 SLOC, CR-926 extracted A-ranked `analytics_portfolio_pages.py` while reducing `analytics_timeseries_service.py` to 1,513 SLOC and improving it to `C (1.52)`, CR-927 extracted A-ranked `analytics_position_responses.py` while reducing `analytics_timeseries_service.py` to 1,424 SLOC and improving it to `C (3.48)`, CR-928 extracted A-ranked `analytics_export_execution.py` while reducing `analytics_timeseries_service.py` to 1,402 SLOC and improving it to `C (5.40)`, CR-929 extracted A-ranked `analytics_export_lifecycle.py` while keeping `analytics_timeseries_service.py` at 1,402 SLOC and improving it to `C (6.86)`, CR-930 extracted A-ranked `analytics_export_results.py` while reducing `analytics_timeseries_service.py` to 1,388 SLOC and improving it to `C (7.80)`, CR-931 removed stale analytics quality wrapper methods while reducing the active service to 1,325 SLOC and improving it to `B (9.21)`, CR-932 extracted A-ranked `core_snapshot_instrument_enrichment.py` while reducing `core_snapshot_service.py` to 1,067 SLOC, CR-933 extracted A-ranked `core_snapshot_baseline_metadata.py` while reducing `core_snapshot_service.py` to 1,018 SLOC and improving it to `C (2.18)`, CR-934 extracted A-ranked `core_snapshot_baseline_positions.py` while reducing `core_snapshot_service.py` to 896 SLOC and improving it to `C (6.12)`, CR-935 extracted A-ranked `core_snapshot_projected_positions.py` while reducing `core_snapshot_service.py` to 789 SLOC and improving it to `B (12.41)`, CR-936 extracted A-ranked `reference_data_query_helpers.py` while reducing `reference_data_repository.py` to 1,163 SLOC and improving it to `B (9.24)`, CR-937 extracted A-ranked `operations_health_queries.py` while reducing `operations_repository.py` from 2,684 SLOC to 2,522 SLOC, CR-938 extracted A-ranked `operations_missing_fx_queries.py` while reducing `operations_repository.py` to 2,456 SLOC, CR-939 extracted A-ranked `operations_lineage_queries.py` while reducing `operations_repository.py` to 2,388 SLOC, CR-940 extracted A-ranked `operations_position_scope_queries.py` while reducing `operations_repository.py` to 2,211 SLOC, CR-941 extracted A-ranked `operations_load_run_queries.py` while reducing `operations_repository.py` to 1,832 SLOC, CR-942 extracted A-ranked `operations_support_job_queries.py` while reducing `operations_repository.py` to 1,723 SLOC, CR-943 extracted A-ranked `operations_analytics_export_queries.py` while reducing `operations_repository.py` to 1,689 SLOC, CR-944 extracted A-ranked `operations_reconciliation_run_queries.py` while reducing `operations_repository.py` to 1,596 SLOC, CR-945 extracted A-ranked `operations_portfolio_control_queries.py` while reducing `operations_repository.py` to 1,538 SLOC and improving it to `C (0.21)`, CR-946 extracted A-ranked `operations_reprocessing_queries.py` while reducing `operations_repository.py` to 1,403 SLOC and improving it to `C (4.42)`, CR-947 extracted A-ranked `operations_reconciliation_finding_queries.py` while reducing `operations_repository.py` to 1,332 SLOC and improving it to `C (6.24)`, CR-948 expanded A-ranked support-job helpers while reducing `operations_repository.py` to 1,247 SLOC and improving it to `B (9.54)`, CR-952 extracted A-ranked instrument eligibility and DPM source-readiness DTO modules while reducing `reference_integration_dto.py` to 2,639 SLOC and improving it to `B (11.49)`, CR-961 extracted an A-ranked instrument eligibility DTO module while improving `reference_data_dto.py` to `B (9.31)`, and CR-969 improved `ingestion_job_service.py` to `B (16.96)` with no remaining B-ranked service methods; the active non-generated C-ranked source hotspot list is clear, with generated `query_service/build` copies tracked separately | Keep maintainability regression-free while reducing existing C hotspots by domain priority |
| Dead code | Production-source baseline clean and enforced after CR-876 by `make quality-vulture-source-gate` plus the quality-baseline Vulture source dead-code job; broader `src tests` Vulture report remains noisy with fixture-style test parameters | Keep production-source dead-code regression-free while reducing test-fixture Vulture noise in focused batches |
| Dependency usage | Production-source deptry baseline clean and enforced after CR-878 by `make quality-deptry-source-gate` plus the quality-baseline Deptry source dependency job | Keep source dependency hygiene regression-free while broader dependency audit remains report-only |
| Security | Bandit baseline clean and enforced after CR-875 by `make quality-bandit-gate` plus the quality-baseline Bandit security job | Keep Bandit regression-free while broader dependency-audit/security gates continue to ratchet |
| Architecture boundaries | Existing strict architecture guard plus 2 kept import-linter contracts enforced by `make quality-import-boundary-gate` after CR-867 | Add focused import contracts as additional ownership boundaries stabilize |
| OpenAPI governance | Existing OpenAPI quality and API vocabulary gates promoted into the quality-baseline API governance job after CR-868 | Keep API governance regression-free while spectral remains report-only until a stable generated-spec artifact exists |
| Documentation | New top-level governance docs scaffolded; CR-847 records collection/build-artifact cleanup | Keep docs implementation-backed and current |

## Before/After PR Scorecard

This table summarizes the evidence the final PR must carry forward. It is intentionally limited to
measured or explicitly documented improvement so the PR can distinguish completed hardening from
remaining merge-gate risk.

| Area | Baseline / Risk Before This Branch | Current Evidence After CR-1006 | Remaining PR Risk |
| --- | --- | --- | --- |
| Code health | Quality foundation existed, but the refactor started with broad format/lint/collection debt and active source maintainability hotspots to measure and reduce. | Ruff lint and format gates pass; complexity and maintainability gates pass; active non-generated C-ranked source hotspot list is clear; current measured source hotspots are `reference_data_dto.py` `B (9.31)` and `ingestion_job_service.py` `B (16.96)`; CR-974 reduced the canonical FX validator from `E (37)` to `A (1)`; CR-975 reduced the canonical INTEREST validator from `D (29)` to `A (1)`; CR-976 reduced the canonical SELL validator from `C (14)` to `A (1)`; CR-977 reduced the canonical BUY validator from `C (14)` to `A (1)`; CR-978 reduced the canonical DIVIDEND validator from `D (21)` to `A (1)`; CR-979 reduced the CA Bundle A validator from `D (22)` to `A (2)`; CR-980 reduced adjustment cash-leg resolution from `C (11)` to `A (3)` and cash-leg construction from `B (9)` to `A (1)`; CR-981 reduced upstream cash-leg pairing validation from `C (12)` to `A (1)`; CR-982 reduced FX baseline processing from `C (14)` to `A (2)`; CR-983 reduced FX contract instrument construction from `C (13)` to `A (5)`; CR-984 leaves the FX linkage module fully A-ranked by complexity; CR-985 reduced BUY linkage enrichment from `B (6)` to `A (2)`; CR-986 reduced SELL linkage enrichment from `B (7)` to `A (2)`; CR-987 reduced INTEREST linkage enrichment from `B (6)` to `A (2)`; CR-988 reduced DIVIDEND linkage enrichment from `B (6)` to `A (2)`; CR-989 reduced CA Bundle A reconciliation from `B (8)` to `A (2)`; CR-990 reduced CA Bundle A dependency ordering from `B (8)` to `A (1)`; CR-991 reduced analytics cashflow semantics classification from `B (10)` to `A (3)`; CR-992 reduced market reference point classification from `B (8)` to `A (1)`; CR-993 reduced reconciliation quality status classification from `B (9)` to `A (2)` and data-quality coverage classification from `B (7)` to `A (1)`; CR-994 reduced ingestion outcome classification from `B (6)` to `A (1)`; CR-995 reduced reconstruction identity scope payload assembly from `B (7)` to `A (1)`; CR-996 reduced database URL scheme normalization from `B (6)` to `A (2)`; CR-997 reduced Kafka topic verification from `B (6)` to `A (3)`; CR-998 reduced shared config integer env parsing from `B (7)` to `A (1)`; CR-999 reduced Kafka consumer config value coercion from `C (16)` to `A (4)`; CR-1000 reduced Kafka consumer runtime override loading from `B (7)` to `A (1)`; CR-1001 reduced Kafka consumer DLQ reason classification from `C (12)` to `A (5)`; CR-1002 reduced Kafka consumer message-correlation context from `B (7)` to `A (3)`; CR-1003 reduced Kafka consumer DLQ publication from `B (10)` to `A (5)`; CR-1004 reduced Kafka consumer shutdown from `B (8)` to `A (3)`; CR-1005 reduced Kafka consumer run-loop commit policy from `C (18)` to `C (13)`; CR-1006 reduced Kafka consumer run-loop orchestration from `C (13)` to `A (5)`. | Keep generated `query_service/build` copies tracked separately and prevent source hotspot regression before PR. |
| Architecture and modularity | Large services, repositories, and DTO modules carried concentrated logic and weak reviewability across analytics, core snapshot, operations, reference data, and ingestion surfaces. | Focused helper/module extractions moved query, DTO-family, analytics export, core snapshot, operations, and ingestion logic into A-ranked modules; `ingestion_job_service.py` is reduced to `B (16.96)` with no remaining B-ranked service methods. | Final PR narrative must explain the architectural pattern and remaining generated-surface debt without claiming complete platform-wide modularity. |
| OpenAPI and API governance | API governance needed to remain measurable and CI-visible while refactoring preserved behavior. | `make openapi-gate`, `make api-vocabulary-gate`, `make no-alias-gate`, and `make monetary-float-guard` pass in the current evidence snapshot. | Spectral remains report-only until the generated-spec artifact and quality contract are stable enough for enforcement. |
| Tests and coverage | Full all-suite collection was blocked by governed mixed-runtime constraints, and coverage evidence needed a runtime-separated gate rather than an unbounded local rerun. | `make warning-gate` passes with 2,918 unit tests, 9 deselected, and 0 warnings; `make coverage-gate` passes with 98% combined unit + integration-lite coverage after 2,918 unit tests and 121 integration-lite tests. | Keep runtime-separated test lanes as PR truth; do not represent the mixed-runtime collection guard as a full all-suite pass. |
| Security and dependency hygiene | Security posture needed measurable gates beyond source-only linting and report-only dependency checks. | `make quality-bandit-gate` passes with 0 Bandit issues across `src`; `make quality-deptry-source-gate` passes; `make security-audit` passes with dependency consistency clean and no known vulnerabilities, with 2 governed ignores; CR-971 reduced source-data security profile validation from `D (25)` to `A (4)`; CR-973 leaves enterprise readiness policy fully A-ranked by complexity. | PR should list the governed pip-audit ignores explicitly and keep dependency-audit evidence current on the final commit. |
| Observability and operations | Ingestion and operational diagnostics had concentrated logic that was harder to test, review, and support. | CR-953 through CR-969 extracted focused ingestion status, SLO, backlog, capacity, reprocessing, replay audit, consumer-lag, health-summary, and idempotency diagnostics helpers with direct tests for representative operational behavior; CR-972 reduced shared outbox dispatcher batch orchestration from `E (33)` to `A (2)` while preserving metrics and delivery accounting. | Runtime-level observability claims still need to stay scoped to diagnostics modularity and outbox helper refactoring unless additional service bring-up evidence is captured. |
| Documentation and CI measurement | The branch needed baseline measurement, incremental evidence, and a reviewable trail rather than cosmetic cleanup claims. | The quality scorecard, refactor report, baseline evidence, and CR-849 through CR-1006 ledger entries record measurable gate and maintainability movement; GitHub `Remote Feature Lane` passed for `89d051ef`. | The final PR must refresh this row after the latest GitHub run on the final pushed commit is green. |

## Current PR Evidence Snapshot

Local evidence captured on 2026-06-05 after CR-1006:

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
- GitHub `Remote Feature Lane` run `26995543519` => passed for `89d051ef`
- Current measured source hotspots: `reference_data_dto.py` `B (9.31)` and
  `ingestion_job_service.py` `B (16.96)`; active non-generated C-ranked source hotspot list is
  clear.
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
