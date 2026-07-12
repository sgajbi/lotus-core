# CR-1372 Holdings Degradation Source Metadata

## Objective

Fix GitHub issue #601 by making HoldingsAsOf fallback, stale, partial, and unavailable evidence
explicit in the Core-owned response contract instead of leaving downstream consumers to infer it
from aggregate `data_quality_status`.

## Changes

- Added reusable `SourceDataDegradationSummary` and `SourceDataDegradationDetail` metadata to the
  shared source-data runtime DTO base.
- Added a dedicated `position_holdings_degradation.py` policy module for HoldingsAsOf degradation
  details.
- Exposed row/field-scoped degradation details for:
  - history rows using snapshot valuation fallback,
  - history rows where snapshot valuation fallback is unavailable and cost basis is used,
  - stale or missing market-price evidence,
  - missing or non-current position-state evidence,
  - empty holdings responses.
- Added deterministic HoldingsAsOf `content_hash`, `source_digest`, `source_batch_fingerprint`,
  `source_refs`, and bounded `source_lineage` for the assembled holdings response.
- Updated OpenAPI contract tests so degradation and source-proof metadata remain visible.

## Expected Improvement

- Downstream proof generators can distinguish authoritative current holdings from fallback-derived
  valuation fields.
- Operators can identify the exact holding and field family affected by degradation.
- Source proof becomes source-owned: downstream consumers no longer need to manufacture Core
  freshness, fallback, or content-hash evidence.
- Design-time complexity is reduced by isolating degradation policy in one module instead of
  spreading fallback semantics through routers or consumers.

## Tests Added

- Holdings runtime metadata now asserts deterministic non-empty source hashes and source refs.
- Hash determinism is covered for identical holdings evidence.
- Degradation policy tests cover authoritative/no-degradation, fallback, stale, partial, and
  unavailable cases.
- Response assembly tests prove the live holdings service output carries fallback degradation
  metadata.
- OpenAPI tests assert the reusable degradation schema is exposed.

## Validation Evidence

```powershell
python -m pytest tests/unit/services/query_service/dtos/test_source_data_product_identity.py tests/unit/services/query_service/services/test_position_holdings.py tests/unit/services/query_service/services/test_position_holdings_response.py tests/integration/services/query_service/test_main_app.py::test_openapi_exposes_holdings_as_of_runtime_supportability_metadata tests/integration/services/query_service/test_main_app.py::test_openapi_describes_position_contract_examples -q
python -m ruff check src/services/query_service/app/dtos/source_data_product_identity.py src/services/query_service/app/services/position_holdings.py src/services/query_service/app/services/position_holdings_degradation.py src/services/query_service/app/services/position_holdings_response.py tests/unit/services/query_service/services/test_position_holdings.py tests/unit/services/query_service/services/test_position_holdings_response.py tests/unit/services/query_service/dtos/test_source_data_product_identity.py tests/integration/services/query_service/test_main_app.py
python -m ruff format --check src/services/query_service/app/dtos/source_data_product_identity.py src/services/query_service/app/services/position_holdings.py src/services/query_service/app/services/position_holdings_degradation.py src/services/query_service/app/services/position_holdings_response.py tests/unit/services/query_service/services/test_position_holdings.py tests/unit/services/query_service/services/test_position_holdings_response.py tests/unit/services/query_service/dtos/test_source_data_product_identity.py tests/integration/services/query_service/test_main_app.py
```

Final architecture, API, docs, and diff checks are recorded in the issue comment before commit.

## Downstream Compatibility Impact

This is an additive API response contract change. Existing fields, route paths, request parameters,
database schema, runtime topology, and existing holdings valuation behavior are preserved.

Intentional additive fields are inherited by source-data runtime responses through the shared base.
HoldingsAsOf now also returns real source-owned hash and lineage metadata instead of the empty
placeholder hash.

## Same-Pattern Scan

The scan found the active fallback-enabled holdings path plus adjacent source-data metadata helper
usage. Cashflow projection, benchmark assignment, core snapshot, cash movement, and maturity summary
already compute content hashes or source proof metadata through their own service-specific helpers.
Cash-balance fallback is a related source-data path but already carries cash-weight supportability
metadata and should be a separate slice if field-level degradation is required there.

Future read-model fallbacks must use the shared `SourceDataDegradationSummary` contract rather than
adding local boolean flags or forcing downstream consumers to infer freshness.

## Docs, Context, And Skill Decision

- Codebase review ledger updated with issue #601 closure evidence.
- Repository context updated with the reusable degradation-metadata rule.
- No wiki update is required for this slice because this is a low-level additive API metadata
  contract; public navigation and operator workflow pages are unchanged.
- No platform skill update is required: existing backend delivery and issue-fix skills already
  require same-pattern scans and durable context updates; the new rule is repo-local.

## Remaining Hotspots

Field-level degradation metadata is now implemented for the HoldingsAsOf fallback path. Related
source-data products that use fallback or synthetic default behavior should adopt the shared
degradation contract as those issue slices touch them.
