# lotus-core Quality Scorecard

Status: Initial scorecard baseline on 2026-06-02.

| Category | Current Baseline | Target Direction |
| --- | --- | --- |
| Python code size | 1,040 files / 213,290 lines under `src` and `tests` | Reduce generated/duplicated quality surface and split large modules |
| Ruff findings | 0 findings under `python -m ruff check . --statistics`; enforced by `make quality-ruff-gate` and the quality-baseline Ruff regression job | Keep Ruff lint regression-free while broader gates continue to ratchet |
| Ruff format | Clean and enforced by `make quality-ruff-format-gate` plus the quality-baseline Ruff format job after CR-866 | Keep Ruff formatting regression-free while broader gates continue to ratchet |
| Typecheck | Clean for the configured query-service DTO/router scope under `make typecheck`; enforced by the quality-baseline typecheck job after CR-869 | Expand typed source scope progressively without weakening the gate |
| Test collection | 3,575 collected; import/plugin blockers fixed; full all-suite collection stops at governed mixed-runtime guard | Run runtime-separated collection lanes cleanly |
| Coverage | Not measured in initial baseline due collection errors | Add line and branch coverage artifacts after collection is clean |
| Complexity | Broad source Xenon gate is clean and enforced after CR-882 with `make quality-complexity-gate`; CR-880 reduced advisory proposal simulation from F to B, CR-881 reduced the cost-calculator consumer from F to C, CR-882 reduced FX linkage from D to B, CR-885 reduced `get_load_run_progress` from D to A, CR-886 reduced `_apply_reconciliation_run_scope` from C to A, CR-887 reduced `_apply_valuation_job_scope` from B to A, CR-888 reduced `_apply_aggregation_job_scope` from B to A, CR-889 reduced `_apply_portfolio_control_stage_scope` from B to A, CR-890 reduced `_apply_reprocessing_job_scope` from B to A, CR-891 reduced `_apply_current_position_history_scope` from B to A, CR-892 reduced valuation and aggregation health summary methods from B to A, CR-893 reduced analytics export health summary from B to A, CR-894 reduced missing historical FX dependency summary from B to A, CR-895 reduced `get_lineage_keys` from B to A, removing the remaining B-ranked method from `operations_repository.py`, CR-896 reduced `list_latest_fx_rates` from B to A, CR-897 reduced `list_dpm_portfolio_universe_candidates` from B to A, CR-898 reduced operations runtime-state wrapper methods to A-ranked complexity, CR-899 reduced `get_position_timeseries` from E to C, CR-900 reduced `get_core_snapshot` from E to A, CR-901 reduced `_resolve_projected_positions` from E to A, CR-902 reduced `_resolve_baseline_positions` from D to A, CR-903 reduced `get_instrument_enrichment_bulk` from C to A, CR-904 reduced `_validated_simulation_session` from B to A, CR-905 reduced `_build_delta_section` from B to A, CR-906 removed the final B-ranked method from `core_snapshot_service.py`, CR-908 reduced `_portfolio_observation_rows` from D to A, CR-909 reduced `_effective_beginning_market_value` from C to A, CR-910 reduced `_latest_available_performance_date` from C to A, CR-911 reduced `_resolve_window` from C to A, CR-912 reduced `get_portfolio_timeseries` from C to A, CR-913 reduced `get_position_timeseries` from C to A, CR-914 reduced `create_export_job` from B to A, CR-915 reduced `_reserve_export_job` from B to A, CR-916 reduced `_jsonable` from B to A, CR-917 reduced `get_export_result_ndjson` from B to A, and CR-918 kept extracted analytics export job helpers A-ranked | Keep broad complexity regression-free while reducing remaining B/C hotspots by domain priority |
| Maintainability | No D/E/F source modules; enforced after CR-879 by `make quality-maintainability-gate`; CR-883 removed `openapi_enrichment.py` from the C-ranked hotspot list, CR-884 improved `reference_data_repository.py` from `C (4.26)` to `C (6.94)`, CR-896 improved it again to `C (7.55)`, CR-897 improved it again to `C (8.74)`, CR-898 improved `operations_service.py` from `C (5.44)` to `B (9.91)`, reducing the C-hotspot count from 8 to 7, CR-907 extracted an A-ranked `core_snapshot_calculations.py` module while reducing `core_snapshot_service.py` from 1,208 SLOC / 518 LLOC to 1,093 SLOC / 464 LLOC, CR-918 extracted A-ranked `analytics_export_jobs.py` while reducing `analytics_timeseries_service.py` from 1,844 SLOC to 1,770 SLOC, CR-919 extracted A-ranked `analytics_page_tokens.py` while reducing `analytics_timeseries_service.py` to 1,751 SLOC, CR-920 extracted A-ranked `analytics_windows.py` while reducing `analytics_timeseries_service.py` to 1,707 SLOC, CR-921 extracted A-ranked `analytics_cash_flows.py` while reducing `analytics_timeseries_service.py` to 1,590 SLOC, CR-922 extracted A-ranked `analytics_fx_rates.py` while reducing `analytics_timeseries_service.py` to 1,582 SLOC, CR-923 extracted A-ranked `analytics_pagination.py` while reducing `analytics_timeseries_service.py` to 1,548 SLOC, CR-924 extracted A-ranked `analytics_quality.py` while reducing `analytics_timeseries_service.py` to 1,536 SLOC, CR-925 extracted A-ranked `analytics_position_pages.py` while reducing `analytics_timeseries_service.py` to 1,523 SLOC, CR-926 extracted A-ranked `analytics_portfolio_pages.py` while reducing `analytics_timeseries_service.py` to 1,513 SLOC and improving it to `C (1.52)`, CR-927 extracted A-ranked `analytics_position_responses.py` while reducing `analytics_timeseries_service.py` to 1,424 SLOC and improving it to `C (3.48)`, CR-928 extracted A-ranked `analytics_export_execution.py` while reducing `analytics_timeseries_service.py` to 1,402 SLOC and improving it to `C (5.40)`, CR-929 extracted A-ranked `analytics_export_lifecycle.py` while keeping `analytics_timeseries_service.py` at 1,402 SLOC and improving it to `C (6.86)`, CR-930 extracted A-ranked `analytics_export_results.py` while reducing `analytics_timeseries_service.py` to 1,388 SLOC and improving it to `C (7.80)`, CR-931 removed stale analytics quality wrapper methods while reducing the active service to 1,325 SLOC and improving it to `B (9.21)`, CR-932 extracted A-ranked `core_snapshot_instrument_enrichment.py` while reducing `core_snapshot_service.py` to 1,067 SLOC, CR-933 extracted A-ranked `core_snapshot_baseline_metadata.py` while reducing `core_snapshot_service.py` to 1,018 SLOC and improving it to `C (2.18)`, CR-934 extracted A-ranked `core_snapshot_baseline_positions.py` while reducing `core_snapshot_service.py` to 896 SLOC and improving it to `C (6.12)`, CR-935 extracted A-ranked `core_snapshot_projected_positions.py` while reducing `core_snapshot_service.py` to 789 SLOC and improving it to `B (12.41)`, CR-936 extracted A-ranked `reference_data_query_helpers.py` while reducing `reference_data_repository.py` to 1,163 SLOC and improving it to `B (9.24)`, CR-937 extracted A-ranked `operations_health_queries.py` while reducing `operations_repository.py` from 2,684 SLOC to 2,522 SLOC, CR-938 extracted A-ranked `operations_missing_fx_queries.py` while reducing `operations_repository.py` to 2,456 SLOC, CR-939 extracted A-ranked `operations_lineage_queries.py` while reducing `operations_repository.py` to 2,388 SLOC, CR-940 extracted A-ranked `operations_position_scope_queries.py` while reducing `operations_repository.py` to 2,211 SLOC, CR-941 extracted A-ranked `operations_load_run_queries.py` while reducing `operations_repository.py` to 1,832 SLOC, CR-942 extracted A-ranked `operations_support_job_queries.py` while reducing `operations_repository.py` to 1,723 SLOC, CR-943 extracted A-ranked `operations_analytics_export_queries.py` while reducing `operations_repository.py` to 1,689 SLOC, CR-944 extracted A-ranked `operations_reconciliation_run_queries.py` while reducing `operations_repository.py` to 1,596 SLOC, CR-945 extracted A-ranked `operations_portfolio_control_queries.py` while reducing `operations_repository.py` to 1,538 SLOC and improving it to `C (0.21)`, CR-946 extracted A-ranked `operations_reprocessing_queries.py` while reducing `operations_repository.py` to 1,403 SLOC and improving it to `C (4.42)`, CR-947 extracted A-ranked `operations_reconciliation_finding_queries.py` while reducing `operations_repository.py` to 1,332 SLOC and improving it to `C (6.24)`, CR-948 expanded A-ranked support-job helpers while reducing `operations_repository.py` to 1,247 SLOC and improving it to `B (9.54)`, CR-952 extracted A-ranked instrument eligibility and DPM source-readiness DTO modules while reducing `reference_integration_dto.py` to 2,639 SLOC and improving it to `B (11.49)`, CR-961 extracted an A-ranked instrument eligibility DTO module while improving `reference_data_dto.py` to `B (9.31)`, and CR-965 improved `ingestion_job_service.py` to `B (11.79)`; the active non-generated C-ranked source hotspot list is clear, with generated `query_service/build` copies tracked separately | Keep maintainability regression-free while reducing existing C hotspots by domain priority |
| Dead code | Production-source baseline clean and enforced after CR-876 by `make quality-vulture-source-gate` plus the quality-baseline Vulture source dead-code job; broader `src tests` Vulture report remains noisy with fixture-style test parameters | Keep production-source dead-code regression-free while reducing test-fixture Vulture noise in focused batches |
| Dependency usage | Production-source deptry baseline clean and enforced after CR-878 by `make quality-deptry-source-gate` plus the quality-baseline Deptry source dependency job | Keep source dependency hygiene regression-free while broader dependency audit remains report-only |
| Security | Bandit baseline clean and enforced after CR-875 by `make quality-bandit-gate` plus the quality-baseline Bandit security job | Keep Bandit regression-free while broader dependency-audit/security gates continue to ratchet |
| Architecture boundaries | Existing strict architecture guard plus 2 kept import-linter contracts enforced by `make quality-import-boundary-gate` after CR-867 | Add focused import contracts as additional ownership boundaries stabilize |
| OpenAPI governance | Existing OpenAPI quality and API vocabulary gates promoted into the quality-baseline API governance job after CR-868 | Keep API governance regression-free while spectral remains report-only until a stable generated-spec artifact exists |
| Documentation | New top-level governance docs scaffolded; CR-847 records collection/build-artifact cleanup | Keep docs implementation-backed and current |

## Current PR Evidence Snapshot

Local evidence captured on 2026-06-05 after CR-964:

- `make quality-ruff-gate` => passed
- `make quality-ruff-format-gate` => passed; 1,151 files already formatted
- `make quality-bandit-gate` => passed; Bandit reported 0 issues across `src`
- `make quality-import-boundary-gate` => passed; 2 import-linter contracts kept
- `make quality-vulture-source-gate` => passed
- `make quality-deptry-source-gate` => passed; no dependency issues found
- `make openapi-gate` => passed
- `make api-vocabulary-gate` => passed
- `make typecheck` => passed; 48 source files checked
- `make no-alias-gate` => passed
- `make warning-gate` => passed; 2,914 unit tests, 9 deselected, 0 warnings
- Current measured source hotspots: `reference_data_dto.py` `B (9.31)` and
  `ingestion_job_service.py` `B (11.79)`; active non-generated C-ranked source hotspot list is
  clear.

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
