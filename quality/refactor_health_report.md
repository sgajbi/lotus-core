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
| Report-only quality CI | Started | `.github/workflows/quality-baseline.yml` |
| Full test collection | Improving | Import/plugin collection blockers removed; `pytest --collect-only -q` now reaches 3,575 collected tests before the governed mixed-runtime guard stops all-suite collection |
| Lint baseline | Improving | 323 ruff findings remain; unused-symbol subset is clean |
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
