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
| Progressive quality CI | Improving | `.github/workflows/quality-baseline.yml` now has enforced Ruff lint, Ruff format, import boundary, API governance, and typecheck gates while other baseline checks remain report-only |
| Full test collection | Improving | Import/plugin collection blockers removed; `pytest --collect-only -q` now reaches 3,575 collected tests before the governed mixed-runtime guard stops all-suite collection |
| Lint baseline | Clean | `python -m ruff check . --statistics` reports zero findings |
| Format baseline | Clean | `python -m ruff format --check .` reports 1,070 files already formatted after CR-865 |
| Typecheck baseline | Clean for configured scope | `make typecheck` reports no issues in 42 source files after CR-869 |
| Security baseline | Improving but not clean | Bandit reports 11 findings after CR-872: 0 low, 11 medium, 0 high |
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
