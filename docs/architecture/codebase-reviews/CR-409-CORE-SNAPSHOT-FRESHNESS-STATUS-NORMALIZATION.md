# CR-409: Core Snapshot Freshness Status Normalization

Date: 2026-05-28

## Scope

`PortfolioStateSnapshot` data-quality classification in `CoreSnapshotService`.

## Finding

Core snapshot freshness status is a control-code field used to decide whether a snapshot is
complete, partial, or unknown. The classifier compared raw status strings to
`CURRENT_SNAPSHOT` and `HISTORICAL_FALLBACK`. Padded or case-varied values could therefore miss
the intended branch and incorrectly downgrade or misclassify snapshot data-quality posture.

## Change

Added a core-snapshot freshness-status normalizer and routed data-quality classification through
it before comparing control-code values. Updated direct unit coverage proving padded lower-case
`current_snapshot` and `historical_fallback` values still classify as complete and partial
respectively when the rest of the evidence supports those states.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/query_service/services/test_core_snapshot_service.py -q`
2. `python -m pytest tests/unit/services/query_service/services -q`
3. `python -m ruff check src/services/query_service/app/services/core_snapshot_service.py tests/unit/services/query_service/services/test_core_snapshot_service.py`

## Closure

Status: Hardened.

No API route, OpenAPI, wiki source, or platform contract change was required. This is an internal
snapshot supportability classification reliability slice.
