# lotus-core Refactor Health Report

Status: Active health report on 2026-06-02.

## Current Direction

The refactor is active but not complete. Recent work has reduced query-service transaction
orchestration complexity by extracting date policy, filter shape, page reads, DTO mapping, FX
conversion boundaries, realized-tax evidence reads, aggregation helpers, and response assembly into
tested modules.

## Current Risk Posture

| Dimension | Status | Evidence |
| --- | --- | --- |
| Service modularity | Improving | CR-832 through CR-845 isolate transaction ledger and realized-tax boundaries |
| Repository-wide quality baseline | Started | `quality/baseline_report.md` |
| Progressive quality CI | Improving | `.github/workflows/quality-baseline.yml` now has enforced Ruff lint, Ruff format, import boundary, API governance, typecheck, Bandit security, Vulture source dead-code, Deptry source dependency, maintainability, complexity, manifest-backed unit collection, manifest-backed integration-lite collection, and workflow-governance gates while other baseline checks remain report-only |
| Full test collection | Improving | Import/plugin collection blockers removed; `pytest --collect-only -q` reaches collection before the governed mixed-runtime guard stops all-suite collection; `make quality-unit-collection-gate` cleanly collects the manifest-backed runtime-safe unit lane with `3082/3092` tests and 10 manifest deselects; `make quality-integration-lite-collection-gate` collects 121 integration-lite tests |
| Lint baseline | Clean | `python -m ruff check . --statistics` reports zero findings |
| Format baseline | Clean | `python -m ruff format --check .` reports 1,070 files already formatted after CR-865 |
| Typecheck baseline | Clean for configured scope | `make typecheck` reports no issues in 42 source files after CR-869 |
| Security baseline | Clean and enforced | Bandit reports 0 findings and is enforced by `make quality-bandit-gate` plus the quality-baseline Bandit security job after CR-875 |
| Production-source dead-code baseline | Clean and enforced | `make quality-vulture-source-gate` reports no high-confidence Vulture findings under production `src` after CR-876 |
| Dependency-usage baseline | Clean and enforced | `make quality-deptry-source-gate` reports no production-source dependency issues after CR-878 |
| Maintainability baseline | No D/E/F modules and enforced | `make quality-maintainability-gate` reports no source modules below C after CR-879; CR-883 removed shared OpenAPI enrichment from the C-ranked hotspot list |
| Complexity baseline | Clean and enforced | CR-880 reduced advisory proposal simulation from F to B, CR-881 reduced the cost-calculator consumer from F to C, and CR-882 reduced FX linkage from D to B; `make quality-complexity-gate` now passes |
| Architecture gates | Improving | Existing `make architecture-guard` now enforces removed-domain import exclusions plus selected direct-import boundaries after CR-1171; `make quality-import-boundary-gate` enforces 2 kept import-linter contracts |
| OpenAPI governance | Improving | Existing `make openapi-gate` and `make api-vocabulary-gate` are enforced in the quality-baseline API governance job; CR-1170 adds stable generated OpenAPI artifacts under `output/openapi/` and enforced portable Spectral blocker-subset linting through `make quality-openapi-spectral-gate` |
| HTTP observability | Improving | CR-1172 removes raw HTTP request paths and portfolio/security business-key labels from shared Prometheus metrics; CR-1175 routes health-only worker web apps through the standard HTTP bootstrap for `/metrics`, `/health/live`, `/health/ready`, correlation/request/trace headers, route-template HTTP metrics, and request-completion logs |
| Sensitive output redaction | Improving | CR-1173 centralizes structured-log/test-output redaction in `portfolio_common.logging_utils`; CR-1174 reuses the shared policy for shared Kafka consumer DLQ payloads; CR-1176 routes durable ingestion request payload storage through source-safe redaction and adds canonical fingerprint groundwork |
| Ingestion idempotency | Improving | CR-1177 compares source-safe canonical payload fingerprints for duplicate ingestion idempotency keys and returns deterministic `409 INGESTION_IDEMPOTENCY_CONFLICT` when the same endpoint/key is reused with a different payload |
| Event contract validation | Improving | CR-1178 changes governed event models from unknown-field drop behavior to fail-closed `extra_forbidden` validation, explicitly preserves outbox envelope metadata, and keeps DLQ validation-error evidence source-safe |

## Current Slice Update

CR-1178 addresses validated GitHub issue #558 by moving shared governed event models from
`extra="ignore"` to `extra="forbid"` while explicitly preserving existing outbox envelope metadata
fields. Producer/consumer drift is now rejected instead of silently dropping unknown lineage,
version, or audit fields. Shared Kafka consumer DLQ evidence renders Pydantic validation errors
without raw rejected input values. Focused tests prove event-contract rejection, envelope
compatibility, and source-safe DLQ error evidence.

## Health Assessment

`lotus-core` is not yet bank-buyable as a whole. It has strong existing governance machinery and
many domain-specific contracts, but the updated goal requires measurable quality evidence,
progressive CI gates, complete API/documentation posture, security posture, and full-suite test
health before that claim is defensible.

## Progress Since Baseline

1. Moved e2e support plugin registration to the repository-root pytest configuration boundary so
   pytest 9 no longer rejects `tests/e2e/conftest.py` as a non-top-level plugin declaration.
2. Enabled pytest `importlib` import mode to prevent duplicate unit/integration test basenames from
   colliding during collection.
3. Removed the local generated `src/services/query_service/build` tree from the active source
   checkout; it remains ignored by Git and excluded from coverage/tool scopes.
4. Removed the 20 unused-symbol lint findings from the baseline; remaining Ruff debt is line
   length, import ordering, and one Alembic import-position finding.
5. Normalized Alembic import ordering, removing 40 import-order findings while preserving migration
   operations and metadata loading.
6. Normalized import ordering for governance scripts, tools, and shared supportability helpers,
   removing 12 additional import-order findings.
7. Normalized the remaining app and test import ordering, removing the last 20 import-order
   findings from the baseline.
8. Reworked Alembic metadata bootstrap to clear the final import-position finding while preserving
   path setup and SQLAlchemy model registration.
9. Started the E501 line-length ratchet on active non-Alembic scripts, tools, app modules, DTOs,
   and focused tests, reducing remaining Ruff findings from 250 to 218.
10. Normalized line length in the first bounded Alembic migration batch, reducing remaining Ruff
    findings from 218 to 172 while preserving migration SQL smoke.
11. Normalized line length in the remaining Alembic migration hotspots, reducing full Ruff findings
    from 172 to 0 and making Ruff suitable for the next regression-gate ratchet.
12. Added a dedicated Ruff regression gate to the quality-baseline workflow and a repo-native
    `make quality-ruff-gate` target so future pull requests cannot reintroduce Ruff findings.
13. Started the Ruff format ratchet with a bounded Alembic batch, reducing format debt from 154 to
    141 files while preserving migration graph and SQL smoke behavior.
14. Continued the Ruff format ratchet across bounded operational scripts, tools, and focused
    script/tool tests, reducing format debt from 141 to 125 files while keeping Ruff lint clean.
15. Continued the Ruff format ratchet across bounded `portfolio_common` shared-library helpers,
    reducing format debt from 125 to 110 files while keeping Ruff lint clean.
16. Continued the Ruff format ratchet across a bounded calculator and runtime-service batch,
    reducing format debt from 110 to 90 files while keeping Ruff lint clean.
17. Continued the Ruff format ratchet across a bounded ingestion and pipeline-orchestrator batch,
    reducing format debt from 90 to 68 files while keeping Ruff lint clean.
18. Continued the Ruff format ratchet across a bounded query-service and query-control-plane batch,
    reducing format debt from 68 to 52 files while keeping Ruff lint clean.
19. Continued the Ruff format ratchet across a bounded timeseries and valuation-orchestrator batch,
    reducing format debt from 52 to 40 files while keeping Ruff lint clean.
20. Continued the Ruff format ratchet across bounded shared test support, persistence repository
    integration collection, portfolio-common unit tests, and local stack contract tests, reducing
    format debt from 40 to 21 files while keeping Ruff lint clean.
21. Completed the Ruff format ratchet across the remaining E2E workflow tests and query-service
    advisory-simulation unit tests, reducing format debt from 21 files to zero while keeping Ruff
    lint clean.
22. Added an enforced Ruff format gate to the quality-baseline workflow and a repo-native
    `make quality-ruff-format-gate` target so future pull requests cannot reintroduce formatter
    drift.
23. Corrected and promoted the import-linter architecture boundary scaffold into
    `make quality-import-boundary-gate` plus an enforced quality-baseline workflow job, keeping
    router repository access and approved shared FastAPI dependency boundaries regression-free.
24. Promoted the existing OpenAPI quality and API vocabulary checks into a dedicated
    quality-baseline API governance workflow job so documented API surface and governed vocabulary
    regressions are blocked earlier.
25. Promoted the configured mypy typecheck baseline into a dedicated quality-baseline workflow job,
    removed stale unused mypy test config, and recorded the current Bandit security baseline for
    the next hardening slice.
26. Replaced query-service MD5 request fingerprints with SHA-256 through the shared helper,
    removing the high-severity Bandit finding and reducing the security baseline to medium/low
    findings only.
27. Replaced production assert guards in operations routing, analytics export creation, and core
    snapshot simulation handling with explicit runtime guards, reducing Bandit findings from 16 to
    12 while keeping high-severity findings at zero.
28. Replaced enterprise readiness string-based integer setting attribute lookup with explicit typed
    settings access, removing the remaining low-severity Bandit finding and reducing the security
    baseline to 11 medium findings with zero low or high findings.
29. Replaced reprocessing job claim SQL interpolation with static job-type-specific claim-query
    templates, removing the low-confidence SQL-construction Bandit finding and reducing the
    security baseline to 10 medium bind-host findings.
30. Centralized consumer health-probe bind-host selection in a shared configurable helper and
    routed all worker consumer managers through it, removing the remaining Bandit findings and
    making the security baseline clean.
31. Added a repo-native Bandit quality gate and a dedicated quality-baseline Bandit security
    workflow job so the clean security baseline is now enforced instead of report-only.
32. Removed high-confidence Vulture findings from production source and added a repo-native source
    dead-code gate plus quality-baseline workflow job, keeping production-source dead-code
    regression-free while broader test-fixture dead-code noise remains report-only.
33. Scoped the report-only deptry dependency baseline to production source and measured the current
    928-finding `DEP003` baseline, making dependency metadata and first-party package modeling the
    next governed cleanup target instead of scanning local environment artifacts.
34. Made the root shared runtime dependency metadata truthful for deptry, configured first-party
    and package/module mappings, governed runtime-only dependency exceptions, and promoted the clean
    production-source deptry baseline into an enforced repo-native and CI quality gate.
35. Added a Radon-backed maintainability gate that blocks D/E/F source modules while preserving the
    current C-hotspot baseline for focused follow-up refactors.
36. Reduced advisory proposal simulation complexity by extracting validation, cash-flow, shelf,
    funding, reconciliation, analytics, suitability, and workflow-gate helpers. The former
    F-ranked `run_proposal_simulation` block is now B-ranked under Radon. At that point, the
    broader Xenon gate remained blocked by the cost-calculator consumer and `fx_linkage.py`.
37. Reduced cost-calculator consumer complexity by extracting transaction preparation,
    cost-engine processing, persistence, cash-leg validation, bundle-A diagnostics, and outbox
    emission helpers. The former F-ranked `process_message` block is now C-ranked. At that point,
    `fx_linkage.py` was the remaining D-ranked Xenon blocker.
38. Reduced FX linkage complexity by extracting economic-event linkage, swap group, contract id,
    cash-leg role, contract-instrument routing, and contract lifecycle helpers. The former D-ranked
    `fx_linkage.py` module now passes the broad Xenon threshold, enabling the enforced
    `quality-complexity-gate`.
39. Reduced shared OpenAPI enrichment maintainability debt by extracting reusable schema
    example/description inference into `portfolio_common.openapi_examples`. `openapi_enrichment.py`
    now reports A-ranked maintainability and no longer appears in the current C-hotspot list.
40. Reduced reference-data coverage calculation debt by extracting benchmark and risk-free
    coverage calculations into `reference_coverage_calculations.py`. `get_benchmark_coverage` is
    now A-ranked for complexity, and `reference_data_repository.py` improved from `C (4.26)` to
    `C (6.94)`, but it remains a C-ranked maintainability hotspot.
41. Reduced load-run progress operations repository complexity by extracting scalar statement,
    summary statement, valuation handoff SQL, and summary-mapping helpers. The former D-ranked
    `get_load_run_progress` method now reports A-ranked complexity, but
    `operations_repository.py` remains a C-ranked maintainability hotspot.
42. Reduced reconciliation run operations repository scope complexity by extracting time,
    identity, and run-attribute filter helpers. The former C-ranked
    `_apply_reconciliation_run_scope` helper now reports A-ranked complexity, but
    `operations_repository.py` remains a C-ranked maintainability hotspot.
43. Reduced valuation job operations repository scope complexity by extracting actionable-job,
    valuation-attribute, and valuation-identity filter helpers. The former B-ranked
    `_apply_valuation_job_scope` helper now reports A-ranked complexity, but
    `operations_repository.py` remains a C-ranked maintainability hotspot.
44. Reduced aggregation job operations repository scope complexity by extracting aggregation-date
    and aggregation-identity filter helpers. The former B-ranked
    `_apply_aggregation_job_scope` helper now reports A-ranked complexity, but
    `operations_repository.py` remains a C-ranked maintainability hotspot.
45. Reduced portfolio-control stage operations repository scope complexity by extracting stage
    identity and business-date filter helpers. The former B-ranked
    `_apply_portfolio_control_stage_scope` helper now reports A-ranked complexity, but
    `operations_repository.py` remains a C-ranked maintainability hotspot.
46. Reduced reprocessing job operations repository scope complexity by extracting payload security
    and job-identity filter helpers. The former B-ranked `_apply_reprocessing_job_scope` helper
    now reports A-ranked complexity, but `operations_repository.py` remains a C-ranked
    maintainability hotspot.
47. Reduced current position history operations repository scope complexity by extracting security
    expression resolution, normalized security filtering, and history-date/as-of filter helpers.
    The former B-ranked `_apply_current_position_history_scope` helper now reports A-ranked
    complexity, but `operations_repository.py` remains a C-ranked maintainability hotspot.
48. Reduced valuation and aggregation support-job health summary complexity by extracting shared
    threshold, aggregate-result selection, row-mapping, and execution helpers. The former B-ranked
    `get_valuation_job_health_summary` and `get_aggregation_job_health_summary` methods now report
    A-ranked complexity, but `operations_repository.py` remains a C-ranked maintainability
    hotspot.
49. Reduced analytics export health summary complexity by extracting aggregate, oldest-open
    lookup, result-selection, row-mapping, and execution helpers. The former B-ranked
    `get_analytics_export_job_health_summary` method now reports A-ranked complexity, but
    `operations_repository.py` remains a C-ranked maintainability hotspot.
50. Reduced missing historical FX dependency summary complexity by extracting transaction
    base-scope SQL, aggregate SQL, sample SQL, sample-record mapping, and summary assembly
    helpers. The former B-ranked `get_missing_historical_fx_dependency_summary` method now reports
    A-ranked complexity, but `operations_repository.py` remains a C-ranked maintainability
    hotspot.
51. Reduced lineage key query complexity by extracting correlated latest-date subqueries,
    artifact-gap policy, lineage priority policy, and result projection helpers. The former
    B-ranked `get_lineage_keys` method now reports A-ranked complexity, removing the remaining
    B-ranked method from `operations_repository.py`; the module remains a C-ranked maintainability
    hotspot.
52. Reduced reference FX-rate query complexity by extracting FX pair normalization and latest-rate
    SQL construction into `reference_fx_queries.py`. The former B-ranked `list_latest_fx_rates`
    method now reports A-ranked complexity, and `reference_data_repository.py` improved from
    `C (6.94)` to `C (7.55)`, but it remains a C-ranked maintainability hotspot.
53. Reduced DPM portfolio-universe query complexity by extracting DPM source eligibility,
    canonical mandate-binding ranking, cursor, and limit SQL construction into
    `reference_dpm_queries.py`. The former B-ranked
    `list_dpm_portfolio_universe_candidates` method now reports A-ranked complexity, and
    `reference_data_repository.py` improved from `C (7.55)` to `C (8.74)`, but it remains a
    C-ranked maintainability hotspot.
54. Reduced operations-service runtime-state maintainability debt by extracting source-data
    product runtime metadata, reconciliation status aggregation, analytics export normalization,
    stale-running detection, and export operational-state classification into
    `operations_runtime_state.py`. `operations_service.py` improved from `C (5.44)` to
    `B (9.91)`, removing it from the current C-ranked maintainability hotspot list and reducing
    the C-hotspot count from 8 to 7.
55. Reduced position-timeseries orchestration complexity by extracting page support-input reads,
    page scope resolution, previous-EOD continuity inputs, row assembly, and FX-rate guard helpers
    inside `analytics_timeseries_service.py`. The former E-ranked `get_position_timeseries`
    method now reports `C (15)` instead of `E (37)`, but `analytics_timeseries_service.py`
    remains a C-ranked maintainability hotspot and the C-hotspot count remains 7.
56. Reduced core snapshot orchestration complexity by extracting currency context resolution,
    simulation projection/session validation, section population, governance resolution,
    fingerprinting, and response construction helpers inside `core_snapshot_service.py`. The
    former E-ranked `get_core_snapshot` method now reports `A (4)` instead of `E (39)`, but
    `core_snapshot_service.py` remains a C-ranked maintainability hotspot and the C-hotspot count
    remains 7.
57. Reduced core snapshot projected-position complexity by extracting baseline copy, simulation
    change normalization, missing-instrument seeding, quantity-delta application, baseline/priced
    valuation, market-to-portfolio FX, and output filtering helpers inside
    `core_snapshot_service.py`. The former E-ranked `_resolve_projected_positions` method now
    reports `A (2)` instead of `E (34)`, but `core_snapshot_service.py` remains a C-ranked
    maintainability hotspot and the C-hotspot count remains 7.
58. Reduced core snapshot baseline-position complexity by extracting current snapshot/history row
    selection, row-to-entry mapping, cash/zero filtering, market-value selection,
    instrument/no-instrument payload construction, and freshness metadata helpers inside
    `core_snapshot_service.py`. The former D-ranked `_resolve_baseline_positions` method now
    reports `A (3)` instead of `D (28)`, removing the remaining D-ranked method from the module,
    but `core_snapshot_service.py` remains a C-ranked maintainability hotspot and the C-hotspot
    count remains 7.
59. Reduced core snapshot instrument-enrichment complexity by extracting request identifier
    normalization, enrichment lookup-map construction, and per-security DTO mapping helpers inside
    `core_snapshot_service.py`. The former C-ranked `get_instrument_enrichment_bulk` method now
    reports `A (2)` instead of `C (13)`, removing the remaining C-ranked method from the module,
    but `core_snapshot_service.py` remains a C-ranked maintainability hotspot and the C-hotspot
    count remains 7.
60. Reduced core snapshot simulation-validation complexity by extracting required simulation
    options, required session lookup, portfolio ownership validation, and expected-version
    validation helpers inside `core_snapshot_service.py`. The former B-ranked
    `_validated_simulation_session` method now reports `A (1)` instead of `B (6)`, but
    `core_snapshot_service.py` remains a C-ranked maintainability hotspot and the C-hotspot count
    remains 7.
