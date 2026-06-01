# lotus-core Refactor Health Report

Status: Initial health scaffold on 2026-06-02.

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
| Full test collection | Not clean | 3 collection errors in `pytest --collect-only -q` |
| Lint baseline | Known debt | 344 ruff findings |
| Architecture gates | Existing plus new scaffold | Existing `make architecture-guard`; new `.importlinter` scaffold |
| OpenAPI governance | Existing plus new scaffold | Existing `make openapi-gate`; new `.spectral.yaml` scaffold |

## Health Assessment

`lotus-core` is not yet bank-buyable as a whole. It has strong existing governance machinery and
many domain-specific contracts, but the updated goal requires measurable quality evidence,
progressive CI gates, complete API/documentation posture, security posture, and full-suite test
health before that claim is defensible.
