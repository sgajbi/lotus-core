# CR-189 - Portfolio Control Stage Support Listing Review

Date: 2026-03-13

## Problem

The support plane exposed control truth only indirectly through the portfolio overview:

- latest control business date
- latest control epoch
- latest control status
- blocking/publish flags

That was not enough for real operational work. Operators could not inspect the durable
portfolio-day control rows over time, filter them by stage/date/status, or verify exactly
which control stage instance was blocking publication.

## Change

Added a first-class support listing for durable portfolio-day control rows:

- `GET /support/portfolios/{portfolio_id}/control-stages`

The support plane now exposes:

- stage name
- business date
- epoch
- status
- last source event type
- updated timestamp
- derived blocking truth
- derived operational state

The repository filters control rows explicitly using the portfolio-stage transaction id
prefix and orders them by operator severity before business date / epoch recency.

## Why this is better

- Operators can inspect portfolio-day control history directly instead of inferring it from
  one latest-status aggregate.
- Blocking control rows are now visible and filterable as first-class support objects.
- The support listing uses the same blocking semantics already used by the portfolio
  overview, so clients do not have to re-derive control meaning.

## Evidence

- `src/services/query_service/app/dtos/operations_dto.py`
- `src/services/query_service/app/repositories/operations_repository.py`
- `src/services/query_service/app/services/operations_service.py`
- `src/services/query_control_plane_service/app/routers/operations.py`
- `tests/unit/services/query_service/repositories/test_operations_repository.py`
- `tests/unit/services/query_service/services/test_operations_service.py`
- `tests/integration/services/query_control_plane_service/test_operations_router_dependency.py`
- `tests/integration/services/query_control_plane_service/test_control_plane_app.py`
