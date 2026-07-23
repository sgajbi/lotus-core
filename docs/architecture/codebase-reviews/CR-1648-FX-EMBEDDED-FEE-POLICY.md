# CR-1648: FX Embedded-Fee Currency And Signed Cash-Leg Policy

## Scope

Review and harden FX spot, forward, swap, and cash-settlement fee economics under issue #754.

## Finding

Canonical FX models required two positive currency amounts but did not identify a currency or
charged leg for an embedded transaction fee. Generic cashflow code subtracted the resolved fee and
then applied absolute-value FX buy/sell signing. A fee below, equal to, or above a cash leg could
therefore alter or reverse the intermediate amount while still producing an apparently valid signed
flow. RFC 082 recommended separate linked charges, but the canonical FX specification still allowed
embedded netting.

## Decision

Phase-1 policy is `SEPARATE_LINKED_ONLY`:

1. absent and zero inline fees preserve current FX economics;
2. every non-zero resolved aggregate or component fee fails with
   `FX_025_NON_ZERO_EMBEDDED_FEE` before persistence, cost mutation, or cashflow signing;
3. supported `FEE`/`TAX` transactions retain the FX `economic_event_id` and
   `linked_transaction_group_id`, plus deal/contract identity where applicable;
4. a future embedded-fee mode requires a versioned contract defining fee currency, charged leg,
   reconciliation treatment, and downstream accounting. No field is inferred from `currency`.

## Implementation

- Canonical FX construction resolves optional fee evidence through the shared transaction-fee
  policy without widening the required `FxTransactionSource` protocol.
- Direct validation, foreign-exchange booking, cost-basis processing, and generated FX cashflow
  calculation use the same stable reason code.
- Cashflow rejects before classification signing, so `abs()` cannot repair an invalid intermediate
  amount.
- A dedicated DB-direct manifest test replays a zero-fee FX buy and a distinct linked fee, verifies
  group partitioning and linkage retention, proves independent `+110000` and `-25` cashflows, and
  rejects duplicate delivery without double count.

## Compatibility And Contract Impact

- No API/OpenAPI shape or vocabulary field changed.
- No event schema/version changed; existing linkage and fee fields are reused.
- No database schema or migration changed.
- No Docker resource or runtime topology changed.
- Malformed and negative source fee evidence retains the shared fee resolver's existing failure.

## Evidence

- signed implementation commit `64fa44f85f0baf595d260db21100c688e118a33c`;
- signed lifecycle-test commit `dc7e9cebfb5289dee593452e82bcd9d165e0587e`;
- focused direct/booking/cost/cashflow proof: 171 warning-strict tests passed;
- repository-native FX manifest before the new DB case: 337 warning-strict tests passed;
- current governed FX manifest: 338 tests collected, including one dedicated DB-direct linked-fee
  replay test;
- complete repository lint, strict MyPy across 237 source files, architecture, OpenAPI, and API
  vocabulary gates passed;
- touched Ruff, format, and diff hygiene passed.

Protected DB execution, peer review, PR/main/exact-main proof, wiki publication, and verified issue
closure remain pending.
