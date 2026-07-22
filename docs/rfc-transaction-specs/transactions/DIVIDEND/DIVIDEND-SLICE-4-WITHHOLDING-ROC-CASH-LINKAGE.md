# DIVIDEND Slice 4 - Cash-Entry Mode and Linkage Accounting

## Scope
Slice 4 implements the dual cash-entry mode requirement for `DIVIDEND` without introducing dedicated endpoints:
1. `AUTO_GENERATE` mode: service-managed cashflow generation remains the default path.
2. `UPSTREAM_PROVIDED` mode: upstream cash entry is authoritative, and calculator flow enforces explicit linkage.

This slice originally focused on deterministic linkage semantics and replay-safe behavior. The
subsequent bounded #448 extension now consumes the existing source-recorded
`withholding_tax_amount` field for current DIVIDEND settlement. ROC decomposition remains reserved
for later policy work on top of this linkage contract.

## Implemented Changes
1. Canonical mode helpers in `portfolio_transaction_processing_service.app.domain.transaction.settlement.cash_entry`:
 - `normalize_cash_entry_mode`
 - `is_upstream_provided_cash_entry_mode`
 - constants for supported modes (`AUTO_GENERATE`, `UPSTREAM_PROVIDED`)
2. Canonical DIVIDEND metadata enrichment now defaults `cash_entry_mode` to `AUTO_GENERATE`.
3. Canonical DIVIDEND validation now enforces:
 - when `cash_entry_mode == UPSTREAM_PROVIDED`, `external_cash_transaction_id` is required (`DIVIDEND_011_MISSING_EXTERNAL_CASH_LINK`).
4. Event and persistence contracts now carry:
 - `cash_entry_mode`
 - `external_cash_transaction_id`
5. Cashflow calculator consumer behavior:
 - `DIVIDEND + AUTO_GENERATE`: existing cashflow rule path unchanged.
 - `DIVIDEND + UPSTREAM_PROVIDED`:
   - requires `external_cash_transaction_id`;
   - skips auto cashflow creation;
   - marks idempotency as processed;
   - emits DLQ error on missing linkage id.
6. Alembic migration adds transaction columns and index:
 - `transactions.cash_entry_mode`
 - `transactions.external_cash_transaction_id`
 - index on `external_cash_transaction_id`
7. Current-booking settlement now derives cash as
   `gross_transaction_amount - withholding_tax_amount - resolved transaction fee`.
   Negative withholding, withholding above gross, and non-positive resulting cash fail closed with
   `DIVIDEND_014`, `DIVIDEND_015`, and `DIVIDEND_013` reason codes respectively. Existing nullable
   event/database/query fields are reused; this extension adds no migration or public field.

## Deterministic Behavior Contract
1. Missing/unknown mode input normalizes to `AUTO_GENERATE`.
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
1. Source-recorded withholding amount is preserved and consumed, but withholding-rate derivation,
   tolerance policy, other receipt deductions, and a separately supplied net-dividend identity are
   not introduced in this slice.
2. ROC component identity, classification, and basis-reduction policy remain unimplemented.
3. Reconciliation reporting surfaces for full income/ROC decomposition remain for later work.

