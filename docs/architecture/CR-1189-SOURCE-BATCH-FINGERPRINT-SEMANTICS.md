# CR-1189 Source Batch Fingerprint Semantics

Date: 2026-06-30

## Objective

Begin fixing GitHub issue #676 by stopping selected source-data products from labeling request-scope
or snapshot fingerprints as upstream source-batch lineage.

## Change

- `ClientTaxProfile:v1`, `ClientRestrictionProfile:v1`,
  `SustainabilityPreferenceProfile:v1`, and `DpmPortfolioUniverseCandidate:v1` now leave
  `source_batch_fingerprint` null when true upstream source-batch evidence is unavailable.
- Existing request/snapshot identity remains available through `snapshot_id` and, for DPM universe
  paging, `page.request_scope_fingerprint`.
- The shared runtime metadata DTO description now reserves `source_batch_fingerprint` for upstream
  source-batch evidence.
- RFC-0083 source-data product catalog guidance now states that request, pagination, or snapshot
  fingerprints must not be substituted into `source_batch_fingerprint`.

## Expected Improvement

Downstream consumers no longer receive request-scope fingerprints mislabeled as source-batch lineage
for the corrected products. This prevents replay/audit tooling from treating response identity as an
upstream batch identity.

## Tests Added

- Client tax profile response now proves `source_batch_fingerprint is None` while `snapshot_id`
  remains populated.
- Client restriction profile response now proves `source_batch_fingerprint is None` while
  `snapshot_id` remains populated.
- Sustainability preference profile response now proves `source_batch_fingerprint is None` while
  `snapshot_id` remains populated.
- DPM portfolio universe response now proves `source_batch_fingerprint is None` while
  `page.request_scope_fingerprint` and `snapshot_id` remain populated.

## Validation Evidence

- `python -m pytest tests/unit/services/query_service/services/test_client_tax_profile.py tests/unit/services/query_service/services/test_client_restriction_profile.py tests/unit/services/query_service/services/test_sustainability_preference_profile.py tests/unit/services/query_service/services/test_dpm_portfolio_universe.py tests/unit/services/query_service/dtos/test_source_data_product_identity.py -q`
  passed with 36 tests.
- `python -m ruff check ...` passed for the touched query-service response builders, DTO, and tests.
- `python -m ruff format --check ...` passed for the touched query-service response builders, DTO,
  and tests.
- `git diff --check` passed.

## Downstream Compatibility

No route path, DTO field name, response envelope, pagination token, snapshot ID shape, or row payload
changed. The intentional behavior change is semantic: products without true source-batch evidence now
return `source_batch_fingerprint: null` instead of a request/snapshot fingerprint.

## Documentation And Wiki Decision

RFC-0083 source-data product catalog, this architecture record, the codebase review ledger, and
quality/refactor scorecards were updated. No wiki update is required because no operator-facing
command or wiki-authored runbook changed.

## Remaining Follow-Up

- Continue auditing other source-data products that still synthesize request fingerprints in
  `source_batch_fingerprint`.
- Wire true source-batch fingerprints from persisted ingestion evidence where available.
- Keep the CR-1220 source-data product contract guard enforced so request/snapshot fingerprints are
  not reassigned to source-batch lineage fields.
