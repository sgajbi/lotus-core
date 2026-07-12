# CR-397: Discretionary Mandate Binding Status Normalization

Date: 2026-05-28

## Scope

Query-service `DiscretionaryMandateBinding` source-data product supportability.

## Finding

The discretionary mandate binding supportability check compared
`discretionary_authority_status` with `lower()` but without trimming. A source row carrying a valid
padded value such as ` active ` could therefore be marked `INCOMPLETE` with
`DISCRETIONARY_AUTHORITY_NOT_ACTIVE`. The same path uppercased quality status without trimming,
which could emit padded data-quality metadata.

## Change

Added a small service-level control-code normalizer and used it for discretionary authority status
and mandate-binding data-quality status. The normalized authority status now drives supportability
and is returned as the canonical product control code. Updated direct coverage so a padded
lower-case active mandate remains `READY` with canonical `ACTIVE` authority and `ACCEPTED`
data-quality metadata.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/query_service/services/test_integration_service.py -q`
2. `python -m pytest tests/unit/services/query_service/services -q`
3. `python -m ruff check src/services/query_service/app/services/integration_service.py tests/unit/services/query_service/services/test_integration_service.py`

## Closure

Status: Hardened.

No API route, OpenAPI, wiki source, or platform contract change was required. This is a
source-data product supportability correctness and downstream control-code consistency slice.
