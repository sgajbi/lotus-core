# CR-044 Position, Cashflow, and Valuation Schema Swagger Review

Date: 2026-03-10  
Status: Hardened

## Scope

Shared `query_service` read-model DTO schemas for positions, cashflows, and valuation details.

Reviewed schemas:

- `CashflowRecord`
- `ValuationData`
- `PositionHistoryRecord`
- `PortfolioPositionHistoryResponse`

## Findings

Router-level `query_service` contracts had already been hardened through CR-034 to CR-042, but the
shared component schemas behind positions and cashflow-heavy responses were still relatively thin.
That left Swagger more informative at the endpoint layer than at the actual schema layer used by
client generators and downstream readers.

## Actions Taken

- Added field-level descriptions/examples to `CashflowRecord`.
- Added field-level descriptions/examples to `ValuationData`.
- Tightened position-history field descriptions/examples where the schema was still generic.
- Added an OpenAPI integration assertion to lock the richer component-schema contract in place.

## Follow-up

Continue the same schema-depth pass on the next weakest shared DTO surface after
positions/cashflow/valuation.

## Evidence

- `src/services/query_service/app/dtos/cashflow_dto.py`
- `src/services/query_service/app/dtos/valuation_dto.py`
- `src/services/query_service/app/dtos/position_dto.py`
- `tests/integration/services/query_service/test_main_app.py`
- `python scripts/openapi_quality_gate.py`
- `python scripts/api_vocabulary_inventory.py --validate-only`