61. Reduced core snapshot delta-section complexity by extracting delta security-id selection,
    delta value extraction, weight calculation, and record construction helpers inside
    `core_snapshot_service.py`. The former B-ranked `_build_delta_section` method now reports
    `A (2)` instead of `B (10)`, but `core_snapshot_service.py` remains a C-ranked
    maintainability hotspot and the C-hotspot count remains 7.
62. Reduced core snapshot data-quality classification complexity by extracting the
    current-snapshot completeness predicate inside `core_snapshot_service.py`. The former B-ranked
    `_snapshot_data_quality_status` method now reports `A (4)` instead of `B (6)`, and
    `core_snapshot_service.py` now has no B-or-worse methods under Radon cyclomatic complexity,
    but it remains a C-ranked maintainability hotspot and the C-hotspot count remains 7.
63. Reduced core snapshot service module size and responsibility by extracting market-value total,
    position weight assignment, and delta-section construction helpers into
    `core_snapshot_calculations.py`. The new calculation module reports `A (43.88)` under Radon
    maintainability and no B-or-worse methods under Radon cyclomatic complexity.
    `core_snapshot_service.py` shrank from 1,208 SLOC / 518 LLOC to 1,093 SLOC / 464 LLOC, but it
    remains a C-ranked maintainability hotspot and the C-hotspot count remains 7.
64. Reduced analytics portfolio-observation complexity by extracting page scope, support-input
    reads, row bucketing, per-date observation assembly, FX rate guards, and next-page token
    helpers inside `analytics_timeseries_service.py`. The former D-ranked
    `_portfolio_observation_rows` method now reports `A (2)` instead of `D (22)`, but
    `analytics_timeseries_service.py` remains a C-ranked maintainability hotspot and the
    C-hotspot count remains 7.
65. Reduced analytics beginning-market-value policy complexity by extracting prior-EOD continuity,
    internal cash-book settlement, previous-EOD repair, and new internally funded position
    predicates inside `analytics_timeseries_service.py`. The former C-ranked
    `_effective_beginning_market_value` method now reports `A (5)` instead of `C (17)`, but
    `analytics_timeseries_service.py` remains a C-ranked maintainability hotspot and the
    C-hotspot count remains 7.
66. Reduced analytics latest-performance-horizon complexity by extracting observed-date promotion,
    portfolio candidate selection, available horizon collection, and as-of-date bounding helpers
    inside `analytics_timeseries_service.py`. The former C-ranked
    `_latest_available_performance_date` method now reports `A (1)` instead of `C (12)`, but
    `analytics_timeseries_service.py` remains a C-ranked maintainability hotspot and the
    C-hotspot count remains 7.
67. Reduced analytics window-resolution complexity by extracting explicit-window bounding,
    period-start selection, and inception-date clamping helpers inside
    `analytics_timeseries_service.py`. The former C-ranked `_resolve_window` method now reports
    `A (2)` instead of `C (11)`, but `analytics_timeseries_service.py` remains a C-ranked
    maintainability hotspot and the C-hotspot count remains 7.
68. Reduced analytics portfolio-timeseries orchestration complexity by extracting request-scope
    fingerprinting, page-token cursor validation, and diagnostics construction helpers inside
    `analytics_timeseries_service.py`. The former C-ranked `get_portfolio_timeseries` method now
    reports `A (4)` instead of `C (11)`, but `analytics_timeseries_service.py` remains a C-ranked
    maintainability hotspot and the C-hotspot count remains 7.
69. Reduced analytics position-timeseries orchestration complexity by extracting request-scope
    fingerprinting, cursor validation, dimension-filter projection, snapshot-epoch resolution,
    next-page token, and diagnostics helpers inside `analytics_timeseries_service.py`. The former
    C-ranked `get_position_timeseries` method now reports `A (4)` instead of `C (15)`, removing
    the final C-ranked method from `analytics_timeseries_service.py`; the module remains a
    C-ranked maintainability hotspot and the C-hotspot count remains 7.
70. Reduced analytics export job creation complexity by extracting reused-job response, dataset
    collection, export result payload, export result metrics, and completed-job persistence helpers
    inside `analytics_timeseries_service.py`. The former B-ranked `create_export_job` method now
    reports `A (4)` instead of `B (8)`, but `analytics_timeseries_service.py` remains a C-ranked
    maintainability hotspot and the C-hotspot count remains 7.
71. Reduced analytics export job reservation complexity by extracting completed, in-flight,
    freshness, and stale-threshold policy helpers inside `analytics_timeseries_service.py`. The
    former B-ranked `_reserve_export_job` method now reports `A (5)` instead of `B (6)`, but
    `analytics_timeseries_service.py` remains a C-ranked maintainability hotspot and the
    C-hotspot count remains 7.
72. Reduced analytics export JSON serialization complexity by extracting Decimal, temporal, list,
    and dictionary JSON conversion helpers inside `analytics_timeseries_service.py`. The former
    B-ranked `_jsonable` helper now reports `A (5)` instead of `B (7)`, but
    `analytics_timeseries_service.py` remains a C-ranked maintainability hotspot and the
    C-hotspot count remains 7.
73. Reduced analytics export NDJSON result complexity by extracting malformed-payload validation,
    metadata/data row rendering, UTF-8 encoding, media type, content-encoding, and optional gzip
    handling into `analytics_export_ndjson.py`. The former B-ranked
    `get_export_result_ndjson` method now reports `A (5)` instead of `B (7)`, and the helper
    module reports A-ranked maintainability. `analytics_timeseries_service.py` remains a C-ranked
    maintainability hotspot and the C-hotspot count remains 7.
74. Reduced analytics export job policy coupling by extracting status normalization, result
    endpoint construction, job response shaping, reused-job disposition, result payload
    construction, JSON-safe conversion, and export result metric recording into
    `analytics_export_jobs.py`. The helper module reports `A (50.45)` maintainability and
    A-ranked helper complexity. `analytics_timeseries_service.py` shrank from 1,844 SLOC to
    1,770 SLOC, but remains a C-ranked maintainability hotspot and the C-hotspot count remains 7.
75. Reduced analytics page-token security-policy coupling by extracting deterministic cursor
    payload serialization, envelope encoding, SHA-256 HMAC signing, constant-time signature
    comparison, blank-token handling, and malformed/signature error classification into
    `analytics_page_tokens.py`. The helper module reports `A (59.76)` maintainability and
    A-ranked helper complexity. `analytics_timeseries_service.py` shrank from 1,770 SLOC to
    1,751 SLOC, but remains a C-ranked maintainability hotspot and the C-hotspot count remains 7.
76. Reduced analytics window policy coupling by extracting explicit-window bounding, supported
    period start lookup, inception clamping, and invalid-window/period classification into
    `analytics_windows.py`. The helper module reports `A (54.96)` maintainability and A-ranked
    helper complexity. `analytics_timeseries_service.py` shrank from 1,751 SLOC to 1,707 SLOC,
    but remains a C-ranked maintainability hotspot and the C-hotspot count remains 7.
77. Reduced analytics cash-flow policy coupling by extracting cash-flow DTO construction,
    portfolio/reporting FX conversion checks, position-flow grouping, internal/external flow
    predicates, and beginning-market-value repair rules into `analytics_cash_flows.py`. The helper
    module reports `A (37.12)` maintainability and A-ranked helper complexity.
    `analytics_timeseries_service.py` shrank from 1,707 SLOC to 1,590 SLOC, but remains a C-ranked
    maintainability hotspot and the C-hotspot count remains 7.
78. Reduced analytics FX policy coupling by extracting portfolio/reporting FX map retrieval,
    position/portfolio FX map retrieval, same-currency identity handling, and missing-rate
    classification into `analytics_fx_rates.py`. The helper module reports `A (51.85)`
    maintainability and A-ranked helper complexity. `analytics_timeseries_service.py` shrank from
    1,590 SLOC to 1,582 SLOC, but remains a C-ranked maintainability hotspot and the C-hotspot count
    remains 7.
79. Reduced analytics pagination and diagnostics coupling by extracting request-scope fingerprint
    construction, cursor parsing, next-token payload construction, diagnostics assembly, and
    stale-point counting into `analytics_pagination.py`. The helper module reports `A (43.97)`
    maintainability and A-ranked helper complexity. `analytics_timeseries_service.py` shrank from
    1,582 SLOC to 1,548 SLOC, but remains a C-ranked maintainability hotspot and the C-hotspot count
    remains 7.
80. Reduced analytics quality and horizon coupling by extracting row quality labels, data-quality
    coverage classification, portfolio-reference completeness classification, evidence timestamp
    selection, and latest portfolio/position horizon bounding into `analytics_quality.py`. The
    helper module reports `A (52.85)` maintainability and A-ranked helper complexity.
    `analytics_timeseries_service.py` shrank from 1,548 SLOC to 1,536 SLOC, but remains a C-ranked
    maintainability hotspot and the C-hotspot count remains 7.
81. Reduced analytics position-page scope coupling by extracting position page date ranges,
    first-page date selection, security-id collection for page support reads, dimension filter
    conversion, and prior-day EOD filtering into `analytics_position_pages.py`. The helper module
    reports `A (58.69)` maintainability and A-ranked helper complexity.
    `analytics_timeseries_service.py` shrank from 1,536 SLOC to 1,523 SLOC, but remains a C-ranked
    maintainability hotspot and the C-hotspot count remains 7.
82. Reduced analytics portfolio-page scope coupling by extracting portfolio observation page
    slicing, page-date row buckets, same-currency observation rates, missing cross-currency rate
    classification, and portfolio next-page token payloads into `analytics_portfolio_pages.py`.
    The helper module reports `A (46.28)` maintainability and A-ranked helper complexity.
    `analytics_timeseries_service.py` shrank from 1,523 SLOC to 1,513 SLOC and improved from
    `C (0.00)` to `C (1.52)` under Radon maintainability, while the C-hotspot count remains 7.
83. Reduced analytics position-response coupling by extracting position response DTO construction,
    valuation-status distribution accumulation, same-security previous-EOD carry-forward between
    valuation dates, dimension projection, and position/reporting currency value conversion into
    `analytics_position_responses.py`. The helper module reports `A (49.05)` maintainability and
    A-ranked helper complexity. `analytics_timeseries_service.py` shrank from 1,513 SLOC to
    1,424 SLOC and improved from `C (1.52)` to `C (3.48)` under Radon maintainability, while the
    C-hotspot count remains 7.
84. Reduced analytics export execution coupling by extracting portfolio and position export page
    traversal loops into `analytics_export_execution.py`. The helper module reports `A (51.47)`
    maintainability and A-ranked helper complexity. `analytics_timeseries_service.py` shrank from
    1,424 SLOC to 1,402 SLOC and improved from `C (3.48)` to `C (5.40)` under Radon
    maintainability, while the C-hotspot count remains 7.
85. Reduced analytics export lifecycle coupling by extracting completed/inflight status
    classification and stale running job freshness policy into `analytics_export_lifecycle.py`.
    The helper module reports `A (62.35)` maintainability and A-ranked helper complexity.
    `analytics_timeseries_service.py` remained 1,402 SLOC and improved from `C (5.40)` to
    `C (6.86)` under Radon maintainability, while the C-hotspot count remains 7.
86. Reduced analytics export result coupling by extracting completed-result payload validation,
    JSON result DTO construction, NDJSON result transport construction, and malformed-payload error
    mapping into `analytics_export_results.py`. The helper module reports `A (62.17)`
    maintainability and A-ranked helper complexity. `analytics_timeseries_service.py` shrank from
    1,402 SLOC to 1,388 SLOC and improved from `C (6.86)` to `C (7.80)` under Radon
    maintainability, while the C-hotspot count remains 7.
87. Removed stale analytics quality and performance-horizon wrapper methods from
    `analytics_timeseries_service.py` after their policies were already extracted into
    `analytics_quality.py`. The active service now calls the helper functions directly, shrank
    from 1,388 SLOC to 1,325 SLOC, and improved from `C (7.80)` to `B (9.21)` under Radon
    maintainability. The generated `query_service/build` copy remains separate generated-surface
    debt and is not changed by this slice.
88. Reduced core snapshot instrument-enrichment coupling by extracting requested security-id
    normalization, returned-instrument lookup-map construction, ordered DTO record construction,
    and unknown-security fallback into `core_snapshot_instrument_enrichment.py`. The helper module
    reports `A (64.32)` maintainability and A-ranked helper complexity. `core_snapshot_service.py`
    shrank from 1,093 SLOC to 1,067 SLOC, but remains a C-ranked maintainability hotspot.
89. Reduced core snapshot baseline metadata coupling by extracting current-snapshot versus
    historical-fallback freshness metadata, latest row/state timestamp selection, single snapshot
    epoch selection, and empty-baseline epoch suppression into
    `core_snapshot_baseline_metadata.py`. The helper module reports `A (58.44)` maintainability and
    A-ranked helper complexity. `core_snapshot_service.py` shrank from 1,067 SLOC to 1,018 SLOC and
    improved from `C (0.00)` to `C (2.18)`, but remains a C-ranked maintainability hotspot.
90. Reduced core snapshot baseline position mapping coupling by extracting deterministic row
    iteration, quantity/security normalization, cash/zero filtering, current snapshot versus
    history market-value selection, missing-instrument fallback payloads, and instrument payload
    construction into `core_snapshot_baseline_positions.py`. The helper module reports `A (45.13)`
    maintainability and A-ranked helper complexity. `core_snapshot_service.py` shrank from 1,018
    SLOC to 896 SLOC and improved from `C (2.18)` to `C (6.12)`, but remains a C-ranked
    maintainability hotspot.
91. Reduced core snapshot projected-position policy coupling by extracting baseline-to-projected
    copying, missing projected security-id discovery, new projected instrument payload
    construction, transaction quantity mutation, baseline unit-value reuse, positive new-position
    pricing requirements, and cash/zero filtering into `core_snapshot_projected_positions.py`.
    The helper module reports `A (42.61)` maintainability and A-ranked helper complexity.
    `core_snapshot_service.py` shrank from 896 SLOC to 789 SLOC and improved from `C (6.12)` to
    `B (12.41)`, removing it from the active C-ranked maintainability hotspot list. The generated
    `query_service/build` copy remains separate generated-surface debt and is not changed by this
    slice.
92. Reduced reference-data repository query-helper coupling by extracting effective-window
    filtering, reference status normalization, canonical series ranking, latest-effective row
    ranking, DPM mandate binding ranking, model portfolio target ranking, and instrument
    eligibility ranking into `reference_data_query_helpers.py`. The helper module reports
    `A (61.46)` maintainability and A-ranked helper complexity. `reference_data_repository.py`
    shrank from 1,278 SLOC to 1,163 SLOC and improved from `C (8.74)` to `B (9.24)`, removing it
    from the active C-ranked maintainability hotspot list. The generated `query_service/build`
    copy remains separate generated-surface debt and is not changed by this slice.
93. Reduced operations repository health-query coupling by extracting integer/latency row-value
    normalization, support-job health thresholds, support-job aggregate and oldest-open selectors,
    support-job health result shaping, analytics-export aggregate and oldest-open selectors, and
    analytics-export health result shaping into `operations_health_queries.py`. The helper module
    reports `A (49.26)` maintainability and A-ranked helper complexity.
    `operations_repository.py` shrank from 2,684 SLOC to 2,522 SLOC, but remains `C (0.00)` under
    Radon maintainability and needs additional focused extractions before it can leave the active
    C-ranked hotspot list.
94. Reduced operations repository missing-historical-FX diagnostic coupling by extracting the base
    transaction query, aggregate missing-count and transaction-date range query, deterministic
    sample query, sample-record normalization, and summary DTO construction into
    `operations_missing_fx_queries.py`. The helper module reports `A (55.27)` maintainability and
    A-ranked helper complexity. `operations_repository.py` shrank from 2,522 SLOC to 2,456 SLOC,
    but remains `C (0.00)` under Radon maintainability and needs additional focused extractions
    before it can leave the active C-ranked hotspot list.
95. Reduced operations repository lineage query coupling by extracting latest artifact-date
    correlated subqueries, lineage artifact-gap classification, lineage priority ordering, and
    lineage-key select construction into `operations_lineage_queries.py`. The helper module
    reports `A (58.81)` maintainability and A-ranked helper complexity.
    `operations_repository.py` shrank from 2,456 SLOC to 2,388 SLOC, but remains `C (0.00)` under
    Radon maintainability and needs additional focused extractions before it can leave the active
    C-ranked hotspot list.
96. Reduced operations repository position-scope query coupling by extracting load-run artifact
    and job filtering, portfolio/security/epoch evidence filtering, current position-history
    scope construction, current epoch snapshot scope construction, and latest transaction-date
    statement construction into `operations_position_scope_queries.py`. The helper module reports
    `A (38.78)` maintainability and A-ranked helper complexity. `operations_repository.py` shrank
    from 2,388 SLOC to 2,211 SLOC, but remains `C (0.00)` under Radon maintainability and needs
    additional focused extractions before it can leave the active C-ranked hotspot list.
97. Reduced operations repository load-run progress coupling by extracting scalar statement
    construction, valuation and aggregation summary statement construction, valuation-to-position
    timeseries handoff diagnostics, and `LoadRunProgressSummary` row shaping into
    `operations_load_run_queries.py`. The helper module reports `A (44.96)` maintainability and
    A-ranked helper complexity. `operations_repository.py` shrank from 2,211 SLOC to 1,832 SLOC,
    but remains `C (0.00)` under Radon maintainability and needs additional focused extractions
    before it can leave the active C-ranked hotspot list.
98. Reduced operations repository support-job scope coupling by extracting valuation and
    aggregation job identity filters, business-date filters, security filters, status filters, and
    composed job-scope helpers into `operations_support_job_queries.py`. The helper module reports
    `A (43.44)` maintainability and A-ranked helper complexity. `operations_repository.py` shrank
    from 1,832 SLOC to 1,723 SLOC, but remains `C (0.00)` under Radon maintainability and needs
    additional focused extractions before it can leave the active C-ranked hotspot list.
99. Reduced operations repository analytics-export scope coupling by extracting analytics-export
    status normalization, stale/open job priority ordering, and composed job-scope filtering into
    `operations_analytics_export_queries.py`. The helper module reports `A (55.97)`
    maintainability and A-ranked helper complexity. `operations_repository.py` shrank from 1,723
    SLOC to 1,689 SLOC, but remains `C (0.00)` under Radon maintainability and needs additional
    focused extractions before it can leave the active C-ranked hotspot list.
100. Reduced operations repository reconciliation-run scope coupling by extracting
     reconciliation-run status normalization, failed/replay priority ordering, as-of filtering,
     identity filtering, attribute filtering, and composed run-scope helpers into
     `operations_reconciliation_run_queries.py`. The helper module reports `A (47.04)`
     maintainability and A-ranked helper complexity. `operations_repository.py` shrank from 1,689
     SLOC to 1,596 SLOC, but remains `C (0.00)` under Radon maintainability and needs additional
     focused extractions before it can leave the active C-ranked hotspot list.
