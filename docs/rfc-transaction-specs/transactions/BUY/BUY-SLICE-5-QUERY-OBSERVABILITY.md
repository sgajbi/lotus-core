# BUY Slice 5 - Query Surfaces and Lifecycle Observability

## Scope Implemented

- Added BUY lot query API surface.
- Added BUY accrued-income offset query API surface.
- Added BUY cash-linkage query API surface.
- Added BUY lifecycle stage metrics and structured lifecycle logs in the cost-calculator flow.

## New Query APIs

- `GET /portfolios/{portfolio_id}/positions/{security_id}/lots`
- `GET /portfolios/{portfolio_id}/positions/{security_id}/accrued-offsets`
- `GET /portfolios/{portfolio_id}/transactions/{transaction_id}/cash-linkage`

These endpoints expose durable state produced by Slice 4 and support supportability/reconciliation use cases.

## Exact Lot Quantity Wire Contract

The current lots route returns `original_quantity` and `open_quantity` as JSON decimal
strings, matching its existing exact cost fields. The source is `PositionLotState`'s
`NUMERIC(18,10)` values; the service and `PositionLotRecord` preserve Decimal values through
registered response serialization. For example, `"12345678.1234567890"` is exact, and
`"99999999.9999999998"` remains distinct from `"99999999.9999999999"`. Zero and closed lots
remain visible. Decimal notation can include an exponent (for example `"0E-10"`); consumers
must compare parsed decimal values rather than assume a fixed number of displayed places.

This intentionally corrects the former JSON number representation on the same route. Direct
consumers that require numeric JSON tokens must update their parser to accept decimal strings
before adopting this response. Parse them directly with an exact decimal type; converting via
binary float or JavaScript `Number` loses information. No rounding fallback or parallel legacy
quantity fields are provided. OpenAPI response properties and examples publish the string type.
Gateway's current `PortfolioTaxLot` consumer already uses Decimal quantities and emits strings;
its lot response builder preserves this representation. The dated `PortfolioTaxLotWindow` source
product is a separate contract and is unchanged by this operational audit-route correction.

Portfolio ownership is checked before the lot read. Foreign portfolios and empty lot state retain
404 responses. Lot identity, acquisition date, local/base cost, accrued interest and published
event/group/policy/source lineage remain unchanged. The regression proof uses synthetic persisted
PostgreSQL rows and registered in-process HTTP; it does not certify ingestion, live network,
production authorization, or bank readiness.

## Observability Additions

- Prometheus counter:
  - `buy_lifecycle_stage_total{stage,status}`
- Stage instrumentation in cost calculator for:
  - transaction cost persistence
  - lot-state persistence
  - accrued-offset-state persistence
  - outbox emission
- Structured `buy_state_persisted` log event with linkage/policy metadata.

## Governance

- OpenAPI quality gate passed.
- API vocabulary inventory regenerated for `lotus-core`.
- Platform catalog sync + cross-app validator passed in `lotus-platform`.
