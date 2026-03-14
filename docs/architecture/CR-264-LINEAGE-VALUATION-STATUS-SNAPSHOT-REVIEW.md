# CR-264 Lineage Valuation Status Snapshot Review

## Summary

The lineage detail and lineage key list both derive their latest valuation job from
`PortfolioValuationJob`, but the snapshot fence only constrained `created_at <= as_of`. That meant
a valuation job created before the snapshot could still leak later status updates into lineage
responses after the claimed snapshot moment.

## Finding

- Class: support-plane correctness risk
- Consequence: lineage detail and lineage list could both reflect valuation-job status that did not
  yet exist at the response snapshot time, weakening operator trust and risking drift between
  lineage and other snapshot-hardened support surfaces.

## Action Taken

- tightened `get_latest_valuation_job(...)` so snapshot selection now requires:
  - `PortfolioValuationJob.created_at <= as_of`
  - `PortfolioValuationJob.updated_at <= as_of`
- tightened all lineage-key projected latest-valuation-job subqueries the same way:
  - latest valuation date
  - latest valuation id
  - latest valuation status
  - latest valuation correlation id
- strengthened repository SQL tests to prove the added `updated_at` fence in both detail and list
  query shapes

## Evidence

- `python -m pytest tests/unit/services/query_service/repositories/test_operations_repository.py -q`
  - `60 passed`
- `python -m ruff check src/services/query_service/app/repositories/operations_repository.py tests/unit/services/query_service/repositories/test_operations_repository.py`
  - passed

## Follow-up

- keep checking “latest status-bearing row” helpers for the same pattern; fencing on creation time
  alone is not enough when the row’s status can still mutate after creation