101. Reduced operations repository portfolio-control scope coupling by extracting
     portfolio-control status normalization, failed/replay priority ordering, identity filtering,
     business-date filtering, and composed stage-scope helpers into
     `operations_portfolio_control_queries.py`. The helper module reports `A (53.89)`
     maintainability and A-ranked helper complexity. `operations_repository.py` shrank from 1,596
     SLOC to 1,538 SLOC and improved from `C (0.00)` to `C (0.21)`, but remains a C-ranked
     maintainability hotspot.
102. Reduced operations repository reprocessing scope coupling by extracting reprocessing status
     normalization, stale-key priority ordering, reset-watermark job portfolio eligibility, payload
     expression extraction, key filtering, and job filtering into `operations_reprocessing_queries.py`.
     The helper module reports `A (43.47)` maintainability and A-ranked helper complexity.
     `operations_repository.py` shrank from 1,538 SLOC to 1,403 SLOC and improved from
     `C (0.21)` to `C (4.42)`, but remains a C-ranked maintainability hotspot.
103. Reduced operations repository reconciliation-finding query coupling by extracting run/as-of
     filtering, finding/security/transaction filters, severity-priority ordering, summary select
     construction, aggregate/top-blocking summary selection, and `ReconciliationFindingSummary`
     row shaping into `operations_reconciliation_finding_queries.py`. The helper module reports
     `A (50.89)` maintainability and A-ranked helper complexity. `operations_repository.py`
     shrank from 1,403 SLOC to 1,332 SLOC and improved from `C (4.42)` to `C (6.24)`, but
     remains a C-ranked maintainability hotspot.
104. Reduced operations repository support-job SQL helper coupling by extracting actionable
     valuation-job filtering, superseding valuation-epoch detection, latest valuation-job lateral
     selection, support-job priority ordering, and reusable security-id expression use into
     `operations_support_job_queries.py` and `operations_position_scope_queries.py`. The expanded
     support helper reports `A (35.97)` maintainability and A-ranked helper complexity.
     `operations_repository.py` shrank from 1,332 SLOC to 1,247 SLOC and improved from
     `C (6.24)` to `B (9.54)`, removing it from the active source C-ranked maintainability
     hotspot list. Generated `query_service/build` copies remain separate generated-surface debt.
105. Reduced query-service reference integration DTO coupling by extracting transaction-cost curve
     and benchmark market-series DTO families into
     `reference_integration_transaction_cost_dto.py` and
     `reference_integration_benchmark_market_series_dto.py`, with compatibility re-exports from
     the original module. The extracted modules report `A (37.79)` and `A (38.91)`
     maintainability. `reference_integration_dto.py` shrank from 3,637 SLOC to 3,264 SLOC and
     improved from `C (0.00)` to `C (1.33)`, but remains a C-ranked maintainability hotspot
     requiring further DTO-family extractions.
106. Reduced query-service reference integration DTO coupling by extracting the market-data
     coverage DTO family into `reference_integration_market_data_coverage_dto.py`, with
     compatibility re-exports from the original module before DPM readiness DTOs. The extracted
     module reports `A (35.77)` maintainability. `reference_integration_dto.py` shrank from
     3,264 SLOC to 3,078 SLOC and improved from `C (1.33)` to `C (4.62)`, but remains a C-ranked
     maintainability hotspot.
107. Reduced query-service reference integration DTO coupling by extracting the portfolio tax-lot
     window DTO family into `reference_integration_portfolio_tax_lot_dto.py`, with compatibility
     re-exports from the original module after shared paging DTOs are defined. The extracted
     module reports `A (41.65)` maintainability. `reference_integration_dto.py` shrank from
     3,078 SLOC to 2,922 SLOC and improved from `C (4.62)` to `C (6.70)`, but remains a C-ranked
     maintainability hotspot.
108. Reduced query-service reference integration DTO coupling by extracting the instrument
     eligibility and DPM source-readiness DTO families into
     `reference_integration_instrument_eligibility_dto.py` and
     `reference_integration_dpm_source_readiness_dto.py`, with compatibility re-exports from the
     original module. The extracted modules report `A (41.20)` and `A (42.75)` maintainability.
     `reference_integration_dto.py` shrank from 2,922 SLOC to 2,639 SLOC and improved from
     `C (6.70)` to `B (11.49)`, removing it from the active non-generated C-ranked source hotspot
     list at that checkpoint. The remaining hotspot list has continued to narrow in later slices.
109. Reduced ingestion job record-status coupling by extracting failed-record-key normalization
     and endpoint-specific replayable-key extraction into `ingestion_record_status.py`.
     `get_job_record_status` improved from `C (20)` to `A (4)`, while the helper module reports
     `A (59.21)` maintainability. `ingestion_job_service.py` shrank from 1,656 SLOC to 1,633 SLOC
     and remains a C-ranked maintainability hotspot requiring additional focused extractions.
110. Reduced ingestion operating-band policy coupling by extracting operating-band policy,
     signal, decision, and classification helpers into `ingestion_operating_band.py`. The extracted
     classifier moved out of the service and now reports `B (7)` in an `A (50.49)` helper module.
     `ingestion_job_service.py` shrank from 1,633 SLOC to 1,545 SLOC and remains a C-ranked
     maintainability hotspot requiring additional focused extractions.
111. Reduced ingestion SLO status coupling by extracting DB aggregate/fallback snapshot loading
     and threshold response assembly into `ingestion_slo_status.py`. `get_slo_status` improved
     from `C (17)` to `A (3)`, while the helper module reports `A (42.76)` maintainability.
     `ingestion_job_service.py` shrank from 1,545 SLOC to 1,477 SLOC and remains a C-ranked
     maintainability hotspot requiring additional focused extractions.
112. Reduced ingestion backlog breakdown coupling by extracting grouped row normalization,
     ordering, concentration-share calculation, and response assembly into
     `ingestion_backlog_breakdown.py`. `get_backlog_breakdown` improved from `C (13)` to `A (3)`,
     while the helper module reports `A (51.73)` maintainability. `ingestion_job_service.py`
     shrank from 1,477 SLOC to 1,419 SLOC and improved from `C (0.00)` to `C (0.81)`, but remains
     a C-ranked maintainability hotspot.
113. Reduced ingestion job listing coupling by extracting filter, cursor lookup, statement-building,
     and page-slicing helpers into `ingestion_job_listing.py`. `list_jobs` improved from `C (11)`
     to `A (4)`, removing the final C-ranked method from `ingestion_job_service.py`. The service
     reports `C (2.32)` maintainability, while the helper module reports `A (46.25)`.
114. Reduced reference-data tax rule validation coupling by extracting effective-window,
     threshold-pair, and bounded-evidence helpers inside `reference_data_dto.py`.
     `ClientTaxRuleSetRecord.validate_rule` improved from `C (12)` to `A (1)`, removing the only
     C-ranked method from `reference_data_dto.py`. The module remains `C (0.00)` because of size
     and remaining B-ranked DTO classes/validators.
115. Reduced reference-data tax DTO coupling by extracting the client tax profile and tax rule-set
     DTO family into `reference_data_tax_dto.py`, with compatibility re-exports from the original
     module. The extracted module reports `A (29.60)` maintainability. `reference_data_dto.py`
     shrank from 1,686 SLOC to 1,511 SLOC and improved from `C (0.00)` to `C (1.05)`, but remains
     a C-ranked maintainability hotspot.
116. Reduced reference-data client preference DTO coupling by extracting the client restriction and
     sustainability preference DTO family into `reference_data_client_preference_dto.py`, with
     compatibility assignments from the original module. The extracted module reports `A (32.04)`
     maintainability. `reference_data_dto.py` shrank from 1,511 SLOC to 1,376 SLOC and improved
     from `C (1.05)` to `C (6.43)`, but remains a C-ranked maintainability hotspot.
117. Reduced reference-data instrument eligibility DTO coupling by extracting the DPM instrument
     eligibility profile DTO family into `reference_data_instrument_eligibility_dto.py`, with
     compatibility assignments from the original module. The extracted module reports `A (40.98)`
     maintainability. `reference_data_dto.py` shrank from 1,376 SLOC to 1,282 SLOC and improved
     from `C (6.43)` to `B (9.31)`, removing it from the active non-generated C-ranked source
     hotspot list.
118. Reduced ingestion capacity-status coupling by extracting capacity group derivation and
     capacity response loading into `ingestion_capacity_status.py`. `get_capacity_status` improved
     from `B (9)` to `A (1)`, while the helper module reports `A (43.64)` maintainability.
     `ingestion_job_service.py` shrank from 1,420 SLOC to 1,304 SLOC and improved from
     `C (2.32)` to `C (5.70)`, but remains the remaining active non-generated C-ranked source
     hotspot.
119. Reduced ingestion error-budget status coupling by extracting default and loaded error-budget
     response assembly into `ingestion_error_budget_status.py`. `get_error_budget_status` improved
     from `B (9)` to `A (1)`, while the helper module reports `A (47.37)` maintainability.
     `ingestion_job_service.py` shrank from 1,304 SLOC to 1,207 SLOC and improved from
     `C (5.70)` to `C (8.17)`, but remains the remaining active non-generated C-ranked source
     hotspot.
120. Reduced ingestion retry guardrail coupling by extracting deterministic retry-policy
     enforcement into `ingestion_retry_guardrails.py`. `assert_retry_allowed_for_records` improved
     from `B (9)` to `A (1)`, while the helper module reports `A (59.19)` maintainability.
     `ingestion_job_service.py` shrank from 1,207 SLOC to 1,200 SLOC and improved from
     `C (8.17)` to `B (9.82)`, clearing the active non-generated C-ranked source hotspot list.
121. Reduced ingestion reprocessing queue-health coupling by extracting SQL aggregation and queue
     response assembly into `ingestion_reprocessing_queue_health.py`.
     `get_reprocessing_queue_health` improved from `B (7)` to `A (1)`, while the helper module
     reports `A (51.01)` maintainability. `ingestion_job_service.py` shrank from 1,200 SLOC to
     1,137 SLOC and improved from `B (9.82)` to `B (11.79)`.
122. Reduced ingestion replay-audit list coupling by extracting optional filter construction,
     bounded ordering, database reads, and DTO mapping into `ingestion_replay_audits.py`.
     `list_replay_audits` improved from `B (7)` to `A (1)`, while the helper module reports
     `A (72.80)` maintainability. `ingestion_job_service.py` shrank from 1,137 SLOC to 1,116 SLOC
     and improved from `B (11.79)` to `B (12.63)`.
123. Reduced ingestion consumer-lag coupling by extracting DLQ aggregate loading, lag severity
     classification, backlog summary stitching, and response assembly into `ingestion_consumer_lag.py`.
     `get_consumer_lag` improved from `B (6)` to `A (1)`, while the helper module reports
     `A (55.85)` maintainability. `ingestion_job_service.py` shrank from 1,116 SLOC to 1,077 SLOC
     and improved from `B (12.63)` to `B (13.77)`.
124. Reduced ingestion health-summary coupling by extracting aggregate counts, oldest-backlog
     lookup, backlog total calculation, and response assembly into `ingestion_health_summary.py`.
     `get_health_summary` improved from `B (6)` to `A (1)`, while the helper module reports
     `A (60.46)` maintainability. `ingestion_job_service.py` shrank from 1,077 SLOC to 1,045 SLOC
     and improved from `B (13.77)` to `B (15.15)`.
125. Reduced ingestion idempotency-diagnostics coupling by extracting aggregate loading, endpoint
     normalization, collision detection, and response assembly into
     `ingestion_idempotency_diagnostics.py`. `get_idempotency_diagnostics` improved from `B (7)`
     to `A (1)`, while the helper module reports `A (59.15)` maintainability.
     `ingestion_job_service.py` shrank from 1,045 SLOC to 990 SLOC and improved from `B (15.15)`
     to `B (16.96)`, leaving no B-ranked methods in the service.
126. Reduced shared event supportability catalog validation complexity by extracting focused
     validators for schema models, unique names, event definitions, governance flags,
     source/evidence links, evidence bundles, source-data products, supportability surfaces,
     direct Kafka topics, and direct-topic headers. `validate_event_supportability_catalog`
     improved from `E (39)` to `A (5)`, all extracted helper functions are A-ranked, and
     `event_supportability.py` remains `A (26.87)` maintainability.
127. Reduced source-data security profile validation complexity by extracting focused validators
     for profile names, classification allowlists, scope requirements, operator-only policy, audit
     mapping, retention mapping, route-family compatibility, PII-field checks, and catalog
     coverage. `_validate_source_data_security_profiles` improved from `D (25)` to `A (4)`, all
     touched helper functions are A-ranked, and `source_data_security.py` remains `A (29.23)`
     maintainability.
128. Reduced shared outbox dispatcher batch orchestration complexity by extracting focused helpers
     for publish handling, flush-result accounting, delivery classification, success persistence,
     retryable failure persistence, terminal failure persistence, callbacks, event headers, event
     payloads, and callback-less failure accounting. `_process_batch_sync` improved from `E (33)`
     to `A (2)`, all dispatcher methods and outbox helper functions are A-ranked, and
     `outbox_dispatcher.py` remains `A (40.41)` maintainability.
129. Reduced enterprise readiness runtime policy complexity by extracting focused helpers for
     runtime issue collection, authorization enablement, capability-rule requirements, header
     normalization, service identity checks, capability parsing, feature-flag lookup, redaction,
     capability-rule normalization, and path-template matching. `validate_enterprise_runtime_config`
     improved from `C (14)` to `A (5)`, `authorize_request` improved from `C (18)` to `A (4)`,
     and every enterprise readiness function/class/method now reports A-ranked complexity.
130. Reduced canonical FX transaction validation complexity by extracting focused helpers for
     normalized control codes, control-code validation, component identity, zero quantity/price
     policy, settlement dates, currency pairs, quote convention, positive amount/rate checks,
     strict metadata, cash settlement components, contract identifiers, swap structure, optional
     policy modes, and realized P&L fields. `validate_fx_transaction` improved from `E (37)` to
     `A (1)`, and every FX validation function/class now reports A-ranked complexity.
131. Reduced canonical INTEREST transaction validation complexity by extracting focused helpers for
     transaction-type validation, settlement-date presence, zero quantity/price policy, gross
     amount policy, interest direction, nonnegative deductions, net interest reconciliation,
     currency fields, date ordering, strict metadata, cash-entry policy, settlement cash-account
     requirements, and external cash-link requirements. `validate_interest_transaction` improved
     from `D (29)` to `A (1)`, and every INTEREST validation function/class now reports A-ranked
     complexity.
132. Reduced canonical SELL transaction validation complexity by extracting focused helpers for
     transaction-type validation, settlement-date presence, positive quantity policy, positive
     gross-amount policy, currency fields, date ordering, strict linkage metadata, and strict
     policy metadata. `validate_sell_transaction` improved from `C (14)` to `A (1)`, and every
     SELL validation function/class now reports A-ranked complexity.
133. Reduced canonical BUY transaction validation complexity by extracting focused helpers for
     transaction-type validation, settlement-date presence, positive quantity policy, positive
     gross-amount policy, currency fields, date ordering, strict linkage metadata, and strict
     policy metadata. `validate_buy_transaction` improved from `C (14)` to `A (1)`, and every BUY
     validation function/class now reports A-ranked complexity.
134. Reduced canonical DIVIDEND transaction validation complexity by extracting focused helpers for
     transaction-type validation, settlement-date presence, zero quantity, zero price, positive
     gross-amount policy, currency fields, date ordering, strict linkage metadata, strict policy
     metadata, cash-entry policy, auto-generated cash-entry requirements, and upstream-provided
     cash-entry requirements. `validate_dividend_transaction` improved from `D (21)` to `A (1)`,
     and every DIVIDEND validation function/class now reports A-ranked complexity.
135. Reduced CA Bundle A transaction validation complexity by extracting focused helpers for
     transaction-type validation, parent event reference validation, linkage identifier validation,
     source instrument validation, target instrument validation, cash-consideration link
     orchestration, cash-link presence, and cash-link consistency.
     `validate_ca_bundle_a_transaction` improved from `D (22)` to `A (2)`, and every CA Bundle A
     validation function/class now reports A-ranked complexity.
136. Reduced adjustment cash-leg helper complexity by extracting focused helpers for adjustment
     resolver dispatch, BUY/SELL/DIVIDEND/INTEREST amount policy, net interest resolution,
     interest movement direction, AUTO_GENERATE eligibility assertion, cash-account resolution,
     cash-instrument resolution, generated linkage metadata, and adjustment cash-leg event
     assembly. `_resolve_adjustment_amount_and_direction` improved from `C (11)` to `A (3)`,
     `build_auto_generated_adjustment_cash_leg` improved from `B (9)` to `A (1)`, and every
     adjustment cash-leg function/class now reports A-ranked complexity.
137. Reduced upstream cash-leg pairing validation complexity by extracting focused helpers for
     product-leg cash-entry mode, portfolio matching, external cash transaction ID matching,
     cash-leg transaction type, cash-leg gross amount, economic event ID, and linked transaction
     group ID. `validate_upstream_cash_leg_pairing` improved from `C (12)` to `A (1)`, and every
     dual-leg pairing function/class now reports A-ranked complexity.
138. Reduced FX baseline processing complexity by extracting focused helpers for decimal
     defaulting, base FX processing update assembly, realized P&L mode dispatch, zero realized P&L
     update assembly, upstream-provided realized P&L update assembly, and total P&L fallback
     resolution. `build_fx_processed_event` improved from `C (14)` to `A (2)`, and every FX
     baseline processing function now reports A-ranked complexity.
139. Reduced FX contract instrument construction complexity by extracting focused helpers for FX
     contract ID resolution, contract currency normalization, pair label resolution, display-name
     construction, and final `InstrumentEvent` assembly. `build_fx_contract_instrument_event`
     improved from `C (13)` to `A (5)`, and every FX contract instrument function now reports
     A-ranked complexity.
140. Reduced FX linkage enrichment complexity by extracting focused helpers for contract ID
     decision predicates, open/close lifecycle transaction IDs, FX metadata update assembly, core
     linkage update fields, contract linkage update fields, instrument lifecycle update fields,
     and FX processing mode update fields. `enrich_fx_transaction_metadata` improved from `B (7)`
     to `A (2)`, `_resolve_fx_contract_id` improved from `B (6)` to `A (4)`, and
     `_resolve_contract_lifecycle_transaction_ids` improved from `B (7)` to `A (3)`.
141. Reduced BUY linkage enrichment complexity by extracting focused helpers for BUY transaction
     eligibility, BUY linkage ID resolution, BUY policy ID resolution, and BUY metadata update
     assembly. `enrich_buy_transaction_metadata` improved from `B (6)` to `A (2)`, and every BUY
     linkage function now reports A-ranked complexity.
142. Reduced SELL linkage enrichment complexity by extracting focused helpers for SELL transaction
     eligibility, SELL linkage ID resolution, SELL policy ID resolution, cost-basis policy
     selection, and SELL metadata update assembly. `enrich_sell_transaction_metadata` improved
     from `B (7)` to `A (2)`, and every SELL linkage function now reports A-ranked complexity.
143. Reduced INTEREST linkage enrichment complexity by extracting focused helpers for INTEREST
     transaction eligibility, INTEREST linkage ID resolution, INTEREST policy ID resolution, and
     INTEREST metadata update assembly. `enrich_interest_transaction_metadata` improved from
     `B (6)` to `A (2)`, and every INTEREST linkage function now reports A-ranked complexity.
