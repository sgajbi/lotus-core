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
| Progressive quality CI | Started | `.github/workflows/quality-baseline.yml` now has an enforced Ruff regression gate while other baseline checks remain report-only |
| Full test collection | Improving | Import/plugin collection blockers removed; `pytest --collect-only -q` now reaches 3,575 collected tests before the governed mixed-runtime guard stops all-suite collection |
| Lint baseline | Clean | `python -m ruff check . --statistics` reports zero findings |
| Format baseline | Improving | `python -m ruff format --check .` reports 40 files remaining after CR-863 |
| Architecture gates | Existing plus new scaffold | Existing `make architecture-guard`; new `.importlinter` scaffold |
| OpenAPI governance | Existing plus new scaffold | Existing `make openapi-gate`; new `.spectral.yaml` scaffold |

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
