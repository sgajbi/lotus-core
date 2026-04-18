# CR-339 BUY Cash Linkage Policy Metadata Alignment

## Scope

Review downstream contract symmetry between BUY and SELL cash-linkage endpoints.

## Finding

`GET /portfolios/{portfolio_id}/transactions/{transaction_id}/sell-cash-linkage` already exposed
`calculation_policy_id` and `calculation_policy_version`, but the corresponding BUY cash-linkage
route omitted them even though the underlying BUY transaction and other BUY-state contracts already
carried that metadata.

That forced downstream consumers to treat BUY and SELL linkage investigations differently for no
good source-owned reason.

## Actions Taken

Added calculation-policy metadata to `BuyCashLinkageResponse`, wired the fields through
`BuyStateService.get_buy_cash_linkage(...)`, and strengthened unit, router, and OpenAPI tests.

## Why This Matters

This removes an avoidable contract asymmetry on a downstream-facing audit route:

1. BUY and SELL linkage endpoints now expose comparable policy metadata,
2. downstream audit and reconciliation flows do not need route-specific fallback logic just to learn
   which calculation policy produced the persisted linkage,
3. OpenAPI now documents the BUY linkage contract more truthfully.

## Evidence

- `src/services/query_service/app/dtos/buy_state_dto.py`
- `src/services/query_service/app/services/buy_state_service.py`
- `tests/unit/services/query_service/services/test_buy_state_service.py`
- `tests/integration/services/query_service/test_buy_state_router.py`
- `tests/integration/services/query_service/test_main_app.py`
- `pytest tests/unit/services/query_service/services/test_buy_state_service.py -q`
- `pytest tests/integration/services/query_service/test_buy_state_router.py -q`
- `pytest tests/integration/services/query_service/test_main_app.py -k buy_sell_state_contract_examples -q`
