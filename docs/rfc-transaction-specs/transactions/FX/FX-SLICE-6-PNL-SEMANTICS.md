# FX Slice 6 - Realized P&L Baseline Semantics

## Scope
This slice establishes deterministic baseline realized-P&L behavior for FX rows before advanced cash-lot treatment is introduced.

## Delivered
1. FX baseline processing path now persists FX rows without routing them through the generic BUY/SELL cost engine.
2. `fx_realized_pnl_mode = NONE`:
 - realized capital P&L local/base = `0`
 - realized FX P&L local/base = `0`
 - realized total P&L local/base = `0`
3. `fx_realized_pnl_mode = UPSTREAM_PROVIDED`:
 - capital P&L defaults to explicit zero when omitted
 - total P&L defaults to capital + FX when omitted
4. Canonical FX validation is enforced before persistence on the FX bypass path.

## Key Design Decisions
1. FX capital P&L remains explicit zero.
2. Baseline implementation supports `NONE` and `UPSTREAM_PROVIDED` deterministically.
3. `CASH_LOT_COST_METHOD` remains a later extension and is not simulated implicitly in this slice.

## Fresh Source Admission

Canonical production FX with an explicit `UPSTREAM_PROVIDED` claim must supply both
`realized_fx_pnl_local` and `realized_fx_pnl_base`. Explicit zero and signed amounts are evidence;
totals do not substitute for missing FX. `FX_CONTRACT_OPEN` is non-realizing and exempt, as are
`NONE`, non-FX and generated cash types. Missing/unknown components cannot downgrade an explicit
claim. Existing business validation separately governs capital and conserving totals.

Activate this strict-forward contract only after deploying both `ingestion-service` and
`persistence-service`; a predecessor writer does not enforce the new admission policy. No schema
backfill or source-presence inference is part of this cutover.

The ingestion DTO rejects incomplete single requests and entire invalid mixed batches with
HTTP 422 / `FX_UPSTREAM_SOURCE_INCOMPLETE` before job creation/publication. Incomplete historical
HTTP resubmissions follow the same strict-forward rule. Raw persistence handles exact duplicates
first, then validates inside its existing UOW: refusal rolls back the claim and leaves no new
ledger/outbox/fence. A complete zero source after first refusal is first booking, not correction.

Raw upstream persistence identity `v3` binds all six original capital/FX/total local/base amounts,
distinguishing missing from supplied zero/signed values. Non-upstream v1/source-booked v2 hashes
remain unchanged. Locked immutable v3 ledger identity can qualify exact incomplete broker replay
after transient fence expiry without a ledger/outbox write. Ambiguous pre-v3 P&L-excluding identity
fails closed for upstream replay even when booked FX matches; old fingerprints/rows are not
rewritten or promoted. Caller receipts and mutable enriched columns are not reconstruction authority.

This admission slice changes no historical calculation, receipt, reader/QCP projection or
correction command. In particular it does not implement historical missing-versus-zero qualification
or the command-level revision model. The distinct real-PG matrix is
`tests/integration/services/persistence_service/test_fx_source_admission_postgresql.py`, selected by
the native FX contract and changed-code coverage lanes. Its captured broker is explicit: registered
HTTP/real consumer/PostgreSQL proof is not live Kafka or deployment certification. Exact-head native
execution, required protected checks and mainline validation remain necessary for acceptance.

## Shared-Doc Conformance Note
Validated against:
1. `05-common-validation-and-failure-semantics.md`
2. `06-common-calculation-conventions.md`
3. `09-idempotency-replay-and-reprocessing.md`

## Residuals
1. No advanced cash-lot realized FX engine yet.
2. No MTM/unrealized contract valuation yet.

## Exit Evidence
1. `tests/unit/services/portfolio_transaction_processing_service/application/cost_basis_processing/test_execution.py`
2. `tests/unit/libs/portfolio_common/test_fx_validation.py`

