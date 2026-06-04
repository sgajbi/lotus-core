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
| Progressive quality CI | Improving | `.github/workflows/quality-baseline.yml` now has enforced Ruff lint, Ruff format, import boundary, API governance, typecheck, Bandit security, Vulture source dead-code, Deptry source dependency, maintainability, and complexity gates while other baseline checks remain report-only |
| Full test collection | Improving | Import/plugin collection blockers removed; `pytest --collect-only -q` now reaches 3,575 collected tests before the governed mixed-runtime guard stops all-suite collection |
| Lint baseline | Clean | `python -m ruff check . --statistics` reports zero findings |
| Format baseline | Clean | `python -m ruff format --check .` reports 1,070 files already formatted after CR-865 |
| Typecheck baseline | Clean for configured scope | `make typecheck` reports no issues in 42 source files after CR-869 |
| Security baseline | Clean and enforced | Bandit reports 0 findings and is enforced by `make quality-bandit-gate` plus the quality-baseline Bandit security job after CR-875 |
| Production-source dead-code baseline | Clean and enforced | `make quality-vulture-source-gate` reports no high-confidence Vulture findings under production `src` after CR-876 |
| Dependency-usage baseline | Clean and enforced | `make quality-deptry-source-gate` reports no production-source dependency issues after CR-878 |
| Maintainability baseline | No D/E/F modules and enforced | `make quality-maintainability-gate` reports no source modules below C after CR-879; CR-883 removed shared OpenAPI enrichment from the C-ranked hotspot list |
| Complexity baseline | Clean and enforced | CR-880 reduced advisory proposal simulation from F to B, CR-881 reduced the cost-calculator consumer from F to C, and CR-882 reduced FX linkage from D to B; `make quality-complexity-gate` now passes |
| Architecture gates | Improving | Existing `make architecture-guard`; `make quality-import-boundary-gate` now enforces 2 kept import-linter contracts |
| OpenAPI governance | Improving | Existing `make openapi-gate` and `make api-vocabulary-gate` are now enforced in the quality-baseline API governance job; `.spectral.yaml` remains report-only |

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
