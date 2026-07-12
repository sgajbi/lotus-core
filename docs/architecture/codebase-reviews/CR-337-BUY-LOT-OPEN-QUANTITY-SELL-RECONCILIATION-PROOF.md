# CR-337 BUY Lot Open Quantity SELL Reconciliation Proof

## Scope

Review the persisted BUY lot state invariant against later SELL disposal processing.

## Finding

`lotus-core#314` reported a live seeded-stack mismatch where:

1. holdings and sell-disposals showed a partial SELL had occurred,
2. BUY lot state still showed the original open quantity.

That is a serious downstream-read risk because BUY lots and SELL disposals are supposed to
reconcile exactly on remaining/open quantity for the same security.

## Actions Taken

Added a DB-backed integration proof that exercises the real cost-calculator consumer flow under the
real persistence ordering:

1. seed the raw BUY and SELL transaction rows,
2. process the BUY message,
3. process the partial SELL message,
4. assert the persisted BUY lot remains at `original_quantity = 420` but moves to
   `open_quantity = 310`,
5. assert the persisted SELL outbox payload also carries the expected disposal economics.

## Why This Matters

This closes the most immediate uncertainty around the code path itself:

1. the lot-state mutation path does reconcile remaining quantity after a partial SELL when the
   runtime ordering matches the real pipeline,
2. the `#314` symptom is therefore more likely to be seeded data drift, missing replay/reseed, or a
   runtime-specific state problem than a current core code-path defect,
3. downstream teams can rely on the invariant being guarded by an explicit DB-backed proof going
   forward.

## Follow-Up

Revalidate the seeded `PB_SG_GLOBAL_BAL_001` runtime slice and close `lotus-core#314` if the live
API/DB state now reconciles. Keep the issue open only if the seeded environment still reproduces
despite this proved code path.

## Evidence

- `tests/integration/services/calculators/cost_calculator_service/test_int_cost_consumer_persistence.py`
- `pytest tests/integration/services/calculators/cost_calculator_service/test_int_cost_consumer_persistence.py -q`