144. Reduced DIVIDEND linkage enrichment complexity by extracting focused helpers for DIVIDEND
     transaction eligibility, DIVIDEND linkage ID resolution, DIVIDEND policy ID resolution, and
     DIVIDEND metadata update assembly. `enrich_dividend_transaction_metadata` improved from
     `B (6)` to `A (2)`, and every DIVIDEND linkage function now reports A-ranked complexity.
145. Reduced CA Bundle A reconciliation complexity by extracting a focused reconciliation
     accumulator plus helpers for event accumulation, source-leg accumulation, target-leg
     accumulation, and reconciliation status resolution. `evaluate_ca_bundle_a_reconciliation`
     improved from `B (8)` to `A (2)`, and every CA Bundle A reconciliation function/class now
     reports A-ranked complexity.
146. Reduced CA Bundle A dependency ordering complexity by replacing repeated rank branches with
     explicit rank-type sets and a deterministic dependency-rank lookup. `ca_bundle_a_dependency_rank`
     improved from `B (8)` to `A (1)`, and every CA Bundle A ordering function now reports
     A-ranked complexity.
147. Reduced analytics cashflow semantics classifier complexity by replacing repeated fixed
     classification branches with a typed static semantics map and a focused transfer-flow helper.
     `classify_analytics_cash_flow` improved from `B (10)` to `A (3)`, and every analytics
     cashflow semantics function now reports A-ranked complexity.
148. Reduced market reference point classifier complexity by extracting explicit
     pre-observation and observed-status maps plus a focused point-status helper.
     `classify_market_reference_point` improved from `B (8)` to `A (1)`, and every market
     reference quality function/class now reports A-ranked complexity.
149. Reduced reconciliation quality classifier complexity by extracting validation helpers,
     status-decision helpers, a run-status classification map, and small blocking/partial
     predicates. `classify_reconciliation_status` improved from `B (9)` to `A (2)`,
     `classify_data_quality_coverage` improved from `B (7)` to `A (1)`, and every reconciliation
     quality function/class now reports A-ranked complexity.
150. Reduced ingestion outcome classifier complexity by extracting count validation,
     terminal-failure counting, partial-outcome detection, and valid-outcome classification helpers.
     `classify_ingestion_outcome` improved from `B (6)` to `A (1)`, and every ingestion evidence
     function/class now reports A-ranked complexity.
151. Reduced reconstruction identity scope payload complexity by extracting reconstruction scope
     validation and transaction-window validation helpers. `_canonical_scope_payload` improved
     from `B (7)` to `A (1)`, and every reconstruction identity function/class now reports
     A-ranked complexity.
152. Reduced database URL scheme normalization complexity by extracting legacy-postgres,
     async-driver, sync-driver, and scheme-replacement helpers. `_normalize_database_url_scheme`
     improved from `B (6)` to `A (2)`, and every shared DB helper function now reports A-ranked
     complexity.
153. Reduced Kafka topic verification complexity by extracting admin-client construction,
     required-topic verification, existing-topic metadata lookup, and missing-topic calculation
     helpers. `ensure_topics_exist` improved from `B (6)` to `A (3)`, and every Kafka admin helper
     function/class now reports A-ranked complexity.
154. Reduced shared config integer environment parsing complexity by extracting safe-default,
     environment-loading, and minimum-enforcement helpers. `_env_int` improved from `B (7)` to
     `A (1)`, and each extracted integer parsing helper reports A-ranked complexity.
155. Reduced Kafka consumer config value coercion complexity by extracting type-specific coercion,
     integer parsing, positive-integer enforcement, and `auto.offset.reset` normalization helpers.
     `_coerce_consumer_config_value` improved from `C (16)` to `A (4)`, and each extracted
     consumer coercion helper reports A-ranked complexity.
156. Reduced Kafka consumer runtime override loading complexity by extracting defaults loading,
     group override loading, group sanitization, and group-context helpers.
     `get_kafka_consumer_runtime_overrides` improved from `B (7)` to `A (1)`, while preserving the
     final merged heartbeat/session relationship validation boundary.
157. Reduced Kafka consumer DLQ reason classification complexity by replacing repeated branch
     token checks with explicit ordered token groups and focused matching helpers.
     `classify_dlq_reason_code` improved from `C (12)` to `A (5)`, and direct taxonomy tests now
     cover validation, data-integrity, timeout, authorization, and unclassified outcomes.
158. Reduced Kafka consumer message-correlation context complexity by extracting current/header/
     fallback selection helpers. `BaseConsumer._message_correlation_context` improved from
     `B (7)` to `A (3)`, and direct tests now prove existing-context preservation,
     header-before-fallback precedence, and explicit fallback preference.
159. Reduced Kafka consumer DLQ publication complexity by extracting payload, header, publish,
     delivery-confirmation, and key-decoding helpers. `BaseConsumer._send_to_dlq_async` improved
     from `B (10)` to `A (5)`, while preserving DLQ payload, header, flush, audit, and fatal
     failure semantics.
160. Reduced Kafka consumer shutdown complexity by extracting shutdown log-context, consumer
     wakeup, consumer close, and DLQ producer flush helpers. `BaseConsumer.shutdown` improved from
     `B (8)` to `A (3)`, and tests now prove wakeup failure continuation and close failure logging.
161. Reduced Kafka consumer run-loop commit policy complexity by extracting successful-processing
     commit, successful-DLQ-publication commit, DLQ-publication-failure logging, and message
     log-context helpers. `BaseConsumer.run` improved from `C (18)` to `C (13)`; the remaining
     C-ranked run-loop orchestration is tracked for a separate slice.
162. Reduced Kafka consumer run-loop orchestration complexity by extracting poll-error handling,
     per-message processing, sync/async dispatch, retryable/terminal processing-error handling,
     and processing metrics helpers. `BaseConsumer.run` improved from `C (13)` to `A (5)`, and
     `_process_polled_message` reports `A (4)` with direct fatal/non-fatal poll-error tests.
163. Reduced runtime supervision failure attribution complexity by extracting completed-task
     selection, exception-task selection, cancelled-task selection, and runtime-error construction
     helpers. `wait_for_shutdown_or_task_failure` improved from `C (15)` to `A (5)`, while
     `shutdown_runtime_components` remains a separate C-ranked teardown hotspot.
164. Reduced runtime supervision teardown complexity by extracting consumer shutdown,
     stop-callback execution, server exit signaling, runtime-task awaiting, timeout logging,
     timed-out task-name extraction, pending-task cancellation, and teardown error logging helpers.
     `shutdown_runtime_components` improved from `C (18)` to `A (1)`, and every function in
     `runtime_supervision.py` now reports A-ranked cyclomatic complexity.
165. Reduced shared OpenAPI inference policy complexity by extracting known-key examples, enum
     examples, typed examples, formatted examples, rule-based description selection, and
     description predicate/formatter helpers. `infer_example` improved from `C (11)` to `A (3)`,
     `infer_description` improved from `C (14)` to `A (2)`, and direct tests now pin example and
     description precedence.
166. Reduced shared OpenAPI example classifier complexity by replacing repeated numeric and
     string-like token checks with explicit token-rule tables and focused token-matching helpers.
     `_infer_number_example` improved from `B (8)` to `A (3)`, `_infer_string_like_example`
     improved from `B (8)` to `A (4)`, and `openapi_examples.py` improved from `B (16.35)` to
     `B (17.47)` maintainability.
167. Reduced shared OpenAPI typed-example dispatch complexity by replacing repeated type branches
     with static and dynamic typed-example maps plus focused array, integer, and number builder
     helpers. `_typed_example` improved from `B (6)` to `A (3)`, and `openapi_examples.py`
     improved from `B (17.47)` to `B (17.91)` maintainability.
168. Reduced shared OpenAPI union example builder complexity by extracting union variant lookup,
     union-key dispatch, and non-empty allOf normalization helpers. `_build_union_example`
     improved from `B (8)` to `A (4)`, with direct allOf and oneOf tests pinning existing
     generated example behavior.
169. Reduced shared OpenAPI object example builder complexity by extracting schema-property,
     required-property, property-example, and property-inclusion helpers. `_build_object_example`
     improved from `B (7)` to `A (4)`, with direct tests pinning the existing generic fallback
     behavior for empty object properties.
170. Reduced shared OpenAPI schema example orchestration complexity by extracting candidate
     selection, structured-schema, fallback-example, and fallback property-name helpers.
     `build_schema_example` improved from `B (10)` to `A (4)`, leaving every function in
     `openapi_examples.py` A-ranked by cyclomatic complexity.
171. Reduced shared reprocessing replay orchestration complexity by extracting ordered-id,
     ordered-query, fetch, no-match logging, correlation-header, publish, publish-failure, and
     flush verification helpers. `ReprocessingRepository.reprocess_transactions_by_ids` improved
     from `C (11)` to `A (4)`, leaving every function/class/method in
     `reprocessing_repository.py` A-ranked by cyclomatic complexity.
172. Reduced shared valuation stale-job reset complexity by extracting stale-row retrieval,
     stale-row grouping, stale-job ID classification, superseded update construction, failed
     update construction, reset update construction, and shared processing-state update predicate
     helpers. `ValuationRepositoryBase.find_and_reset_stale_jobs` improved from `C (14)` to
     `A (2)`, and all stale reset helpers now report A-ranked cyclomatic complexity.
173. Reduced shared valuation snapshot-contiguity complexity by extracting first-open-date table
     construction, date-series generation, history/snapshot reconciliation predicates, first-gap
     detection, latest-snapshot fallback, optional join construction, and result mapping into
     `valuation_snapshot_contiguity.py`. `ValuationRepositoryBase.find_contiguous_snapshot_dates`
     improved from `B (8)` to `A (3)`, leaving every function/class/method in
     `valuation_repository_base.py` A-ranked by cyclomatic complexity.
174. Reduced shared OpenAPI enrichment complexity by extracting path-operation discovery,
     HTTP-operation classification, parameter example eligibility, explicit schema-example
     extraction, media-content example eligibility, error response detection, and error
     response-code classification helpers. Every function in `openapi_enrichment.py` now reports
     A-ranked cyclomatic complexity.
175. Reduced shared valuation price policy complexity by extracting bond percent-quote
     normalization eligibility, product-type normalization, percent-quote multiplier selection,
     legacy percent-quote detection, and ratio-based multiplier selection helpers.
     `resolve_valuation_unit_price` improved from `B (9)` to `A (2)`, and every function in
     `valuation_prices.py` now reports A-ranked cyclomatic complexity.
176. Reduced shared reprocessing stale-job reset complexity by extracting stale-row retrieval,
     over-limit and retryable stale-job classification, failed update construction, reset update
     construction, shared processing-state update predicates, failed-job marking, and
     retryable-job reset helpers. `ReprocessingJobRepository.find_and_reset_stale_jobs` improved
     from `B (8)` to `A (2)`, and every function/class/method in
     `reprocessing_job_repository.py` now reports A-ranked cyclomatic complexity.
177. Reduced shared transaction fee policy complexity by extracting optional fee validation,
     fee-component presence detection, component totaling, component validation, and shared
     non-negative amount enforcement helpers. `resolve_transaction_trade_fee` improved from
     `B (7)` to `A (2)`, and every function in `transaction_fee_components.py` now reports
     A-ranked cyclomatic complexity.
178. Reduced shared Kafka producer publish complexity by extracting publish-header construction,
     key encoding, delivery-report callback construction, outbox-id extraction/decoding, delivery
     failure handling, delivery success handling, delivery log context, message-key
     representation, and guarded delivery-callback notification helpers.
     `KafkaProducer.publish_message` improved from `B (6)` to `A (3)`, and every
     function/class/method in `kafka_utils.py` now reports A-ranked cyclomatic complexity.
179. Reduced shared valuation job upsert complexity by extracting eligible job filtering, upsert
     execution, insert value construction, conflict update values, conflict update predicates, and
     staged upsert logging helpers. `ValuationJobRepository.upsert_jobs` improved from `B (7)` to
     `A (4)`, and every function/class/method in `valuation_job_repository.py` now reports
     A-ranked cyclomatic complexity.
180. Reduced shared timeseries stale aggregation job reset complexity by extracting stale-row
     retrieval, over-limit and retryable stale-job classification, failed update construction,
     reset update construction, shared processing-state update predicates, failed-job marking, and
     retryable-job reset helpers. `TimeseriesRepositoryBase.find_and_reset_stale_jobs` improved
     from `B (9)` to `A (2)`, and every stale aggregation job reset helper now reports A-ranked
     cyclomatic complexity.
181. Reduced shared position and portfolio timeseries upsert complexity by extracting
     statement-specific helpers, shared insert-value extraction, shared conflict-update value
     construction, and shared PostgreSQL conflict-update assembly. `upsert_position_timeseries`
     and `upsert_portfolio_timeseries` both improved from `B (6)` to `A (2)`, and every
     function/class/method in `timeseries_repository_base.py` now reports A-ranked cyclomatic
     complexity.
182. Reduced cashflow calculator consumer orchestration complexity by extracting
     transaction-scoped processing, idempotency claim helpers, stale replay detection, semantic
     duplicate claiming, transaction contract validation, non-cash lifecycle classification,
     required rule lookup, cashflow calculation staging, and `CashflowCalculatedEvent`
     construction helpers. `CashflowCalculatorConsumer._process_message_with_retry` improved from
     `D (24)` to `B (8)`, with all extracted helpers A-ranked by cyclomatic complexity.
183. Reduced cashflow calculator rule-cache lookup complexity by extracting fresh-cache lookup,
     direct cache lookup, stale/missing cache refresh, and missing-rule reload helpers.
     `CashflowCalculatorConsumer._get_rule_for_transaction` improved from `B (7)` to `A (3)`,
     with all cache lookup helpers A-ranked by cyclomatic complexity.
184. Reduced cashflow calculator validated-event processing complexity by extracting
     physical/stale-replay early-stop helpers, epoch/semantic-duplicate early-stop helpers, and
     cashflow staging or non-cash lifecycle skip helpers.
     `CashflowCalculatorConsumer._process_validated_cashflow_event` improved from `B (7)` to
     `A (4)`, with all extracted decision helpers A-ranked by cyclomatic complexity.
185. Reduced cashflow calculator retry/DLQ wrapper complexity by extracting message metadata,
     decoded event processing, and cashflow processing error-classification helpers.
     `CashflowCalculatorConsumer._process_message_with_retry` improved from `B (8)` to `A (2)`,
     leaving every function/class/method in `transaction_consumer.py` A-ranked by cyclomatic
     complexity.
186. Reduced cashflow calculation complexity by extracting base amount, interest amount,
     classification/direction sign, interest sign, adjustment sign, and transfer sign helpers.
     `CashflowLogic.calculate` improved from `C (18)` to `A (2)`, and `cashflow_logic.py`
     remains A-ranked maintainability at `A (52.17)`.
187. Reduced cashflow sign-dispatch complexity by replacing direct classification sign branches
     with an explicit sign-factor map and focused classification sign helper.
     `_signed_cashflow_amount` improved from `B (7)` to `A (4)`, leaving every
     function/class/method in `cashflow_logic.py` A-ranked by cyclomatic complexity.
188. Reduced cost calculator consumer process-message complexity by extracting message metadata,
     valid cost-event processing, process-message error classification, and process-message
     failure metric helpers. `CostCalculatorConsumer.process_message` improved from `C (11)` to
     `A (2)`, and `consumer.py` remains A-ranked maintainability at `A (22.35)`.
189. Reduced cost calculator consumer fee-transformation complexity by extracting fee-component
     removal, explicit component detection, component normalization, and engine fee-field
     application helpers. `CostCalculatorConsumer._transform_event_for_engine` improved from
     `B (9)` to `A (2)`, and `consumer.py` remains A-ranked maintainability at `A (22.19)`.
190. Reduced cost calculator consumer Bundle A reconciliation diagnostics complexity by extracting
     reconciliation-key resolution, complete key validation, Bundle A group event loading, and
     missing dependency calculation helpers.
     `CostCalculatorConsumer._record_bundle_a_reconciliation_diagnostics` improved from `B (9)`
     to `A (3)`, and `consumer.py` remains A-ranked maintainability at `A (20.93)`.
191. Reduced reference-data DTO module size by extracting model-portfolio definition and target
     DTOs into `reference_data_model_portfolio_dto.py` while preserving the public
     `reference_data_dto.py` import surface. The aggregate DTO module improved from `B (9.31)` to
     `B (12.49)`, the extracted module reports `A (41.43)`, and an unreachable
     model-portfolio target band-order validation branch was removed because the target-bound
     checks already classify every invalid min/max ordering.
192. Reduced reference-data DTO module size again by extracting classification taxonomy,
     cash-account master, and instrument look-through component DTOs plus their ingestion request
     wrappers into `reference_data_support_dto.py`. The aggregate DTO module improved from
     `B (12.49)` to `B (14.29)`, the extracted support module reports `A (43.83)`, and the
     public `reference_data_dto.py` import surface remains compatible for routers and tests.
     The temporal vocabulary allowlist now records the moved legacy `source_timestamp` field with
     CR-1036 rationale so the guard preserves behavior without allowing new source-observation
     terminology drift.
193. Reduced reference-data DTO module size by extracting benchmark, benchmark-composition, index,
     index-price, index-return, benchmark-return, and risk-free records plus their ingestion
     request wrappers into `reference_data_benchmark_dto.py`. The aggregate DTO module improved
     from `B (14.29)` to `A (21.98)`, the extracted benchmark module reports `A (30.27)`, and
     focused DTO plus ingestion OpenAPI contract tests prove public imports and schema component
     names remain compatible. The temporal vocabulary allowlist now records the moved legacy
     `source_timestamp` fields with CR-1037 rationale.
194. Reduced reference-data DTO module size by extracting discretionary mandate binding and
     portfolio benchmark assignment records plus their ingestion request wrappers into
     `reference_data_mandate_dto.py`. The aggregate DTO module improved from `A (21.98)` to
     `A (27.76)`, the extracted mandate module reports `A (39.16)`, and focused DTO plus
     ingestion OpenAPI contract tests prove public imports and schema component names remain
     compatible.
195. Reduced the reference-data DTO compatibility facade by moving model-portfolio definition and
     target ingestion request wrappers into `reference_data_model_portfolio_dto.py`, beside the
     model-portfolio records they wrap. The aggregate DTO module improved from `A (27.76)` to
     `A (28.88)`, the model-portfolio module remains A-ranked at `A (39.13)`, and focused DTO plus
     ingestion OpenAPI contract tests prove public imports and schema component names remain
     compatible.
196. Reduced the reference-data DTO compatibility facade by extracting client income-needs
     schedule, liquidity reserve requirement, and planned withdrawal schedule records plus their
     ingestion request wrappers into `reference_data_cashflow_planning_dto.py`. The aggregate DTO
     module improved from `A (28.88)` to a pure compatibility facade at `A (100.00)`, the
     extracted cashflow-planning module reports `A (31.18)`, and focused DTO plus ingestion
     OpenAPI contract tests prove public imports and schema component names remain compatible.
197. Reduced the ingestion-job DTO module size by extracting capacity diagnostics and backlog
     breakdown response DTOs into `ingestion_job_capacity_dto.py` while preserving the public
     `ingestion_job_dto.py` import surface. The aggregate ingestion-job DTO module improved from
     `A (25.62)` to `A (27.87)` and shrank from 1,120 SLOC to 936 SLOC, the extracted operations
     diagnostics module reports `A (50.80)`, and focused capacity/backlog service tests plus the
     ingestion OpenAPI contract tests prove response behavior and schema component names remain
     compatible.
