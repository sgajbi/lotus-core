# CR-336 Sell Disposal Base/Local Arithmetic Review

## Scope

Review the downstream-facing `sell-disposals` query contract for figure reconstruction risk.

## Finding

`SellStateService` reconstructs the read model from persisted SELL transaction fields:

1. disposed quantity from absolute SELL quantity,
2. disposed basis from absolute persisted negative `net_cost` fields,
3. net proceeds from `realized_gain_loss - net_cost`.

The service already had a happy-path unit test, but it did not explicitly prove that base-currency
and local-currency arithmetic are handled independently. For cross-currency disposals, that matters:
the base and local figures should not silently collapse into one another or inherit the wrong field.

## Actions Taken

Added a focused unit test that seeds a SELL disposal with different base and local persisted figures
and proves the API response preserves them correctly:

1. `disposal_cost_basis_base`
2. `disposal_cost_basis_local`
3. `realized_gain_loss_base`
4. `realized_gain_loss_local`
5. `net_sell_proceeds_base`
6. `net_sell_proceeds_local`

## Why This Matters

This is a small but real downstream control:

1. front-office and reporting consumers rely on these figures directly,
2. incorrect base/local mapping would undermine disposal economics even if the core persisted state
   was correct,
3. the test now locks the read-model arithmetic to the intended contract.

## Evidence

- `tests/unit/services/query_service/services/test_sell_state_service.py`
- `pytest tests/unit/services/query_service/services/test_sell_state_service.py -q`
