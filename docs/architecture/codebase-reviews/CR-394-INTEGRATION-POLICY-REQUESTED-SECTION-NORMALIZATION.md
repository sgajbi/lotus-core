# CR-394: Integration Policy Requested-Section Normalization

Date: 2026-05-28

## Scope

Query-service effective integration policy section filtering.

## Finding

Configured allowed integration-policy sections were normalized with trim plus uppercase, but
requested `include_sections` were only uppercased. Requests carrying padded values such as
` overview ` or ` holdings ` could be filtered out even when `OVERVIEW` or `HOLDINGS` were
allowed by the effective consumer policy.

This affected downstream consumers that depend on effective policy responses to decide which
source-data sections they may request or render.

## Change

Reused `normalize_sections(...)` for requested `include_sections` inside
`build_effective_policy_response(...)`. Updated the effective-policy unit test to prove padded
lower-case requested sections still match configured allowed sections while disallowed sections
remain filtered.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/query_service/services/test_integration_service.py -q`
2. `python -m pytest tests/unit/services/query_service/services -q`
3. `python -m ruff check src/services/query_service/app/services/integration_policy.py tests/unit/services/query_service/services/test_integration_service.py`

## Closure

Status: Hardened.

No API, OpenAPI, wiki source, or platform contract change was required. This is a query-service
integration-policy correctness and downstream source-data product reliability slice.