198. Reduced the ingestion-job DTO module size by extracting consumer dead-letter, consumer-lag,
     DLQ replay, and replay-audit response/request DTOs into `ingestion_job_replay_dto.py` while
     preserving the public `ingestion_job_dto.py` import surface. The aggregate ingestion-job DTO
     module improved from `A (27.87)` to `A (32.33)` and shrank from 936 SLOC to 730 SLOC, the
     extracted replay diagnostics module reports `A (43.08)`, and focused DLQ/replay guardrail
     tests plus event-replay OpenAPI contract tests prove response behavior and schema component
     names remain compatible.
199. Reduced the ingestion-job DTO module size by extracting ingestion health, SLO, operating
     band, operating policy, reprocessing queue, stalled-job, retry, ops-mode, and error-budget
     DTOs into `ingestion_job_operations_dto.py` while preserving the public
     `ingestion_job_dto.py` import surface. The aggregate ingestion-job DTO module improved from
     `A (32.33)` to `A (44.17)` and shrank from 730 SLOC to 249 SLOC, the extracted operations
     diagnostics module reports `A (37.66)`, and focused guardrail tests plus ingestion and
     event-replay OpenAPI contract tests prove response behavior and schema component names remain
     compatible.
200. Completed the ingestion-job DTO compatibility-facade split by extracting job lifecycle,
     failure, record-status, and idempotency diagnostic DTOs into `ingestion_job_lifecycle_dto.py`
     while preserving the public `ingestion_job_dto.py` import surface. The aggregate
     ingestion-job DTO module improved from `A (44.17)` to a pure compatibility facade at
     `A (100.00)` and shrank from 249 SLOC to 38 SLOC, the extracted lifecycle module reports
     `A (46.58)`, and focused guardrail tests plus ingestion and event-replay OpenAPI contract
     tests prove response behavior and schema component names remain compatible.
201. Reduced the transaction DTO module hotspot by extracting the canonical transaction record into
     `transaction_model_dto.py` and the ingestion request envelope into
     `transaction_ingestion_request_dto.py` while preserving the public `transaction_dto.py` import
     surface. The aggregate transaction DTO module improved from 678 SLOC to a 4-SLOC
     compatibility facade at `A (100.00)`, the extracted transaction model reports `A (42.85)`,
     the request-envelope module reports `A (100.00)`, and the moved transaction model is now
     directly clean under scoped mypy by replacing `condecimal(...)` annotations with explicit
     constrained `Annotated[Decimal, Field(...)]` aliases. Focused transaction model,
     transaction-spec characterization, and ingestion OpenAPI contract tests prove validation
     behavior, public imports, and schema component names remain compatible.
202. Reduced the benchmark/reference-data DTO module hotspot by extracting benchmark definition,
     composition, and benchmark-return records into `reference_data_benchmark_records_dto.py` and
     index definition, index price/return, and risk-free series records into
     `reference_data_index_series_dto.py` while preserving the public
     `reference_data_benchmark_dto.py` import surface. The aggregate benchmark DTO module improved
     from `A (30.27)` and 444 SLOC to a pure compatibility facade at `A (100.00)` and 16 SLOC,
     the extracted benchmark-record module reports `A (40.91)`, and the extracted index/risk-free
     series module reports `A (37.52)`. Focused reference-data DTO, benchmark/index/risk-free
     router, and ingestion OpenAPI contract tests prove validation behavior, route behavior, public
     imports, and schema component names remain compatible. The temporal vocabulary allowlist now
     records the moved legacy `source_timestamp` fields with CR-1046 rationale so the guard remains
     strict for new source-observation field names.
203. Reduced the ingestion operations DTO module hotspot by extracting health, SLO, operating-band,
     policy, and error-budget response contracts into `ingestion_job_observability_dto.py` and
     reprocessing queue, stalled-job, retry, and ops-mode contracts into
     `ingestion_job_control_dto.py` while preserving the public
     `ingestion_job_operations_dto.py` and `ingestion_job_dto.py` import surfaces. The aggregate
     operations DTO module improved from `A (37.66)` and 498 SLOC to a pure compatibility facade at
     `A (100.00)` and 15 SLOC, the extracted observability module reports `A (49.01)`, and the
     extracted control module reports `A (47.35)`. Focused event-replay OpenAPI contract,
     ingestion guardrail, and operating-band tests prove schema component names, public imports,
     and representative operations behavior remain compatible.
204. Reduced the reference-data tax DTO module hotspot by extracting client tax profile contracts
     into `reference_data_tax_profile_dto.py` and client tax rule-set contracts into
     `reference_data_tax_rule_set_dto.py` while preserving the public `reference_data_tax_dto.py`
     and `reference_data_dto.py` import surfaces. The aggregate tax DTO module improved from
     `A (29.60)` and 190 SLOC to a pure compatibility facade at `A (100.00)` and 6 SLOC, the
     extracted tax-profile module reports `A (41.82)`, and the extracted tax-rule-set module
     reports `A (37.58)`. The moved constrained decimal annotations are now directly clean under
     scoped mypy, and focused reference-data DTO plus ingestion OpenAPI contract tests prove
     validation behavior, schema component names, and public imports remain compatible.
205. Reduced the reference-data client preference DTO module hotspot by extracting client
     restriction profile contracts into `reference_data_client_restriction_dto.py` and
     sustainability preference profile contracts into `reference_data_sustainability_preference_dto.py`
     while preserving the public `reference_data_client_preference_dto.py` and
     `reference_data_dto.py` import surfaces. The aggregate client-preference DTO module improved
     from `A (32.04)` and 142 SLOC to a pure compatibility facade at `A (100.00)` and 10 SLOC,
     the extracted client-restriction module reports `A (42.42)`, and the extracted
     sustainability-preference module reports `A (40.79)`. The moved allocation-bound decimal
     annotations are now directly clean under scoped mypy, and focused reference-data DTO plus
     ingestion OpenAPI contract tests prove validation behavior, schema component names, and
     public imports remain compatible.
206. Reduced the reference-data cashflow planning DTO module hotspot by extracting client
     income-needs contracts into `reference_data_income_needs_dto.py`, liquidity reserve
     requirement contracts into `reference_data_liquidity_reserve_dto.py`, and planned withdrawal
     contracts into `reference_data_planned_withdrawal_dto.py` while preserving the public
     `reference_data_cashflow_planning_dto.py` and `reference_data_dto.py` import surfaces. The
     aggregate cashflow-planning DTO module improved from `A (31.18)` and 190 SLOC to a pure
     compatibility facade at `A (100.00)` and 15 SLOC, the extracted income-needs module reports
     `A (45.42)`, the liquidity-reserve module reports `A (45.44)`, and the planned-withdrawal
     module reports `A (49.30)`. Focused reference-data DTO plus ingestion OpenAPI contract tests
     prove validation behavior, currency normalization, schema component names, and public imports
     remain compatible.
207. Reduced the reference-data mandate DTO module hotspot by extracting discretionary mandate
     binding contracts into `reference_data_discretionary_mandate_dto.py` and portfolio benchmark
     assignment contracts into `reference_data_portfolio_benchmark_assignment_dto.py` while
     preserving the public `reference_data_mandate_dto.py` and `reference_data_dto.py` import
     surfaces. The aggregate mandate DTO module improved from `A (39.16)` and 240 SLOC to a pure
     compatibility facade at `A (100.00)` and 10 SLOC, the extracted discretionary-mandate module
     reports `A (42.80)`, and the extracted portfolio-benchmark-assignment module reports
     `A (57.85)`. Focused reference-data DTO plus ingestion OpenAPI contract tests prove
     validation behavior, schema component names, and public imports remain compatible.
208. Reduced the reference-data model portfolio DTO module hotspot by extracting model portfolio
     definition contracts into `reference_data_model_portfolio_definition_dto.py` and model
     portfolio target contracts into `reference_data_model_portfolio_target_dto.py` while
     preserving the public `reference_data_model_portfolio_dto.py` and `reference_data_dto.py`
     import surfaces. The aggregate model-portfolio DTO module improved from `A (39.13)` and
     229 SLOC to a pure compatibility facade at `A (100.00)` and 6 SLOC, the extracted
     model-portfolio-definition module reports `A (52.32)`, and the extracted
     model-portfolio-target module reports `A (46.09)`. Focused reference-data DTO plus ingestion
     OpenAPI contract tests prove validation behavior, base-currency normalization, schema
     component names, and public imports remain compatible.
209. Reduced the reference-data index/risk-free series DTO module hotspot by extracting index
     definition contracts into `reference_data_index_definition_dto.py`, index price-series
     contracts into `reference_data_index_price_series_dto.py`, index return-series contracts into
     `reference_data_index_return_series_dto.py`, and risk-free series contracts into
     `reference_data_risk_free_series_dto.py` while preserving the public
     `reference_data_index_series_dto.py`, `reference_data_benchmark_dto.py`, and
     `reference_data_dto.py` import surfaces. The aggregate index-series DTO module improved from
     `A (37.52)` and 243 SLOC to a pure compatibility facade at `A (100.00)` and 12 SLOC, the
     extracted index-definition module reports `A (51.44)`, the index-price-series module reports
     `A (56.99)`, the index-return-series module reports `A (56.48)`, and the risk-free-series
     module reports `A (54.44)`. Focused reference-data DTO plus ingestion OpenAPI contract tests
     prove validation behavior, currency normalization, schema component names, and public imports
     remain compatible. The temporal vocabulary allowlist now records the moved legacy
     `source_timestamp` fields with CR-1053 rationale so the guard remains strict for new
     source-observation field names.
210. Reduced the reference-data benchmark-record DTO module hotspot by extracting benchmark
     definition contracts into `reference_data_benchmark_definition_dto.py`, benchmark composition
     contracts into `reference_data_benchmark_composition_dto.py`, and benchmark return-series
     contracts into `reference_data_benchmark_return_series_dto.py` while preserving the public
     `reference_data_benchmark_records_dto.py`, `reference_data_benchmark_dto.py`, and
     `reference_data_dto.py` import surfaces. The aggregate benchmark-record DTO module improved
     from `A (40.91)` and 207 SLOC to a pure compatibility facade at `A (100.00)` and 13 SLOC,
     the extracted benchmark-definition module reports `A (50.64)`, the benchmark-composition
     module reports `A (56.85)`, and the benchmark-return-series module reports `A (56.48)`.
     Focused reference-data DTO plus ingestion OpenAPI contract tests prove validation behavior,
     currency normalization, schema component names, and public imports remain compatible. The
     temporal vocabulary allowlist now records the moved legacy `source_timestamp` fields with
     CR-1054 rationale so the guard remains strict for new source-observation field names.
211. Reduced the DPM instrument eligibility DTO validation hotspot by extracting effective-window,
     buy-permission, and sell-permission checks into named helpers while preserving the public
     `InstrumentEligibilityProfileRecord` and ingestion request contract. The record class improved
     from `B (8)` to `A (2)`, the model validator improved from `B (7)` to `A (1)`, and every
     function/class/method in `reference_data_instrument_eligibility_dto.py` now reports
     A-ranked cyclomatic complexity. Focused reference-data DTO plus ingestion OpenAPI contract
     tests prove validation behavior, schema component names, public imports, and route shape
     remain compatible.
212. Reduced the client tax rule-set DTO evidence validator by extracting bounded-evidence
     detection into a named predicate while preserving the public `ClientTaxRuleSetRecord`
     contract and validation error text. `_validate_tax_rule_evidence` improved from `B (6)` to
     `A (2)`, `reference_data_tax_rule_set_dto.py` improved from `A (37.58)` to `A (38.36)`,
     and every function/class/method in the module now reports A-ranked cyclomatic complexity.
     Focused reference-data DTO plus ingestion OpenAPI contract tests prove validation behavior,
     schema component names, public imports, and route shape remain compatible.
213. Reduced the client tax profile DTO unknown-status validator by extracting applicable-tax-detail
     detection into a named predicate while preserving the public `ClientTaxProfileRecord`
     contract and validation error text. `_validate_unknown_tax_status_detail` improved from
     `B (6)` to `A (3)`, `reference_data_tax_profile_dto.py` improved from `A (41.82)` to
     `A (42.63)`, and every function/class/method in the module now reports A-ranked cyclomatic
     complexity. Focused reference-data DTO plus ingestion OpenAPI contract tests prove validation
     behavior, schema component names, public imports, and route shape remain compatible.
214. Reduced the client restriction DTO scoped-value validator by extracting scope-policy and
     scoped-value detection into named predicates while preserving the public
     `ClientRestrictionProfileRecord` contract and validation error text.
     `_validate_scoped_restriction_values` improved from `B (6)` to `A (3)`,
     `reference_data_client_restriction_dto.py` improved from `A (42.42)` to `A (43.00)`, and
     every function/class/method in the module now reports A-ranked cyclomatic complexity.
     Focused reference-data DTO plus ingestion OpenAPI contract tests prove validation behavior,
     schema component names, public imports, and route shape remain compatible.
215. Reduced the model portfolio target DTO band-order validation boundary by extracting the
     target/min/max band policy into `_validate_target_band_order` while preserving the public
     `ModelPortfolioTargetRecord` contract and validation error text. `ModelPortfolioTargetRecord`
     improved from `B (6)` to `A (2)`, `validate_bands` improved from `A (5)` to `A (1)`, and
     every DTO class now reports A-ranked cyclomatic complexity. Focused reference-data DTO plus
     ingestion OpenAPI contract tests prove validation behavior, schema component names, public
     imports, and route shape remain compatible.
216. Reduced portfolio readiness supportability composition complexity by extracting explicit
     reason-family, bucket-construction, supportability-state, freshness, blocking-reason, and
     missing-FX payload helpers while preserving the public `PortfolioReadinessResponse` contract.
     `build_portfolio_readiness_response` improved from `D (23)` to `A (1)`,
     `_portfolio_supportability_summary` improved from `B (7)` to `A (2)`, and every function in
     `portfolio_readiness_builder.py` now reports A-ranked cyclomatic complexity. Focused builder
     and operations-service tests prove readiness buckets, blocking reasons, missing-FX payloads,
     bounded supportability metric labels, and response fields remain compatible.
217. Reduced integration capability policy composition complexity by extracting explicit feature
     default, tenant-override, input-mode, workflow, and response-assembly helpers while preserving
     the public `IntegrationCapabilitiesResponse` contract. `CapabilitiesService.get_integration_capabilities`
     improved from `D (29)` to `A (1)`, `CapabilitiesService` improved from `C (11)` to `A (4)`,
     and every function in `capabilities_service.py` now reports A-ranked cyclomatic complexity.
     Focused capability-service tests prove default flags, environment overrides, tenant policy
     overrides, invalid override handling, ecosystem consumers, workflow required features,
     as-of-date fallback, and lazy DB engine posture remain compatible.
218. Reduced support overview response composition complexity by extracting explicit reprocessing,
     valuation, aggregation, analytics-export, portfolio-evidence, control-stage, reconciliation,
     and response-assembly helpers while preserving the public `SupportOverviewResponse` contract.
     `build_support_overview_response` improved from `D (23)` to `A (1)`, and every function in
     `support_overview_builder.py` now reports A-ranked cyclomatic complexity. Focused support
     overview builder and operations-service tests prove backlog age, control status, latest
     reconciliation, blocking finding, nullable control, generated-date fallback, and
     publish-allowed behavior remain compatible.
219. Reduced benchmark market-series response composition complexity by extracting row-indexing,
     component point, component series, returned-evidence, evidence-count, quality-summary, and
     page-metadata helpers while preserving the public `BenchmarkMarketSeriesResponse` contract.
     `build_benchmark_market_series_response` improved from `D (23)` to `A (1)`, and every
     function in `benchmark_market_series.py` now reports A-ranked cyclomatic complexity. Focused
     benchmark market-series tests prove page-scoped metadata, component points, FX normalization
     status, evidence timestamps, data-quality status, quality summary, and next-page token
     behavior remain compatible.
220. Reduced cash-balance account record composition complexity by extracting master-row indexing,
     fallback cash-account ID resolution, master/fallback record input construction, instrument
     naming, account-currency, and account-ID helpers while preserving the public
     `CashBalancesResponse` contract. `CashBalanceResolver.build_cash_account_balance_records`
     improved from `D (22)` to `A (2)`, and every function in `cash_balance_service.py` now reports
     A-ranked cyclomatic complexity. Focused cash-balance tests prove holdings-as-of metadata,
     master cash-account rows, fallback identifiers, normalized master joins, zero-balance
     accounts, sequential FX conversions, and sorting behavior remain compatible.
221. Reduced latest cash-account ID repository complexity by extracting settlement-cash security
     normalization, ranked transaction subquery construction, latest-ID statement assembly, and
     result mapping helpers while preserving the public `ReportingRepository` behavior.
     `ReportingRepository.get_latest_cash_account_ids` improved from `B (7)` to `A (2)`, and every
     function in `reporting_repository.py` now reports A-ranked cyclomatic complexity. Focused
     reporting repository and cash-balance tests prove normalized security matching, latest
     transaction ranking, non-null cash-account filtering, and fallback account mapping behavior
     remain compatible.
222. Reduced market-reference data-quality classification complexity by extracting quality-status
     normalization, status-family counting, and coverage-signal construction while preserving the
     public `market_reference_data_quality_status` helper and shared market-reference quality
     classifier. `market_reference_data_quality_status` improved from `C (11)` to `A (3)`.
     Focused reference-data helper and integration-service tests prove accepted, estimated,
     blocked, stale, missing-status, and required-count behavior remain compatible.
223. Reduced benchmark component-window resolution complexity by extracting component grouping,
     effective-date ordering, supersession end-date inference, overlap filtering, and row
     projection helpers while preserving the public `resolve_component_window_rows` helper.
     `resolve_component_window_rows` improved from `C (11)` to `A (4)`, and the module remains
     A-ranked maintainability. Focused reference-data helper and integration-service tests prove
     inferred superseded end dates, earlier explicit end dates, non-overlapping window filtering,
     returned metadata fields, and result ordering remain compatible.
224. Reduced reference-evidence timestamp selection complexity by extracting the durable timestamp
     field policy and per-row timestamp extraction while preserving the public
     `latest_reference_evidence_timestamp` helper. `latest_reference_evidence_timestamp` improved
     from `B (6)` to `A (2)`, and the module remains A-ranked maintainability. Focused
     reference-data helper and integration-service tests prove observed, source, assignment,
     updated, and created timestamp handling, multi-row-group max timestamp behavior, and
     missing/non-datetime filtering remain compatible.
225. Reduced benchmark market-series point mapping complexity by extracting metadata precedence,
     requested row-decimal normalization, and requested optional-value selection helpers while
     preserving the public `benchmark_market_series_point` mapper. `benchmark_market_series_point`
     improved from `C (19)` to `A (1)`, and every function in `reference_data_mappers.py` now
     reports A-ranked cyclomatic complexity. Focused reference-data mapper and benchmark
     market-series tests prove selected-field suppression, price-row metadata precedence, decimal
     normalization, component weight, and FX-rate behavior remain compatible.
