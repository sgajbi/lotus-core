# DIVIDEND Slice 4 - Cash-Entry Mode and Linkage Accounting

## Scope
Slice 4 implements the dual cash-entry mode requirement for `DIVIDEND` without introducing dedicated endpoints:
1. `AUTO` mode: service-managed cashflow generation remains the default path.
2. `EXTERNAL` mode: upstream cash entry is authoritative, and calculator flow enforces explicit linkage.

This slice focuses on deterministic linkage semantics and replay-safe behavior. Withholding/ROC decomposition remains reserved for subsequent extension on top of this linkage contract.

## Implemented Changes
1. Canonical mode helpers in `portfolio_common.transaction_domain.cash_entry_mode`:
 - `normalize_cash_entry_mode`
 - `is_external_cash_entry_mode`
 - constants for supported modes (`AUTO`, `EXTERNAL`)
2. Canonical DIVIDEND metadata enrichment now defaults `cash_entry_mode` to `AUTO`.
3. Canonical DIVIDEND validation now enforces:
 - when `cash_entry_mode == EXTERNAL`, `external_cash_transaction_id` is required (`DIVIDEND_011_MISSING_EXTERNAL_CASH_LINK`).
4. Event and persistence contracts now carry:
 - `cash_entry_mode`
 - `external_cash_transaction_id`
5. Cashflow calculator consumer behavior:
 - `DIVIDEND + AUTO`: existing cashflow rule path unchanged.
 - `DIVIDEND + EXTERNAL`:
   - requires `external_cash_transaction_id`;
   - skips auto cashflow creation;
   - marks idempotency as processed;
   - emits DLQ error on missing linkage id.
6. Alembic migration adds transaction columns and index:
 - `transactions.cash_entry_mode`
 - `transactions.external_cash_transaction_id`
 - index on `external_cash_transaction_id`

## Deterministic Behavior Contract
1. Missing/unknown mode input normalizes to `AUTO`.
2. External mode is explicit and cannot silently fall back when a linkage id is absent.
3. Replay of already-processed external-mode events remains idempotent through processed-event marking.
4. Existing BUY/SELL behavior is unchanged.

## Test Evidence
1. Unit: cash-entry mode normalization and classification.
2. Unit: DIVIDEND linkage enrichment defaults/preservation including mode fields.
3. Unit: DIVIDEND validation enforcement for external linkage id.
4. Unit: cashflow consumer external-mode skip path and DLQ failure path.
5. Unit: ingestion DTO acceptance for mode/link fields.
6. Integration: transaction repository UPSERT persists and updates mode/link fields.

## Shared-Doc Conformance Note
1. `07-accounting-cash-and-linkage.md`:
 - dual cash-entry mode behavior implemented with deterministic linkage requirement.
2. `09-idempotency-replay-and-reprocessing.md`:
 - external mode branch marks processed-event state, preserving replay safety.
3. `10-query-audit-and-observability.md`:
 - mode/link fields propagated into event + DTO + persistence contracts for traceability.

## Residual Gaps
1. Withholding-tax and ROC component decomposition fields/identities are not introduced in this slice.
2. Reconciliation reporting surfaces for full income decomposition remain for later slice work.
