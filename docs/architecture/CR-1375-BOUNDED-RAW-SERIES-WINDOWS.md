# CR-1375 Bounded Raw Series Windows

## Objective

Fix GitHub issue #527 for the named unpaginated query-service raw series endpoints by requiring
bounded date windows for market prices, FX rates, and position history, and by documenting latest
holdings as a current HoldingsAsOf book rather than an unbounded history series.

## Changes

- Added `collection_window_policy.py` with a shared ten-year raw-series window limit.
- Required both `start_date` and `end_date` for:
  - `GET /prices/`
  - `GET /fx-rates/`
  - `GET /portfolios/{portfolio_id}/position-history`
- Rejected missing, reversed, and oversized windows with structured HTTP 400 details.
- Enforced the same window policy in services so non-HTTP callers cannot bypass route validation.
- Updated OpenAPI descriptions for raw series endpoints and latest HoldingsAsOf small-cardinality
  semantics.

## Expected Improvement

- Raw market/reference/position series reads no longer allow accidental full-history scans.
- API consumers get a visible max-window contract instead of implicit optional filters.
- Repository calls are protected by service-layer validation before SQL execution.
- Current holdings remains behaviorally compatible while documentation clarifies it is not a
  historical collection endpoint.

## Tests Added

- Policy tests cover accepted ten-year windows, missing bounds, reversed windows, and oversized
  windows.
- Service tests prove unbounded price, FX, and position-history requests fail before repository
  access.
- Router tests prove missing/reversed/oversized windows return structured 400 responses and do not
  call mocked services.
- OpenAPI tests assert bounded-window descriptions and latest HoldingsAsOf current-row semantics.

## Validation Evidence

```powershell
python -m pytest tests/unit/services/query_service/application/test_collection_window_policy.py tests/unit/services/query_service/services/test_price_service.py tests/unit/services/query_service/services/test_fx_rate_service.py tests/unit/services/query_service/services/test_position_service.py::test_get_position_history tests/unit/services/query_service/services/test_position_service.py::test_get_position_history_rejects_missing_window tests/integration/services/query_service/test_reference_data_routers.py::test_get_fx_rates_success_and_uppercase tests/integration/services/query_service/test_reference_data_routers.py::test_get_prices_success tests/integration/services/query_service/test_reference_data_routers.py::test_get_fx_rates_rejects_missing_window tests/integration/services/query_service/test_reference_data_routers.py::test_get_prices_rejects_oversized_window tests/integration/services/query_service/test_reference_data_routers.py::test_get_fx_rates_unexpected_uses_global_500_envelope tests/integration/services/query_service/test_reference_data_routers.py::test_get_prices_unexpected_uses_global_500_envelope tests/integration/services/query_service/test_positions_router_dependency.py::test_get_position_history_success tests/integration/services/query_service/test_positions_router_dependency.py::test_get_position_history_unexpected_maps_to_500 tests/integration/services/query_service/test_positions_router_dependency.py::test_get_position_history_not_found_maps_to_404 tests/integration/services/query_service/test_positions_router_dependency.py::test_get_position_history_rejects_missing_window tests/integration/services/query_service/test_positions_router_dependency.py::test_get_position_history_rejects_reversed_window tests/integration/services/query_service/test_main_app.py::test_openapi_describes_reference_market_data_contract_examples tests/integration/services/query_service/test_main_app.py::test_openapi_describes_position_contract_examples -q
python -m ruff check src/services/query_service/app/application/collection_window_policy.py src/services/query_service/app/routers/http_errors.py src/services/query_service/app/routers/prices.py src/services/query_service/app/routers/fx_rates.py src/services/query_service/app/routers/positions.py src/services/query_service/app/services/price_service.py src/services/query_service/app/services/fx_rate_service.py src/services/query_service/app/services/position_service.py tests/unit/services/query_service/application/test_collection_window_policy.py tests/unit/services/query_service/services/test_price_service.py tests/unit/services/query_service/services/test_fx_rate_service.py tests/unit/services/query_service/services/test_position_service.py tests/integration/services/query_service/test_reference_data_routers.py tests/integration/services/query_service/test_positions_router_dependency.py tests/integration/services/query_service/test_main_app.py
```

Final API, architecture, docs, typecheck, and diff checks are recorded in the issue comment before
commit.

## Downstream Compatibility Impact

Intentional behavior change: the raw series endpoints now reject missing, incomplete, reversed, or
larger-than-ten-year windows with HTTP 400 instead of returning unbounded arrays. Valid bounded
windows preserve existing route paths, response DTOs, repository query semantics, ordering,
database schema, source-data metadata, and runtime topology. Latest positions remain compatible and
continue returning the current HoldingsAsOf book for the resolved as-of scope.

## Same-Pattern Scan

The named query-service unpaginated series endpoints are now bounded. Instrument and portfolio
lookups already have explicit `limit` controls. Transaction and instrument list reads already use
offset pagination. Maturity summary has a bounded `horizon_days` limit. Operations and event-replay
list-style endpoints generally expose explicit `limit`, `lookback_hours`, or support-filter
controls and remain a separate operations API governance review surface if a future issue finds an
unbounded support diagnostic path.

## Docs, Context, And Skill Decision

- Codebase review ledger updated with #527 closure evidence.
- Repository context updated with the raw-series bounded-window rule.
- API governance docs updated to require pagination, bounded windows, or explicit
  small-cardinality proof for collection endpoints.
- No wiki update is required because the public navigation did not change; OpenAPI is the
  consumer-facing query-parameter contract.
- No platform skill update is required: existing backend delivery and issue-fix skills already
  require same-pattern scans and durable context updates.