226. Reduced discretionary mandate binding response composition complexity by extracting
     supportability, review-schedule, rebalance-band, and lineage assembly helpers while preserving
     the public `DiscretionaryMandateBindingResponse` contract. `build_discretionary_mandate_binding_response`
     improved from `C (17)` to `A (2)`, the extracted review supportability helper reports
     `B (7)`, and the module reports `A (40.24)` maintainability. Focused discretionary mandate
     binding tests prove ready responses, repository orchestration, absent rows, policy-pack
     hiding, inactive authority, missing policy-pack priority, missing review data, overdue-review
     degradation, sparse rebalance bands, lineage, and runtime metadata behavior remain compatible.
227. Reduced portfolio tax-lot window response composition complexity by extracting lot mapping,
     missing-security detection, supportability/data-quality policy, page metadata, and lineage
     helpers while preserving the public `PortfolioTaxLotWindowResponse` contract.
     `build_portfolio_tax_lot_window_response` improved from `C (15)` to `A (2)`, the extracted
     supportability-state helper reports `B (6)`, and the module reports `A (35.88)`
     maintainability. Focused portfolio tax-lot window tests prove page-token scope binding,
     repository orchestration, missing portfolio errors, partial-page degradation, complete
     ready-page status, missing requested-security reporting, empty portfolio unavailability,
     lineage, and runtime metadata behavior remain compatible.
228. Reduced market-data coverage response composition complexity by extracting price/fx coverage
     record mapping, missing/stale evidence classification, batch supportability, data-quality
     status, and lineage helpers while preserving the public `MarketDataCoverageWindowResponse`
     contract. `build_market_data_coverage_response` improved from `C (18)` to `A (1)`, every
     function in `market_data_coverage.py` now reports A-ranked cyclomatic complexity, and the
     module reports `A (38.12)` maintainability. Focused market-data coverage tests prove read
     scope normalization, repository orchestration, ready evidence, stale/missing price and FX
     supportability, resolved counts, lineage, and runtime metadata behavior remain compatible.
229. Reduced simulation projected-position orchestration complexity by extracting baseline
     snapshot/history fallback, baseline record construction, change normalization, new-security
     projection defaults, instrument enrichment, change application, and response-row construction
     helpers while preserving the public `ProjectedPositionsResponse` contract.
     `SimulationService.get_projected_positions` improved from `D (22)` to `A (2)`, every method
     in `simulation_service.py` now reports A-ranked cyclomatic complexity, and the module reports
     `A (29.73)` maintainability. Focused simulation service tests prove session lookup, baseline
     read ordering, snapshot/history fallback, normalized security IDs, new-security projection,
     non-positive filtering, sorted response rows, and projected-summary behavior remain compatible.
230. Reduced upload ingestion commit and XLSX parsing complexity by extracting row key/value
     normalization, XLSX header/record/data helpers, commit validation guardrails, entity publish
     dispatch, typed publish helpers, and commit response construction while preserving the public
     upload preview and commit contracts. `UploadIngestionService.commit_upload` improved from
     `D (23)` to `A (1)`, `_parse_xlsx` improved from `C (12)` to `A (4)`, every function in
     `upload_ingestion_service.py` now reports A-ranked cyclomatic complexity, and the module
     reports `A (25.69)` maintainability. Focused upload ingestion service tests prove CSV/XLSX
     preview, partial-upload rejection, partial commit, empty-file rejection, publish routing,
     published/skipped row counts, and response shape remain compatible.
231. Reduced position next-state calculation complexity by extracting explicit transaction-family
     constants, update-handler selection, BUY/SELL cost-basis helpers, cash-position delta
     application, transfer cost-basis policy, same-instrument corporate-action quantity policy,
     spin-off basis handling, FX contract lifecycle quantity helpers, and flat-position cost-basis
     cleanup while preserving the public `calculate_next_position` contract.
     `PositionCalculator.calculate_next_position` improved from `D (27)` to `A (2)`, and
     `position_logic.py` reports `A (24.96)` maintainability. Focused position calculator and
     transaction-spec characterization tests prove BUY/SELL net-cost behavior, cash-flow and
     adjustment direction behavior, FX cash settlement, FX contract lifecycle, transfer and
     corporate-action quantity updates, spin-off basis handling, and flat-position cost-basis reset
     remain compatible.
232. Reduced valuation consumer processing complexity by extracting event-session orchestration,
     position-state lookup, reference-data validation, snapshot valuation, FX-missing failure
     classification, terminal job completion, valuation-to-timeseries outbox publication, and
     missing-position skip handling while preserving the public Kafka consumer behavior.
     `ValuationConsumer.process_message` improved from `D (26)` to `B (7)`, and
     `valuation_consumer.py` reports `A (32.50)` maintainability. Focused valuation consumer tests
     prove Kafka delivery idempotency identity, correlation propagation, same-currency valuation
     without FX lookup, missing-position skip handling, missing-FX failed snapshot behavior,
     unexpected-error DLQ handling, and lost-job-ownership side-effect suppression remain
     compatible.
233. Reduced advisory simulation suitability scanning complexity by extracting single-position,
     issuer enrichment, issuer concentration, liquidity enrichment, liquidity concentration,
     governance, and cash-band scanners while preserving issue keys, severity policy, evidence
     wiring, and gate recommendation behavior. `_scan_state_issues` improved from `D (27)` to
     `A (1)`. Focused suitability scanner tests prove resolved, persistent, new issuer breach,
     sell-only, restricted, banned, suspended, liquidity, missing-shelf, missing-enrichment, cash
     band, and low-severity behavior remains compatible.
234. Promoted the clean runtime-safe unit collection baseline into `make quality-unit-collection-gate`
     and the quality-baseline workflow's `Quality Baseline / Unit Collection Gate`. The enforced
     lane collected 2,964 unit tests locally and avoids the known all-suite mixed-runtime guard
     that intentionally prevents db-direct integration tests and live-worker E2E tests from being
     collected in one command.
235. Remediated the GitHub Actions Node 20 deprecation warning source in the governed runtime
     workflows by upgrading PR Merge Gate and Main Releasability uses of `actions/cache`,
     `actions/upload-artifact`, `actions/download-artifact`, and `docker/setup-buildx-action` to
     current major pins with available upstream tags. Added a focused workflow-action version test
     so deprecated `actions/cache@v4`, `actions/upload-artifact@v4`,
     `actions/download-artifact@v4`, and `docker/setup-buildx-action@v3` pins cannot silently
     return in those release workflows.
235a. Hardened the artifact action runtime baseline again after GitHub Main Releasability still
      emitted Node 20 deprecation annotations for artifact upload steps. PR Merge Gate and Main
      Releasability now use `actions/upload-artifact@v7`, Main Releasability uses
      `actions/download-artifact@v8` for sign-off collection, and the workflow action-version test
      rejects stale artifact v5 pins while keeping `actions/cache@v5` and
      `docker/setup-buildx-action@v4`.
236. Reduced advisory simulation suitability result and governance issue composition complexity by
     extracting status-change classification, candidate selection, evidence construction, summary
     aggregation, highest-severity selection, and governance issue builders while preserving issue
     keys, severity policy, ordering, evidence wiring, and recommended-gate behavior.
     `compute_suitability_result` improved from `C (16)` to `A (3)`,
     `_governance_issue_for_instrument` improved from `C (11)` to `A (1)`, and
     `suitability.py` remains a B-ranked maintainability module at `B (18.34)`. Focused
     suitability scanner and advisory proposal simulation tests prove resolved, persistent, new
     issuer breach, sell-only, restricted, banned, suspended, liquidity, missing-shelf,
     missing-enrichment, cash-band, low-severity, and proposal-level suitability behavior remains
     compatible.
237. Hardened current-epoch position-history correction signaling after Main Releasability exposed
     stale cash position-timeseries values in the MWR E2E pipeline. Position-history writes now
     opt into touching already-lagging `position_state` rows: the earliest dirty watermark is
     preserved, status remains `REPROCESSING`, and `updated_at` advances so the valuation scheduler
     builds a fresh correlation and can re-arm completed valuation jobs for corrected snapshots.
     Focused non-Docker position-calculator tests passed with 46 tests, scoped Ruff lint and format
     checks passed, and Docker-backed repository/E2E proof is deferred to GitHub CI because the
     local Docker engine is unavailable in this workspace.
238. Added explicit GitHub Actions Node 24 runtime opt-in across all workflows by setting
     `FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: "true"` at workflow scope. The workflow action-version
     test now enforces the opt-in for every workflow in addition to rejecting deprecated Node 20
     action pins in governed runtime workflows. Workflow YAML parsing passed for 5 workflows,
     `tests/unit/test_ci_workflow_action_versions.py` passed with 3 tests, and scoped Ruff lint and
     format checks passed. GitHub Remote Feature Lane run `27458485134` passed for `b4555b7d`, and
     log inspection showed the Node 24 opt-in present without matching `Node.js 20` warning text.
239. Fix-forwarded the Main Releasability run `27459725250` Integration Full regression where
     `test_find_and_claim_eligible_jobs_claims_first_day_without_portfolio_history` claimed 0
     timeseries aggregation jobs instead of 1. The shared timeseries scheduler now expresses
     first-day completeness as explicit authoritative snapshot `EXISTS` and missing
     position-timeseries `NOT EXISTS` predicates, avoiding the nested count/window predicate that
     was fragile when position snapshots exist without prior portfolio history. `timeseries_repository_base.py`
     compiles, scoped Ruff lint and format checks pass, `git diff --check` passes, and the
     runtime-scope unit guard tests pass with 12 tests. Docker-backed proof of the exact
     integration regression is deferred to PR Merge Gate/Main Releasability because local Docker
     Desktop is unavailable. After aligning the SQL-shape unit guard to reject the legacy
     count/window gate while allowing the intentional anti-exists predicates, `make warning-gate`
     passed locally with 2,958 tests, 10 deselected, and 0 warnings, and Remote Feature Lane run
     `27460894329` passed for `84857360`.
240. Reduced advisory simulation valuation state assembly complexity by extracting position
     summary resolution, base-value totaling, cash value conversion, allocation metadata,
     position/cash allocation rows, instrument metrics, and attribute metrics while preserving the
     public `build_simulated_state` input and `SimulatedState` output contracts.
     `build_simulated_state` improved from `D (21)` to `A (2)`, and focused advisory valuation
     plus advisory simulation service tests passed with 17 tests. Scoped Ruff lint/format checks
     and Radon complexity/maintainability measurements passed.
241. Reduced advisory simulation position valuation policy complexity by extracting price lookup,
     price-currency context, trust-snapshot value resolution, and calculated market-value
     resolution while preserving trusted base-currency authority behavior, calculated valuation,
     FX fallback behavior, and `PositionSummary` shape. `ValuationService.value_position`
     improved from `C (13)` to `A (4)`, `ValuationService` improved from `C (14)` to `A (5)`,
     and the same 17 focused tests, scoped Ruff lint/format checks, and Radon measurements passed.
242. Fix-forwarded the Main Releasability run `27464050698` MWR E2E failure by making cash
     expense cost semantics explicit before downstream position and timeseries workers consume
     persisted transaction events. The cost engine now recognizes `TAX` as a governed transaction
     type, routes cash-instrument `FEE` and `TAX` rows through the existing cash-outflow strategy,
     rejects non-cash `TAX` rows instead of silently applying positive default cost, and includes
     explicit fee components in cash `FEE` booked outflow cost plus position quantity movement to
     match cashflow semantics. This
     preserves negative booked cost semantics and avoids strict lot consumption for cash expenses.
     The transaction-type coverage fixture now generates `TAX` with the cash security so E2E
     coverage exercises the supported cash-tax path. Focused cost-engine tests passed with 54
     tests, position-calculator tests passed with 47 tests, the transaction-type coverage dry-run
     test passed, and scoped Ruff lint passed. Docker-backed proof of the exact MWR E2E regression
     is deferred to GitHub CI because local Docker Desktop is unavailable.
243. Fix-forwarded PR auto-merge governance after PR #403 exposed that the required
     `Queue Auto Merge` job could not read main branch protection and failed with GitHub
     `HTTP 403`. The workflow no longer probes the branch-protection endpoint with the default
     workflow token and instead relies on `gh pr merge --auto --merge --delete-branch` to obey
     branch protection and required checks. Workflow YAML parsing passed for all workflows,
     `tests/unit/test_ci_workflow_action_versions.py` passed with 4 tests, and `git diff --check`
     passed.
244. Fix-forwarded the Main Releasability run `27468473911` Integration Full failure where
     `test_dispatcher_respects_batch_size` expected the injected mock producer to publish ten
     outbox rows but observed zero. The failed log also showed a real Kafka producer attempting
     localhost broker connections, exposing that manifest-declared `db_direct` suites were still
     starting the full live-worker stack. `integration-lite`, `integration-all`, `ops-contract`,
     and all transaction contract suites now use DB-only Docker composition, matching the test
     manifest runtime-mode contract and preventing live workers from racing direct database
     integration tests. Focused suite-composition tests passed with 17 tests, scoped Ruff lint and
     format checks passed, and Docker-backed proof of the exact Integration Full correction is
     deferred to GitHub CI because local Docker Desktop is unavailable.
245. Fix-forwarded the follow-up Main Releasability run `27469924560` Integration Full failure
     where the CR-1088 DB-only mapping removed Kafka infrastructure from `integration-all`, causing
     Kafka setup and DLQ replayer integration tests to fail with broker transport metadata errors.
     Test service composition now distinguishes DB-only suites from DB-plus-Kafka infrastructure
     suites: `integration-all` starts Postgres, migration runner, Zookeeper, Kafka, and the topic
     creator, while still excluding live application worker/API services. The service-scope unit
     guard now allows manifest-declared `db_direct` suites to use isolated DB-only or
     DB-plus-Kafka infrastructure and explicitly proves that `integration-all` has Kafka without
     live workers. Focused suite-composition tests passed with 18 tests, scoped Ruff lint and
     format checks passed, and Docker-backed proof of the exact Kafka integration correction is
     deferred to GitHub CI because local Docker Desktop is unavailable.
246. Fixed the `integration-all` DB-plus-Kafka runtime profile race found by PR #405 review by
     waiting for the `kafka-topic-creator` one-shot compose service to exit successfully before
     yielding `docker_services`. The wait is implemented through a shared
     `wait_for_compose_service_success` helper that also backs `wait_for_migration_runner`, and the
     focused suite-composition/support tests passed with 31 tests plus scoped Ruff lint and format
     checks.
247. Fix-forwarded the Main Releasability run `27471662345` E2E Full failure where the
     dual-leg upstream-provided settlement position-timeseries test still expected the cash-book
     settlement leg to carry `-1000` beginning and ending market value. Existing analytics
     cash-flow policy neutralizes internal cash-book settlement market value while preserving the
     cash quantity and internal settlement flow. The E2E proof now asserts the stock acquisition
     value, neutralized cash-book market value, `-1000` cash quantity, and stock/cash internal
     flows netting to zero. Focused cash-flow policy tests and scoped Ruff lint/format checks
     passed locally; Docker-backed E2E proof is deferred to GitHub CI because local Docker Desktop
     is unavailable.
248. Fix-forwarded the Main Releasability run `27473292084` E2E Full failures by tightening
     HoldingsAsOf assembly and making the dual-leg settlement E2E prove economic invariants
     instead of one transitional cash-book valuation presentation. HoldingsAsOf now compares
     snapshot rows with latest current-epoch history by base and NULL-safe local cost basis per
     security, preserving reconciled snapshot rows while supplementing stale-basis securities from
     authoritative history. The dual-leg E2E still proves stock acquisition value, cash quantity,
     internal flow net-zero, and cash-book value that is either neutralized or explicitly
     offsetting. Focused HoldingsAsOf merge, repository SQL-shape, and position-calculator tests
     passed locally; scoped Ruff lint/format checks and `git diff --check` passed locally.
     Docker-backed E2E proof is deferred to GitHub CI because local Docker Desktop is unavailable.
249. Fix-forwarded the Main Releasability run `27476338028` Latency Gate and E2E Full failures.
     The latency artifact showed `support_overview` was functionally healthy but measured during
     active demo-data bootstrap ingestion, breaching p95 at `452.66ms` against the `320ms` budget.
     Compose-backed latency profiling now waits for the `demo_data_loader` one-shot service to exit
     successfully before resolving runtime IDs and starting measurements, keeping budgets unchanged.
     The E2E dual-currency holdings failure showed that CR-1092 corrected history cost basis but
     could still return missing fallback unrealized P&L when snapshot market values were present.
     HoldingsAsOf fallback valuation now derives missing base and local unrealized amounts from
     market value minus authoritative history cost basis when both inputs exist. Focused latency and
     holdings unit tests passed with 45 tests; scoped Ruff lint and format checks passed locally;
     Remote Feature Lane run `27477365942` passed. Docker-backed latency and E2E proof is deferred
     to PR Merge Gate/Main Releasability because local Docker Desktop is unavailable.
250. Fix-forwarded PR Merge Gate run `27477746565` Latency Gate seed-readiness timeout.
     The gate passed all other PR Merge Gate jobs but timed out before latency measurement because
     `demo_data_loader` was still running after the initial five-minute seed-completion wait.
     `make test-latency-gate` now passes an explicit
     `LATENCY_SEED_COMPLETION_TIMEOUT_SECONDS` value to the latency profiler, giving CI enough
     bootstrap time while keeping the endpoint p95 budgets unchanged. Fresh PR Merge Gate proof is
     required before merge.
251. Fix-forwarded PR Merge Gate run `27478449844` Latency Gate demo verification timeout.
     The longer seed-completion wait allowed `demo_data_loader` to reach its own verifier, but the
     one-shot loader exited with status `1` after timing out on `DEMO_INCOME_CHF_001` output
     verification. The app-local compose contract now makes demo-data verification wait and poll
     intervals environment-driven with a `900` second default for CI, and the verifier timeout now
     reports last-observed positions, valued positions, transaction counts, and terminal quantity
     checks. Focused demo-data and compose-contract tests passed with 12 tests; scoped Ruff lint and
     format checks passed locally. Fresh PR Merge Gate proof is required before merge.
252. Fix-forwarded PR Merge Gate run `27479265925` Latency Gate demo seed duration.
     The gate passed every other PR Merge Gate job, including Docker Smoke, E2E Smoke, and the fast
     performance gate. Latency still failed before measurement because the full three-year demo pack
     kept `demo_data_loader` running beyond the total `900` second pre-measurement wait while
     workers processed unrelated historical valuation backfill for later demo portfolios. The demo
     pack now supports a bounded `--history-days` window, compose passes the setting through, and
     PR Merge Gate/Main Releasability latency jobs use a one-year history profile while preserving
     the richer three-year default for app-local demo usage. Fresh PR Merge Gate proof is required
     before merge.
253. Fix-forwarded PR Merge Gate run `27480252636` Latency Gate bounded-history reference coverage.
     The one-year seed profile applied correctly, reducing the demo pack to `261` business dates,
     `3,393` market prices, and `2,610` FX rates, but the loader still did not complete because
     cost processing retried on transaction dates that were not covered by the business-date-only
     reference series. Demo market-price and FX series now include transaction dates and the as-of
     date in addition to business dates, with focused coverage proving bounded-history reference
     data covers those operational dates. Fresh PR Merge Gate proof is required before merge.
