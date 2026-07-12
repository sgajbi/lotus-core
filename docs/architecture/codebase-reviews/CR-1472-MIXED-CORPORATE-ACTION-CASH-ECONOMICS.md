# CR-1472: Mixed Corporate Action Cash Economics

## Objective

Close the incorrect treatment of true corporate-action cash consideration as generic income and
make its allocated basis, realized P&L, settlement linkage, and Bundle A reconciliation auditable
through the combined transaction-processing path.

This is an issue #468 correctness and modularity slice. It does not activate the combined runtime.

## Finding

`CASH_CONSIDERATION` previously used the generic income cost strategy. That behavior:

- discarded basis allocated to the cash component,
- produced no realized P&L,
- classified proceeds as income,
- reconciled only source-out basis against target-in basis, and
- could not prove a mixed demerger ledger equation end to end.

The engine transaction extension serializer also emitted original extra-field values after a
calculator changed them, which could produce stale calculated metadata.

## Architecture

The corrected dependency path is:

1. ingestion and query DTOs expose optional source-owned allocated basis fields;
2. `BookedTransaction` and `TransactionEvent` preserve them across the anti-corruption boundary;
3. the pure `corporate_action_cash_economics` domain policy calculates and validates economics;
4. `CashConsiderationStrategy` applies the policy without repository or consumer dependencies;
5. repository adapters persist canonical transaction economics;
6. cashflow policy classifies the product leg as `CORPORATE_ACTION_PROCEEDS`;
7. Bundle A reconciliation validates source basis against target plus cash basis; and
8. the combined use case commits cost, cashflow, position, reconciliation, idempotency, and outbox
   effects atomically.

## Financial Contract

For true cash consideration:

```text
net_proceeds_local = gross_proceeds_local - fees_local
realized_total_pnl_local = net_proceeds_local - allocated_cost_basis_local
realized_total_pnl_base = net_proceeds_base - allocated_cost_basis_base
source_basis_out_local = target_basis_in_local + cash_basis_local
```

The default policy is fail closed:

- local and base allocated basis are required;
- quantity and price on the product marker must be zero;
- same-currency P&L is capital P&L with zero FX P&L;
- cross-currency capital and FX components must be source-provided and reconcile to total P&L;
- the actual cash movement is a linked `ADJUSTMENT` on the cash instrument; and
- missing cash basis produces `insufficient_cash_basis`, not a false balanced result.

`CASH_IN_LIEU` remains separate. Its fractional product/MVT/cash overlay contract is not broadened
or claimed complete by this slice.

## Compatibility

The transaction API additions are nullable and backward compatible for transaction types that do
not use cash allocation. `CASH_CONSIDERATION` behavior intentionally changes: incomplete basis now
fails closed, proceeds no longer count as generic income, and valid events persist realized P&L.

Existing route paths, event topics, portfolio cost-basis selection, source/target transfer logic,
position quantity behavior, and linked cash settlement amount are preserved.

## Documentation Decision

Repository context, the mixed-consideration RFC, schema catalog, performance-economics methodology,
consolidation ledger, review ledger, and cost/cashflow/position wiki sources changed with the
implementation. `README.md` does not change because no repository front door, canonical command,
runtime activation state, or supported top-level capability changed in this slice.

## Validation

- 12 pure cash-economics domain tests cover gains, losses, fees, same/cross currency, and failures.
- 87 focused cost-engine tests cover strategy, calculated-field serialization, and FX regression.
- 113 cashflow/analytics unit tests cover proceeds classification and sign semantics.
- 52 cost-consumer/reconciliation tests cover durable evidence and missing-basis findings.
- 2 rebuilt migration-backed cashflow rule tests passed.
- 2 mixed-demerger PostgreSQL tests prove financial outputs, zero-sum product flows, linked cash,
  idempotency, reconciliation evidence, and rollback.
- `make test-transaction-processing-contract` passed 20 tests in 93.21 seconds.
- migration SQL, OpenAPI quality, vocabulary validation, Ruff, and scoped cost-engine MyPy passed.

## Remaining Work

- complete cash-in-lieu fractional basis, MVT, and settlement semantics separately;
- add jurisdiction/policy configuration before supporting non-realizing or pro-rata cash basis;
- complete #468 runtime capacity, deployment, observability, and cutover prerequisites; and
- obtain CI and deployed evidence before changing runtime topology or issue status.
