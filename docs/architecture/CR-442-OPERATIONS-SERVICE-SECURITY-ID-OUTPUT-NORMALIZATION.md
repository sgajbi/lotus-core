# CR-442: Operations Service Security-ID Output Normalization

Date: 2026-05-28

## Scope

Query-service operations service DTO assembly for lineage, support jobs, reprocessing, and
reconciliation evidence.

## Finding

Repository predicates now normalize security identifiers, but several operations service response
builders still copied `security_id` values directly from ORM objects or repository rows. If a
source row carried padding, operator-facing DTOs could still expose non-canonical identifiers even
after the query found the correct evidence.

That is an operational evidence quality risk because support dashboards and drilldowns should
present one canonical security identity across valuation, replay, lineage, and reconciliation
flows.

## Change

Reused the shared query-service security identifier normalizer in operations service DTO assembly.
Lineage key records, direct lineage responses, support-job records, reconciliation finding records,
and reprocessing key records now emit canonical security identifiers.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/query_service/services/test_operations_service.py -q`
2. `python -m ruff check src/services/query_service/app/services/operations_service.py tests/unit/services/query_service/services/test_operations_service.py`
3. `python -m pytest tests/unit/services/query_service/repositories -q`
4. `python -m pytest tests/unit/services/query_service/services -q`
5. `git diff --check`

## Closure

Status: Hardened.

No API route, OpenAPI, wiki source, or platform contract change was required. This is an
operator-facing DTO hardening slice that keeps supportability responses aligned to canonical
security identity after repository-level lookup normalization.