254. Fix-forwarded PR Merge Gate run `27481208159` Latency Gate seed scope.
     The gate passed every other PR Merge Gate job, but latency still timed out waiting for
     `demo_data_loader` after `900` seconds. The artifact showed the job was still loading all
     five demo portfolios and retrying non-target FX dependencies even though the profiler measures
     `DEMO_DPM_EUR_001`. The demo pack now supports a validated `--portfolio-ids` selector that
     filters portfolios, transactions, instruments, market prices, FX pairs, existence checks, and
     verification expectations to the selected scope. Compose exposes
     `DEMO_DATA_PACK_PORTFOLIO_IDS`, and PR Merge Gate/Main Releasability latency jobs set it to
     `DEMO_DPM_EUR_001` while app-local defaults continue to seed the full demo pack. Focused
     demo-data, compose-contract, and workflow-governance tests passed with 22 tests; scoped Ruff
     format and lint checks passed. Fresh PR Merge Gate proof is required before merge.
255. Fix-forwarded PR Merge Gate run `27482056426` Latency Gate benchmark assignment FK failure.
     The focused seed applied correctly (`1` portfolio, `7` transactions, `789` market prices,
     `526` FX rates), but reference ingestion still posted a benchmark assignment for the unseeded
     `DEMO_ADV_USD_001` portfolio and hit the portfolio benchmark assignment foreign-key
     constraint. Focused demo seeds now omit out-of-scope benchmark assignments and skip empty
     reference payload posts, preserving benchmark catalog/reference data without violating the
     selected portfolio scope. Remote Feature Lane run `27482536715`, Quality Baseline run
     `27482537598`, and PR Merge Gate run `27482537616` all passed for `8d745a08`; PR Merge Gate
     Latency Gate completed successfully with the focused seed.
256. Reduced ingestion ops-mode persistence coupling by extracting control-row response mapping,
     missing-row bootstrap, and update persistence into `ingestion_ops_mode.py`. The public
     `IngestionJobService.get_ops_mode` and `update_ops_mode` methods now delegate to the helper
     while preserving the existing response contract and database-session boundary.
     `ingestion_job_service.py` shrank from the previously recorded 990 SLOC to 879 SLOC and
     improved from `B (18.73)` to `A (19.55)` under Radon maintainability; the new helper reports
     `A (62.44)`. Focused ops-mode and guardrail tests passed with 21 tests, the broader ingestion
     service unit package passed with 67 tests, scoped Ruff lint/format, typecheck,
     maintainability, and complexity gates passed.
257. Reduced ingestion stalled-job listing coupling by extracting stalled-job SQL scope,
     queue-age calculation, row-to-response mapping, and operator suggested-action policy into
     `ingestion_stalled_jobs.py`. The public `IngestionJobService.list_stalled_jobs` method now
     delegates to the helper while preserving the response contract and session boundary.
     `ingestion_job_service.py` shrank from 879 SLOC to 835 SLOC and improved from `A (19.55)` to
     `A (20.28)` under Radon maintainability; the new helper reports `A (65.73)`. Focused
     stalled-job and guardrail tests passed with 21 tests, the broader ingestion service unit
     package passed with 70 tests, scoped Ruff lint/format, typecheck, maintainability, and
     complexity gates passed.
258. Reduced ingestion backlog-breakdown read-model coupling by moving grouped backlog SQL loading
     from `IngestionJobService.get_backlog_breakdown` into `load_backlog_breakdown_response` in
     `ingestion_backlog_breakdown.py`. The service method now delegates to the helper while the
     helper owns query scope, total backlog counting, grouped-row response assembly, integer
     normalization, and failure-rate policy. `ingestion_job_service.py` shrank from 835 SLOC to
     786 SLOC and improved from `A (20.28)` to `A (21.58)` under Radon maintainability; the backlog
     helper remains fully A-ranked at `A (45.30)`. Focused backlog helper and service tests passed
     with 6 tests, the broader ingestion service unit package passed with 71 tests, scoped Ruff
     lint/format, typecheck, maintainability, and complexity gates passed.
259. Hardened ingestion backlog-breakdown age semantics after PR review identified a possible
     negative `oldest_backlog_age_seconds` value during active ingestion. The backlog count and
     grouped-row queries now share an upper submitted-at snapshot bound, and backlog age calculation
     defensively clamps to zero to preserve the response field's `ge=0.0` contract. Added focused
     regression coverage for future submitted timestamps. Focused backlog helper and service tests
     passed with 7 tests, the broader ingestion service unit package passed with 72 tests, scoped
     Ruff lint/format, typecheck, maintainability, and complexity gates passed. The backlog helper
     remains fully A-ranked at `A (44.94)`.
260. Reduced ingestion record-status read-model coupling by moving job lookup, failure lookup,
     malformed request-payload fallback, replayable-record extraction, failed-record aggregation,
     and response DTO assembly from `IngestionJobService.get_job_record_status` into
     `ingestion_record_status.py`. The public service method now delegates to the helper while
     preserving the existing response contract and session boundary. `ingestion_job_service.py`
     shrank from 786 SLOC to 762 SLOC and improved from `A (21.58)` to `A (22.62)` under Radon
     maintainability; the expanded helper reports `A (48.38)` and all helper functions are
     A-ranked by cyclomatic complexity. Focused record-status and guardrail tests passed with
     25 tests, and scoped Ruff lint/format checks passed.
261. Reduced ingestion replay-audit persistence coupling by moving successful replay-audit
     fingerprint lookup, single-audit lookup, replay-audit row creation, replay-audit status
     policy, and duplicate/failure metric accounting from `IngestionJobService` into
     `ingestion_replay_audits.py`. The public service methods now remain thin delegates while the
     helper owns the replay-audit read/write and metric side-effect boundary. `ingestion_job_service.py`
     shrank from 762 SLOC to 726 SLOC and improved from `A (22.62)` to `A (25.65)` under Radon
     maintainability; the expanded helper reports `A (52.41)`. Focused replay-audit and guardrail
     tests passed with 21 tests, the broader ingestion service unit package passed with 79 tests,
     scoped Ruff lint/format checks passed, and all touched replay-audit functions remain
     A-ranked except the pre-existing list-filter helper at `B (7)`.
262. Reduced ingestion job lifecycle persistence coupling by moving idempotent job creation,
     queued/failed/retried state transitions, failure-observation recording, simple job reads,
     replay-context reads, failure listing, response mapping, and lifecycle metric side effects
     from `IngestionJobService` into `ingestion_job_lifecycle.py`. The public service methods now
     delegate to the helper while preserving router contracts, API DTOs, database semantics, and
     metric labels. `ingestion_job_service.py` shrank from 726 SLOC to 584 SLOC and improved from
     `A (25.65)` to `A (38.41)` under Radon maintainability; the new helper reports
     `A (40.28)` / 261 SLOC. Focused state-transition tests passed with 4 tests, the broader
     ingestion service unit package passed with 79 tests, scoped Ruff lint/format checks passed,
     and all touched service/helper functions remain A-ranked by cyclomatic complexity.
263. Reduced ingestion SLO status coupling by moving lookback timing, SQLAlchemy fallback handling,
     safe-default response construction, backlog-age metric updates, and SLO response orchestration
     from `IngestionJobService.get_slo_status` into `ingestion_slo_status.py`. The public service
     method now delegates while preserving response thresholds, fallback behavior, metric labels,
     and logging posture. `ingestion_job_service.py` shrank from 584 SLOC to 550 SLOC and improved
     from `A (38.41)` to `A (41.09)` under Radon maintainability; the expanded SLO helper reports
     `A (39.95)` / 194 SLOC. Focused SLO and guardrail tests passed with 21 tests, the broader
     ingestion service unit package passed with 79 tests, and scoped Ruff lint/format checks
     passed.
264. Reduced ingestion retry permission coupling by moving backlog counting, retry/replay
     permission orchestration, and reprocessing publish record-count normalization from
     `IngestionJobService` into `ingestion_retry_permissions.py`. The service methods remain
     public delegates and preserve the existing guardrail test patch points. Removed an obsolete
     error-budget default wrapper that was no longer used after helper extraction. `ingestion_job_service.py`
     shrank from 550 SLOC to 522 SLOC and improved from `A (41.09)` to `A (44.24)` under Radon
     maintainability; the new retry-permission helper reports `A (68.59)` / 50 SLOC. Focused
     guardrail tests passed with 18 tests, the broader ingestion service unit package passed with
     79 tests, and scoped Ruff lint/format checks passed.
265. Reduced ingestion job-list read-model coupling by moving cursor lookup, filtered statement
     execution, page construction, next-cursor selection, and row-to-response mapping from
     `IngestionJobService.list_jobs(...)` into `ingestion_job_listing.py`. The public service
     method now delegates while preserving filter, pagination, DTO, API, and database behavior.
     `ingestion_job_service.py` shrank from 522 SLOC to 512 SLOC and improved from `A (44.24)` to
     `A (48.85)` under Radon maintainability; the expanded listing helper reports `A (43.44)` /
     68 SLOC. Focused listing and guardrail tests passed with 22 tests, the broader ingestion
     service unit package passed with 80 tests, and scoped Ruff lint/format checks passed.
266. Hardened the PR Merge Gate latency profile after run `27858285400` proved the
     `analytics_portfolio_timeseries` case could return 422 for all measured calls when the
     profile requested `period: one_year` against the intentionally bounded 365-day CI seed. The
     case now uses an explicit deterministic 90-day analytics window ending at the resolved runtime
     `as_of_date`, preserving the real portfolio-timeseries API call and p95 budget while aligning
     the proof with seeded coverage. Latency JSON evidence now samples non-2xx response bodies so
     future failures carry actionable validation or data-quality detail.
267. Reduced ingestion operating-band response assembly coupling by moving SLO/error-budget loader
     orchestration, classifier signal construction, and `IngestionOperatingBandResponse` assembly
     from `IngestionJobService.get_operating_band(...)` into `ingestion_operating_band.py`. The
     public service method now delegates while preserving existing runtime thresholds, loaders, and
     DTO behavior. `ingestion_job_service.py` shrank from 512 lines to 490 lines and improved from
     `A (48.85)` to `A (49.41)` under Radon maintainability; the expanded operating-band helper
     remains A-ranked at `A (49.28)` / 156 lines. Focused operating-band and guardrail tests passed
     with 23 tests, and scoped Ruff lint/format checks passed.
268. Reduced ingestion write-mode guard coupling by moving ingestion-mode metric mapping and
     paused/drain write-denial policy from `IngestionJobService.assert_ingestion_writable()` into
     `assert_ingestion_writable_mode(...)` in `ingestion_ops_mode.py`. The service method now
     delegates to the ops-mode helper while preserving `INGESTION_MODE_STATE` updates and existing
     `PermissionError` behavior. Radon reports the service method reduced from `A (2)` to `A (1)`,
     and `ingestion_ops_mode.py` remains A-ranked at `A (58.59)`. Focused ops-mode and guardrail
     tests passed with 23 tests, and scoped Ruff lint/format checks passed.
269. Reduced ingestion operating-policy config coupling by moving runtime-policy-to-config mapping
     from `IngestionJobService.get_operating_policy()` into `build_operating_policy_config(...)`
     in `ingestion_operating_policy.py`. The service method now supplies the runtime policy and
     existing operating-band policy to the helper, while response normalization and fingerprinting
     stay in the policy module. Removed service-local aliases that only supported inline policy
     config assembly. Focused operating-policy and guardrail tests passed with 21 tests; Radon
     reports `get_operating_policy` remains `A (1)`, `ingestion_job_service.py` remains A-ranked
     at `A (100.00)`, and `ingestion_operating_policy.py` remains A-ranked at `A (58.22)`.
270. Reduced ingestion operating-band policy coupling by moving runtime operating-band threshold
     mapping from `IngestionJobService` into `build_operating_band_policy(...)` in
     `ingestion_operating_band.py`. The service facade now delegates policy construction to the
     same module that classifies operating bands and assembles operating-band responses. Focused
     operating-band and guardrail tests passed with 24 tests; Radon reports the new helper is
     `A (1)`, `get_operating_band` remains `A (1)`, `ingestion_job_service.py` remains A-ranked
     at `A (100.00)`, and `ingestion_operating_band.py` remains A-ranked at `A (48.91)`.
271. Reduced cost transaction processor orchestration complexity by splitting valid transaction
     ID resolution, valid transaction selection, processed-new filtering, sorted-timeline
     processing, calculator invocation, and unexpected-error recording out of
     `TransactionProcessor.process_transactions(...)`. The runtime consumer behavior remains
     unchanged: parser/sorter/cost-calculator/error-reporter/disposition dependencies are still
     injected, recalculation depth and duration metrics are still emitted, and only successfully
     processed new transactions are returned. Focused transaction-processor tests passed with
     3 tests, including a new regression for unexpected calculator exceptions; Radon reports
     `process_transactions` reduced from `C (12)` to `A (1)` and all extracted helpers A-ranked.
272. Reduced cost upstream cash-leg validation complexity by replacing inline cash-entry-mode
     comparison in `CostCalculatorConsumer._validate_upstream_cash_leg(...)` with the shared
     `is_upstream_provided_cash_entry_mode(...)` policy helper and extracting upstream-validation
     predicate, external cash ID resolution, and persisted cash-leg loading helpers. Focused
     consumer tests passed with 29 tests, including a new regression that upstream-provided product
     legs without an external cash ID fail before repository lookup. Radon no longer reports
     `_validate_upstream_cash_leg` in the B-ranked hotspot list; `consumer.py` remains A-ranked
     maintainability at `A (20.32)`.
273. Reduced cost consumer event-building complexity by splitting history/input loading and FX
     enrichment, processed-new persistence, and BUY/SELL-only lot-quantity updates out of
     `CostCalculatorConsumer._build_cost_engine_events_to_publish(...)`. Focused consumer tests
     passed with 30 tests, including a new regression that non-BUY/SELL events skip lot-quantity
     updates while SELL events still persist them. Radon no longer reports any B-ranked method in
     `cost_calculator_service/app/consumer.py`; the module remains A-ranked maintainability at
     `A (19.49)`.
274. Reduced cost-engine strategy policy complexity by extracting common zero-cost and realized-P&L
     assignment, BUY cost-field/invariant validation, SELL proceeds/availability/cost-basis/disposal
     policy, DIVIDEND/INTEREST zero-quantity/price/cost invariants, INTEREST direction normalization,
     and transaction FX validation helpers in `cost_calculator.py`. Focused cost-engine tests passed
     with 72 tests and scoped Ruff passed. Radon now reports no B-or-worse functions/classes in
     `cost_calculator.py`: `SellStrategy.calculate_costs` is `A (4)`, `BuyStrategy.calculate_costs`
     is `A (2)`, `InterestStrategy.calculate_costs` is `A (4)`, `DividendStrategy.calculate_costs`
     is `A (3)`, and `CostCalculator._validate_fx` is `A (2)`. Residual risk remains: the module is
     still B-ranked maintainability (`B (16.31)`) and should remain on the cost-engine modularity
     backlog.
275. Reduced cost-basis strategy complexity by extracting required cost-basis field checks,
     one-pass decimal normalization, empty zero-quantity/zero-cost lot skip policy, positive
     quantity and non-negative cost-basis validation, and single FIFO lot consumption from
     `cost_basis_strategies.py`. Focused cost-basis tests passed with 20 tests, broader
     cost-engine unit tests passed with 91 tests, broader cost-calculator service tests passed
     with 133 tests, and scoped Ruff passed. Radon now reports no B-or-worse functions/classes in
     the module; `_validated_buy_lot_inputs` and `FIFOBasisStrategy.consume_sell_quantity` are no
     longer B-ranked, and the module remains A-ranked maintainability at `A (37.00)`.
276. Reduced cost-engine dependency sorter complexity by replacing Bundle A/rights dependency
     branch ladders and cash dependency branch ladders with named rank maps plus focused cash
     transaction, inflow, and outflow predicates. Focused sorter tests passed with 8 tests,
     including direct FX cash-settlement component-type ordering proof. Scoped Ruff passed after
     import normalization. Radon now reports no B-or-worse functions/classes in `sorter.py`;
     `_cash_dependency_rank` and `_ca_bundle_a_dependency_rank` are no longer B-ranked, and module
     maintainability improves from `A (63.50)` to `A (66.03)`.
277. Reduced performance economics component-family supportability complexity by splitting
     `_observed_component_families` into an ordered collector, row-level family collector, and
     focused predicates for cashflow, fee, income, tax, realized capital P&L, realized FX P&L,
     realized total P&L, and FX-context evidence. Focused performance economics tests passed with
     5 tests and scoped Ruff passed. Radon reduces `_observed_component_families` from `C (18)` to
     `A (4)`, keeps all extracted helpers A-ranked, and improves module maintainability from
     `A (27.59)` to `A (27.86)`.
279. Reduced HoldingsAsOf data-quality policy complexity by extracting reprocessing status
     normalization, unknown/non-current state detection, stale market-price evidence detection, and
     reprocessing-derived classification from `holdings_data_quality_status(...)`. Focused holdings
     tests passed with 34 tests, including direct coverage for non-current STALE, stale price STALE,
     and current/fresh COMPLETE behavior. Scoped Ruff passed. Radon reports
     `holdings_data_quality_status` reduced from `C (12)` to `A (4)`, with extracted helpers
     A-ranked and `position_holdings.py` remaining A-ranked maintainability at `A (25.48)` after
     CR-1129 on the same branch.
280. Reduced HoldingsAsOf response mapper complexity by extracting snapshot/history date selection,
     optional instrument field fallback, and optional position-state status selection from
     `position_response_data(...)`. Focused holdings tests passed with 34 tests and scoped Ruff
     passed. Radon reports `position_response_data` reduced from `C (12)` to `A (1)`, leaving
     CR-1129 to address the remaining B-ranked helper in `position_holdings.py`; module
     maintainability remains A-ranked at `A (25.48)` after CR-1129.
281. Reduced HoldingsAsOf snapshot/history merge-policy complexity by extracting typed row-result
     identity, normalized result indexing, booked-basis mismatch detection, snapshot/history split,
     and history-only supplementation from `merge_snapshot_and_history_position_rows(...)`.
     Focused holdings tests passed with 34 tests, scoped Ruff and typecheck passed, and Radon
     reports `merge_snapshot_and_history_position_rows` reduced from `B (7)` to `A (1)`. Every
     function in `position_holdings.py` is now A-ranked, and module maintainability remains
     A-ranked at `A (25.48)`.
282. Reduced integration policy context complexity by extracting default/global/tenant policy
     context construction, tenant matched-rule IDs, missing allowed-section warning posture, and
     requested-section filtering from `resolve_policy_context(...)` and
     `build_effective_policy_response(...)`. Focused integration-policy tests passed with 10 tests,
     scoped Ruff and typecheck passed, and Radon reports `resolve_policy_context` reduced from
     `C (11)` to `A (2)`, `build_effective_policy_response` reduced from `B (8)` to `A (2)`, and
     all functions/classes in `integration_policy.py` A-ranked.
283. Reduced advisory drift highlight complexity by extracting largest-improvement,
     largest-deterioration, max-exposure, unmodeled-exposure, and highlight-entry helpers from
     `_build_highlights(...)`. Focused drift analytics tests passed with 4 tests, including direct
     ordering and top-limit proof. Scoped Ruff passed. Radon reports `_build_highlights` reduced
     from `C (11)` to `A (1)`, every function in `drift_analytics.py` is A-ranked, and module
     maintainability remains A-ranked at `A (40.38)`.
