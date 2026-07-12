# CR-1220 Source Batch Fingerprint Guard

Date: 2026-07-01

## Objective

Continue GitHub issue #676 as a category-wise lineage slice: fix the remaining active source-data
products that labeled request or snapshot fingerprints as `source_batch_fingerprint`, then promote
the lesson into an executable guard so the same defect class is blocked.

## Change

- `ClientTaxRuleSet:v1`, `ClientIncomeNeedsSchedule:v1`,
  `LiquidityReserveRequirement:v1`, `PlannedWithdrawalSchedule:v1`,
  `CioModelChangeAffectedCohort:v1`, `ExternalCurrencyExposure:v1`,
  `ExternalEligibleHedgeInstrument:v1`, `ExternalFXForwardCurve:v1`,
  `ExternalHedgePolicy:v1`, `ExternalHedgeExecutionReadiness:v1`, and
  `ExternalOrderExecutionAcknowledgement:v1` now leave `source_batch_fingerprint` null when true
  source-batch lineage is unavailable.
- Existing response identity remains available through each product's deterministic `snapshot_id`.
- `scripts/source_data_product_contract_guard.py` now rejects request/snapshot-scope expressions in
  `source_batch_fingerprint`, including `request_fingerprint(...)`, `snapshot_fingerprint`, and
  `request_scope_fingerprint`.

## Expected Improvement

Downstream audit, replay, and data-mesh consumers no longer receive request identity or fail-closed
snapshot identity mislabeled as upstream batch lineage for these products. Future source-data product
slices also get a fast local and CI-visible guard instead of depending on manual review.

## Tests Added

- Source-data product service tests now assert null `source_batch_fingerprint` with retained
  `snapshot_id` for the corrected reference, liquidity, CIO, treasury, and OMS products.
- Source-data product contract guard tests cover accepted null/source-derived evidence and rejected
  request, snapshot, and request-scope fingerprint assignments.

## Validation Evidence

- `python scripts/source_data_product_contract_guard.py` passed.
- `python -m pytest tests/unit/scripts/test_source_data_product_contract_guard.py -q` passed with
  16 tests.
- `python -m pytest tests/unit/services/query_service/services/test_client_tax_rule_set.py tests/unit/services/query_service/services/test_client_income_needs_schedule.py tests/unit/services/query_service/services/test_planned_withdrawal_schedule.py tests/unit/services/query_service/services/test_liquidity_reserve_requirement.py tests/unit/services/query_service/services/test_cio_model_change_cohort.py tests/unit/services/query_service/services/test_external_currency_exposure.py tests/unit/services/query_service/services/test_external_eligible_hedge_instrument.py tests/unit/services/query_service/services/test_external_fx_forward_curve.py tests/unit/services/query_service/services/test_external_hedge_policy.py tests/unit/services/query_service/services/test_external_hedge_execution_readiness.py tests/unit/services/query_service/services/test_external_order_execution_acknowledgement.py -q`
  passed with 36 tests.

## Downstream Compatibility

No route path, response field name, snapshot ID shape, supportability payload, row payload, or
repository read behavior changed. The intentional behavior change is that products without true
source-batch lineage return `source_batch_fingerprint: null` instead of a request/snapshot hash.

## Documentation And Wiki Decision

This architecture record, the codebase review ledger, quality scorecard, refactor health report, and
repository context were updated. No wiki update is required because no operator command, wiki
navigation, or runbook truth changed.

## Remaining Follow-Up

- Wire true persisted source-batch lineage where available instead of leaving degraded null lineage.
- Keep issue #676 open for PR/CI/QA evidence and any downstream adoption checks.
