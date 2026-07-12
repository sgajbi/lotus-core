# CR-338 SELL State OpenAPI Field Documentation Proof

## Scope

Review Swagger/OpenAPI quality for the downstream-facing SELL-state endpoints.

## Finding

The route-level SELL-state descriptions were already explicit about when to use the endpoints and
when not to use them, but the automated OpenAPI proof did not yet lock the schema-level field
descriptions and examples for the main SELL disposal and cash-linkage payloads.

## Actions Taken

Extended the query-service OpenAPI integration proof to assert schema-level descriptions and
examples for:

1. `SellDisposalRecord.disposal_cost_basis_base`
2. `SellDisposalRecord.net_sell_proceeds_local`
3. `SellDisposalRecord.realized_gain_loss_local`
4. `SellDisposalRecord.source_system`
5. `SellCashLinkageResponse.cashflow_amount`
6. `SellCashLinkageResponse.cashflow_classification`

## Why This Matters

This keeps the route self-explanatory for downstream teams:

1. route descriptions explain when to use the endpoints,
2. field-level schema assertions keep the per-attribute contract readable and stable,
3. downstream generators and human consumers now have explicit proof that the SELL-state payload
   remains fully described rather than only discoverable through code.

## Evidence

- `tests/integration/services/query_service/test_main_app.py`
- `pytest tests/integration/services/query_service/test_main_app.py -k buy_sell_state_contract_examples -q`
