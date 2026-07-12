# CR-404: Reprocessing Lineage Status Normalization

Date: 2026-05-28

## Scope

Query-service operations reprocessing-key stale classification, reprocessing operational state,
lineage artifact-gap detection, and lineage operational-state classification.

## Finding

Reprocessing and lineage supportability classifiers still compared raw status values after the
support-job status normalizer existed. Padded valid values such as ` reprocessing ` or ` failed `
could miss stale-reprocessing, replaying, artifact-gap, or valuation-blocked branches and make
operator supportability surfaces look current or healthy when replay or valuation remediation was
still required.

## Change

Routed reprocessing-key stale detection, reprocessing operational-state classification, lineage
artifact-gap status checks, and lineage operational-state classification through the same
trim-plus-uppercase status normalizer used by support jobs. Updated direct operations-service tests
to prove padded lower-case reprocessing and valuation statuses still classify into the correct
operator states.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/query_service/services/test_operations_service.py -q`
2. `python -m pytest tests/unit/services/query_service/services -q`
3. `python -m ruff check src/services/query_service/app/services/operations_service.py tests/unit/services/query_service/services/test_operations_service.py`

## Closure

Status: Hardened.

No API route, OpenAPI, wiki source, or platform contract change was required. This is an internal
operations supportability classification and replay-readiness reliability slice.