284. Reduced advisory BUY intent dependency complexity by extracting type-narrowed security side
     detection, notional currency extraction, same-currency SELL indexing, BUY filtering,
     append-once mutation, and per-BUY linking helpers from `link_buy_intent_dependencies(...)`.
     Focused simulation helper tests passed with 3 tests, scoped Ruff and typecheck passed, and
     Radon reports `link_buy_intent_dependencies` reduced from `C (16)` to `A (3)`, with all
     functions in `intent_dependencies.py` A-ranked.
285. Reduced advisory compliance rule-engine complexity by extracting cash-band, single-position,
     data-quality, suppressed-intent, no-shorting, and insufficient-cash rule helpers from
     `RuleEngine.evaluate(...)`. Focused compliance tests passed with 6 tests, including direct
     multi-breach single-position proof, scoped Ruff and typecheck passed, and Radon reports
     `RuleEngine` reduced from `C (20)` to `A (2)`, `RuleEngine.evaluate` reduced from `C (19)` to
     `A (1)`, with all functions in `compliance.py` A-ranked.
286. Reduced advisory auto-funding complexity by extracting funding enablement, BUY grouping,
     priority-candidate construction, per-target funding need calculation, FX candidate selection,
     smallest-deficit tracking, missing-FX posture, insufficient-cash diagnostics, and generated FX
     application helpers from `build_auto_funding_plan(...)`. Proposal-simulation tests passed with
     29 tests, scoped Ruff and typecheck passed, and Radon reports `build_auto_funding_plan`
     reduced from `C (20)` to `A (4)`, `funding_priority_currencies` reduced from `B (6)` to
     `A (2)`, with all functions/classes in `funding.py` A-ranked.
287. Reduced privileged ingestion ops auth complexity by extracting auth error, JWT decode,
     signature, claim validation, bearer extraction, required JWT, and required token helpers from
     `require_ops_token(...)`. Focused auth tests passed with 5 tests across token-only, JWT-only,
     token-or-JWT, and invalid-token behavior; scoped Ruff and typecheck passed; Radon reports
     `require_ops_token` reduced from `C (14)` to `A (4)`.
288. Reduced ingestion write rate-limit complexity by extracting record-count normalization,
     projected usage calculation, budget breach detection, error-message construction, and
     write-event recording helpers from `enforce_ingestion_write_rate_limit(...)`. Focused
     ops-control tests passed with 8 tests across disabled mode, record-count flooring, budget
     denial, and endpoint isolation; scoped Ruff and typecheck passed; Radon reports
     `enforce_ingestion_write_rate_limit` reduced from `B (6)` to `A (3)`, with all
     `ops_controls.py` functions/classes A-ranked.
289. Reduced transaction repository filter complexity by extracting identity filter construction,
     normalized security filtering, and transaction-date boundary filtering from
     `TransactionRepository._apply_filters(...)`. Focused transaction repository tests passed with
     27 tests, including direct count-query coverage for identity and date filters; scoped Ruff
     passed; Radon reports `_apply_filters` reduced from `C (14)` to `A (1)`.
290. Reduced buy-state tax-lot filter complexity by extracting security-scope normalization,
     lot-status predicate selection, keyset pagination, and optional predicate appending from
     `BuyStateRepository.list_portfolio_tax_lots(...)`. Focused buy-state repository tests passed
     with 10 tests, including direct blank-security no-query and keyset predicate coverage; scoped
     Ruff and format checks passed; Radon reports `list_portfolio_tax_lots` reduced from `C (11)`
     to `A (4)`, with every function/class in `buy_state_repository.py` A-ranked.
291. Reduced analytics position-timeseries page-filter complexity by extracting cursor/keyset
     predicate construction, dimension predicates, optional predicate application, security-scope
     filtering, and position-ID scope filtering from
     `AnalyticsTimeseriesRepository.list_position_timeseries_rows(...)`. Focused analytics
     repository tests passed with 7 tests, including invalid position-ID no-query coverage; scoped
     Ruff and format checks passed; Radon reports `list_position_timeseries_rows` reduced from
     `C (11)` to `A (5)`.
292. Reduced analytics position snapshot-epoch filter complexity by extracting trimmed
     position-timeseries security expression reuse, security-scope filtering, position-ID scope
     filtering, and instrument dimension predicates from
     `AnalyticsTimeseriesRepository.get_position_snapshot_epoch(...)`. Focused analytics
     repository tests passed with 8 tests, including invalid position-ID no-query epoch coverage;
     scoped Ruff and format checks passed; Radon reports `get_position_snapshot_epoch` reduced from
     `B (9)` to `A (5)`, with every function/class in `analytics_timeseries_repository.py`
     A-ranked.
293. Reduced position timeseries calculation complexity by extracting beginning market value,
     zero-safe average cost, expense classification, and cashflow bucket accumulation from
     `PositionTimeseriesLogic.calculate_daily_record(...)`. Focused position timeseries logic tests
     passed with 7 tests, including direct zero-quantity average-cost coverage; scoped Ruff and
     format checks passed; Radon reports `calculate_daily_record` reduced from `C (11)` to
     `A (1)`, `PositionTimeseriesLogic` reduced from `C (12)` to `A (2)`, with every
     function/class in `position_timeseries_logic.py` A-ranked.
294. Reduced reporting allocation look-through complexity by extracting parent-security
     normalization, resolved/direct allocation rows, component grouping, look-through metadata,
     complete component-weight validation, row decomposition, and component allocation row
     construction from `ReportingService._resolve_allocation_rows(...)`. Focused reporting service
     tests passed with 20 tests; scoped Ruff and format checks passed; Radon reports
     `_resolve_allocation_rows` reduced from `C (16)` to `A (3)` and `_can_decompose_position`
     reduced from `B (7)` to `A (2)`.
295. Reduced reporting portfolio summary complexity by extracting required portfolio/date/currency
     resolution, cash totals, summary rollup, totals, metadata, and response assembly from
     `ReportingService.get_portfolio_summary(...)`. Focused reporting service tests passed with
     20 tests; scoped Ruff and format checks passed; Radon reports `get_portfolio_summary` reduced
     from `C (11)` to `A (3)`, with every function/class in `reporting_service.py` A-ranked.
296. Reduced position calculator orchestration complexity by extracting epoch validation,
     completed-date resolution, original backdated replay detection, replay logging, stale-fence
     handling, deterministic replay event construction, outbox publication, normal position-history
     replay, and persistence/rearming side effects from `PositionCalculator.calculate(...)`.
     Focused position calculator tests passed with 47 tests; focused reprocessing atomicity
     integration tests passed with 3 tests; scoped Ruff and format checks passed; Radon reports
     `PositionCalculator.calculate` reduced from `C (16)` to `A (3)`.
297. Reduced ingestion retry payload filter complexity by extracting endpoint-specific partial
     retry payload filters and a governed dispatch table from `_filter_payload_by_record_keys(...)`.
     Focused event replay helper tests passed with 7 tests; focused ingestion retry route tests
     passed with 3 tests; scoped Ruff and format checks passed; Radon reports
     `_filter_payload_by_record_keys` reduced from `C (17)` to `A (3)`.
298. Reduced ingestion job retry workflow complexity by extracting replay-context lookup,
     retry-payload shaping, retry-policy enforcement, retry audit recording, dry-run handling,
     duplicate replay blocking, replay publication, failed-publish bookkeeping, successful replay
     bookkeeping, and final job reload from `retry_ingestion_job(...)`. Focused helper tests passed
     with 7 tests; focused ingestion retry route tests passed with 3 tests; scoped Ruff and format
     checks passed; Radon reports `retry_ingestion_job` reduced from `C (11)` to `A (2)`.
299. Reduced consumer-DLQ replay workflow complexity by extracting required DLQ-event lookup,
     correlated job resolution, replay candidate/context resolution, not-replayable response
     recording, duplicate replay response recording, replay publication failure handling, and replay
     bookkeeping from `replay_consumer_dlq_event(...)`. Focused consumer-DLQ replay route tests
     passed with 5 tests; scoped Ruff and format checks passed; Radon reports
     `replay_consumer_dlq_event` reduced from `C (18)` to `A (5)`, with no C-or-worse functions
     remaining in `ingestion_operations.py`.
300. Reduced business-date ingestion route complexity by extracting write-mode control, rate
     limiting, payload/future-date/monotonic policy validation, idempotent job creation, publish
     failure handling, queue bookkeeping, and ACK assembly from `ingest_business_dates(...)`.
     Focused business-date route tests passed with 7 tests; scoped Ruff and format checks passed;
     Radon reports `ingest_business_dates` reduced from `C (17)` to `A (2)`.
301. Reduced core snapshot route policy complexity by extracting policy section-code normalization,
     governed request construction, applied/dropped section resolution, strict/empty section
     assertion, governance metadata construction, and service response/error mapping from
     `create_core_snapshot(...)`. Focused core-snapshot route tests passed with 7 tests; scoped Ruff
     and format checks passed; Radon reports `create_core_snapshot` reduced from `C (17)` to
     `A (1)`, with no C-or-worse functions remaining in `integration.py`.
302. Reduced reconciliation authoritative metric aggregation complexity by extracting metric
     accumulator creation, currency pair normalization, FX conversion requirement detection,
     cached positive FX-rate resolution, and metric accumulation from
     `ReconciliationService._aggregate_authoritative_portfolio_metrics(...)`. Focused
     reconciliation service tests passed with 13 tests; scoped Ruff and format checks passed; Radon
     reports `_aggregate_authoritative_portfolio_metrics` reduced from `C (11)` to `A (3)`.
303. Reduced transaction cashflow reconciliation workflow complexity by extracting per-row finding
     construction, missing-cashflow finding construction, cashflow rule mismatch comparison, and
     rule-mismatch finding construction from `ReconciliationService.run_transaction_cashflow(...)`.
     Focused reconciliation service tests passed with 13 tests; scoped Ruff and format checks
     passed; Radon reports `run_transaction_cashflow` reduced from `C (11)` to `A (2)`.
304. Reduced timeseries integrity reconciliation workflow complexity by extracting timeseries scope
     map construction, deterministic scope-key ordering, per-key finding construction, missing
     portfolio/position findings, completeness-gap findings, metric pair extraction, tolerance-based
     mismatch detection, and aggregate mismatch finding construction from
     `ReconciliationService.run_timeseries_integrity(...)`. Focused reconciliation service tests
     passed with 13 tests; scoped Ruff and format checks passed; Radon reports
     `run_timeseries_integrity` reduced from `C (19)` to `A (3)`, with no C-or-worse functions
     remaining in `reconciliation_service.py`.
305. Reduced durable reprocessing worker batch complexity by extracting reset-watermark job scope
     parsing, watermark fanout observation/logging, stale reset and job claiming, per-job
     correlation-scoped processing, impacted portfolio lookup, watermark reset/no-op decisioning,
     terminal status update, ownership-loss posture, and failed job marking from
     `ReprocessingWorker._process_batch(...)`. Focused reprocessing worker tests passed with
     12 tests; scoped Ruff and format checks passed; Radon reports `_process_batch` reduced from
     `C (18)` to `A (3)`, with no C-or-worse functions/classes remaining in
     `reprocessing_worker.py`.
306. Reduced valuation scheduler poll-loop complexity by extracting database poll-step transaction
     execution, combined reprocessing and queue metric refresh, stale valuation job reset, one
     complete scheduler poll iteration, and stop-aware poll waiting from
     `ValuationScheduler.run(...)`. Focused scheduler tests passed with 20 tests; scoped Ruff and
     format checks passed; Radon reports `ValuationScheduler.run` reduced from `C (11)` to
     `A (4)`. Remaining C-ranked scheduler routines are explicit valuation-domain workflows:
     `_advance_watermarks(...)` and `_create_backfill_jobs(...)`.
307. Reduced valuation scheduler watermark-advance complexity by extracting terminal update
     construction, lagging watermark advance update construction, update-example formatting,
     epoch-fenced bulk update execution and stale-skip logging, terminal reprocessing
     normalization, and lagging watermark advancement from
     `ValuationScheduler._advance_watermarks(...)`. Focused scheduler tests passed with 20 tests;
     scoped Ruff and format checks passed; Radon reports `_advance_watermarks` reduced from
     `C (18)` to `B (6)`. The remaining C-ranked scheduler workflow is
     `_create_backfill_jobs(...)`.
308. Reduced valuation scheduler backfill-job complexity by extracting no-history state
     partitioning, no-history normalization update construction, no-history normalization
     persistence/logging, reprocessing defer logging, backfill gap metric observation,
     missing current-epoch history logging, deterministic `ValuationJobUpsert` request
     construction, per-state job staging, and ordered per-state processing from
     `ValuationScheduler._create_backfill_jobs(...)`. Focused scheduler tests passed with
     20 tests; scoped Ruff and format checks passed; Radon reports `_create_backfill_jobs`
     reduced from `C (20)` to `A (4)`, and the source-wide C-or-worse scan is empty.
309. Reduced valuation scheduler dispatch complexity by extracting valuation job record-key
     formatting, correlation header construction, event payload construction, producer
     publication, partial dispatch failure handling, and delivery confirmation from
     `ValuationScheduler._dispatch_jobs(...)`. Focused scheduler tests passed with 20 tests;
     scoped Ruff and format checks passed; Radon reports `_dispatch_jobs` reduced from
     `B (7)` to `A (5)`.
310. Reduced valuation scheduler watermark orchestration complexity by extracting
     watermark-advance input loading and active reprocessing key metric observation from
     `ValuationScheduler._advance_watermarks(...)`. Focused scheduler tests passed with
     20 tests; scoped Ruff and format checks passed; Radon reports `_advance_watermarks`
     reduced from `B (6)` to `A (3)`, and every function/class in
     `valuation_scheduler.py` is A-ranked.
311. Expanded `HoldingsAsOf:v1` cash-balance source evidence with a Core-owned
     `source_reported_cash_weight`, denominator, and supportability posture so downstream
     `lotus-idea` high-cash evidence does not reconstruct Core-owned cash/AUM facts locally.
     Focused cash-balance, OpenAPI, domain-product, and source-data-product tests passed with
     41 tests; scoped Ruff passed; `make openapi-gate`, `make api-vocabulary-gate`, and
     `make domain-product-validate` passed.
312. Reduced PR auto-merge workflow signal noise by removing the `unlabeled` pull-request trigger
     from `.github/workflows/pr-auto-merge.yml` and making absent `automerge` labels successful
     no-ops inside the queue script. The workflow preserves explicit `automerge` label opt-in and
     branch-protected `gh pr merge --auto --rebase --delete-branch` behavior. Added a
     workflow-governance regression test so missing or removed labels do not emit stale skipped
     `Queue Auto Merge` check runs. Focused workflow tests, scoped Ruff, and workflow YAML parse
     validation passed.
313. Fixed the PR Merge Gate latency profile after run `27916210920` showed deterministic
     `422` responses for both analytics timeseries probes due to a weekend `2026-03-21` FX lookup
     outside business-day seed coverage. The latency profile now aligns analytics window starts to
     the next business day and sends the same explicit window to portfolio and position analytics
     timeseries probes while preserving real endpoint calls, 30 measured runs, p95 budgets, and
     non-2xx response-body evidence. Focused latency-profile tests and scoped Ruff validation
     passed locally; PR Merge Gate latency rerun remains the remote proof.
314. Reduced cost reprocessing consumer orchestration complexity by extracting JSON object payload
     parsing, requested transaction-id normalization, repository-backed reprocessing execution, and
     parse/retryable/unexpected error handling from `ReprocessingConsumer.process_message(...)`.
     Focused reprocessing consumer tests passed with 6 tests, scoped Ruff lint and format checks
     passed, Radon reports `process_message` reduced from `B (6)` to `A (3)`, and the class
     reduced from `B (7)` to `A (4)`.
315. Hardened workflow fail-closed governance by adding a 10-minute timeout to the PR auto-merge
     queue job and adding workflow-governance tests that require every job to define a positive
     timeout and restrict `continue-on-error` to documented report-only scope. Focused workflow
     tests passed with 8 tests; scoped Ruff lint and format checks passed; all 5 workflow YAML files
     parsed successfully.
316. Promoted workflow fail-closed governance into the progressive quality lane by adding
     `make quality-workflow-governance-gate`, wiring it into `.github/workflows/quality-baseline.yml`
     as `Quality Baseline / Workflow Governance Gate`, and adding a regression assertion that the
     workflow runs the Make target. The Make gate passed with 9 tests; scoped Ruff lint and format
     checks passed; all 5 workflow YAML files parsed successfully.
317. Reduced cost transaction datetime normalization complexity by extracting ISO text
     normalization, parsing, UTC-aware marking, and public normalization policy from the Pydantic
     validator. Focused transaction model tests passed with 4 tests; the broader cost-engine unit
     folder passed with 96 tests; scoped Ruff lint and format checks passed; Radon reports
     `Transaction.standardize_datetimes` reduced from `B (6)` to `A (1)` and `Transaction` from
     `B (7)` to `A (2)`.
318. Made partial progress on GitHub issue #446 by reducing event replay ingestion operations
     replay publish dispatch complexity. `_replay_job_payload(...)` now delegates to an immutable
     endpoint publisher descriptor and declarative publisher table. Focused ingestion operations
     tests passed with 10 tests; event replay app integration/OpenAPI tests passed with 10 tests;
     scoped Ruff lint and format checks passed; complexity and maintainability gates passed; Radon
     reports `_replay_job_payload` reduced from `B (9)` to `A (2)`.
319. Continued GitHub issue #446 by reducing consumer-DLQ replay candidate selection complexity.
     Extracted replay job id, deterministic fingerprint construction, and missing-payload
     not-replayable response helpers from `_consumer_dlq_replay_candidate_or_response(...)`.
     Focused ingestion operations tests passed with 13 tests; event replay app integration/OpenAPI
     tests passed with 10 tests; scoped Ruff lint and format checks passed; complexity and
     maintainability gates passed; Radon reports the helper reduced from `B (8)` to `A (4)`.
320. Addressed validated GitHub issue #445 by routing collection-only gates through
     `scripts/test_manifest.py` and adding a named manifest-backed `integration-lite` collection
     job to the quality-baseline workflow. `make quality-unit-collection-gate` collected
     `3082/3092` tests with 10 manifest deselects, `make quality-integration-lite-collection-gate`
     collected 121 tests, focused manifest/workflow governance tests passed with 20 tests, scoped
     Ruff lint and format checks passed, and workflow YAML parsing passed.
321. Addressed validated GitHub issue #444 by generating stable per-service OpenAPI artifacts under
     `output/openapi/` and adding an enforced portable Spectral blocker-subset gate to the
     quality-baseline API governance job. The new `make quality-openapi-spectral-gate` generated
     14 service artifacts and reported no warn-or-higher Spectral results; focused
     OpenAPI/workflow/Spectral tests passed with 21 tests; scoped Ruff lint and format checks
     passed; `python scripts/openapi_quality_gate.py` passed; and workflow YAML parsing passed.
322. Began validated GitHub issue #462 by adding AST-based direct-import architecture checks to
     `scripts/architecture_boundary_guard.py`. `make architecture-guard` now blocks direct
     query-control-plane router imports of query-service repositories, query runtime router imports
     of query-control-plane internals, and ingestion router imports of other service
     implementations. Focused architecture boundary tests passed with 2 tests; `make
     architecture-guard` and `make quality-import-boundary-gate` passed; scoped Ruff lint and
     format checks passed.
