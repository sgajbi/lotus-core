# FX Slice 2 - Persistence and Linkage Traceability

## Scope
This slice makes the FX metadata durable and deterministic enough for later settlement and contract-lifecycle slices.

## Delivered
1. Added FX transaction metadata columns to the `transactions` table.
2. Added deterministic FX linkage enrichment helper:
 - `enrich_fx_transaction_metadata`
3. Wired FX enrichment into cost-calculator intake so persisted downstream transaction updates carry stable defaults when upstream does not provide them.
4. Added integration evidence that FX metadata survives UPSERT round trips.

## Deterministic Defaults Introduced
1. `economic_event_id`
2. `linked_transaction_group_id`
3. `calculation_policy_id`
4. `calculation_policy_version`
5. `component_id`
6. `fx_contract_id` for forward/swap and contract components
7. `swap_event_id` for swap business types
8. `fx_cash_leg_role` inference for settlement component types

## What This Slice Does Not Yet Do
1. It does not generate linked cash settlement rows automatically.
2. It does not implement `FX_CONTRACT` position lifecycle.
3. It does not yet compute realized FX P&L.

## Exit Evidence
1. `tests/unit/libs/portfolio_common/test_fx_linkage.py`
2. `tests/integration/services/persistence_service/repositories/test_repositories.py`
3. `alembic/versions/ac23de45f678_feat_add_fx_transaction_metadata_fields.py`
