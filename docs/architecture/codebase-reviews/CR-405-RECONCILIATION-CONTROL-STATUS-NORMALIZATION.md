# CR-405: Reconciliation Control Status Normalization

Date: 2026-05-28

## Scope

Query-service reconciliation operational-state, portfolio-control-stage blocking, and
reconciliation-finding blocking classifiers.

## Finding

Reconciliation and portfolio-control supportability classifiers compared raw control status and
finding severity values. Padded valid values such as ` failed `, ` requires_replay `, ` running `,
or ` error ` could miss blocking or running branches and make operator surfaces understate active
control remediation.

## Change

Routed reconciliation run status, portfolio-control stage status, and reconciliation finding
severity checks through the existing trim-plus-uppercase operations status normalizer before branch
classification. Updated direct operations-service tests proving padded lower-case control statuses
and severities still classify correctly.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/query_service/services/test_operations_service.py -q`
2. `python -m pytest tests/unit/services/query_service/services -q`
3. `python -m ruff check src/services/query_service/app/services/operations_service.py tests/unit/services/query_service/services/test_operations_service.py`

## Closure

Status: Hardened.

No API route, OpenAPI, wiki source, or platform contract change was required. This is an internal
operations supportability classification and control-remediation reliability slice.
