# CR-1648: FX Embedded-Fee Currency And Signed Cash-Leg Policy

## Scope

Review and harden FX spot, forward, swap, and cash-settlement charge economics under issue #754.

## Finding

Canonical FX models required two positive currency amounts but did not identify a currency or
charged leg for an embedded transaction fee. Generic cashflow code subtracted the resolved fee and
then applied absolute-value FX buy/sell signing. A fee below, equal to, or above a cash leg could
therefore alter or reverse the intermediate amount while still producing an apparently valid signed
flow. RFC 082 recommended separate linked charges, but the canonical FX specification still allowed
embedded netting. Exact-head review also found that a source exposing both an aggregate fee and a
structured fee object could mask non-zero components behind an inconsistent zero aggregate. Peer
review then found the same unsupported inline-charge pattern in `withholding_tax_amount`.
Late PR review found a second representation gap in replay and repair: persisted FX cash legs retain
the business `transaction_type` (`FX_SPOT`, `FX_FORWARD`, or `FX_SWAP`) and identify the settlement
leg through `component_type`. Although application rule resolution used that effective component,
the domain cashflow calculator re-read the broader business type and could bypass the charge fence.

## Decision

Phase-1 policy is `SEPARATE_LINKED_ONLY`:

1. absent and zero inline fees and withholding taxes preserve current FX economics;
2. every non-zero resolved aggregate or component fee fails with
   `FX_025_NON_ZERO_EMBEDDED_FEE` before persistence, cost mutation, or cashflow signing;
3. every non-zero inline `withholding_tax_amount` fails at the same boundaries with
   `FX_026_NON_ZERO_EMBEDDED_TAX`;
4. supported `FEE`/`TAX` transactions retain the FX `economic_event_id` and
   `linked_transaction_group_id`, plus deal/contract identity where applicable;
5. a future embedded-charge mode requires a versioned contract defining charge currency, charged leg,
   reconciliation treatment, and downstream accounting. No field is inferred from `currency`.

## Implementation

- Canonical FX construction resolves optional fee evidence through the shared transaction-fee
  policy without widening the required `FxTransactionSource` protocol. Aggregate and component
  representations are inspected independently so an inconsistent zero value cannot mask a
  non-zero value in the other representation.
- Direct validation, foreign-exchange booking, cost-basis processing, and generated FX cashflow
  calculation use stable, charge-specific reason codes.
- Cashflow rejects before classification signing, so `abs()` cannot repair an invalid intermediate
  amount.
- The application passes its validated effective processing type into the domain calculator. The
  calculator uses that type consistently for date, economics, signing, and embedded-charge policy,
  while direct callers that have no component-level type retain the existing default behavior.
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
- signed exact-head review fix `33b211a88073ba623d46e0682443c6b7a5ead0f4`;
- signed lifecycle-test commit `dc7e9cebfb5289dee593452e82bcd9d165e0587e`;
- signed peer-review withholding-tax fix `6111460b4ab0a54227ce005c8d15068d55e809a8`;
- focused direct/booking/cost/cashflow proof: 200 warning-strict tests passed;
- expanded ordinary-settlement compatibility proof: 295 warning-strict tests passed;
- repository-native FX manifest before the new DB case: 337 warning-strict tests passed;
- current governed FX manifest: 358 tests passed, including one dedicated DB-direct linked-fee
  replay test and the effective-component replay/repair regressions;
- complete repository lint, strict MyPy across 237 source files, architecture, OpenAPI, and API
  vocabulary gates passed;
- touched Ruff, format, and diff hygiene passed.
- focused effective-component calculation plus application replay/repair proof: 89 warning-strict
  tests passed.

Protected DB execution, peer review, PR/main/exact-main proof, wiki publication, and verified issue
closure remain pending.
