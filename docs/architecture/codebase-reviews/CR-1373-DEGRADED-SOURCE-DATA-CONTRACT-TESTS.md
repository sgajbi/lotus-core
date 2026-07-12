# CR-1373 Degraded Source-Data Contract Tests

## Objective

Fix GitHub issue #609 by adding a representative contract suite for degraded source-data and
read-model responses, so stale, partial, fallback, unavailable, and control-blocking evidence
cannot masquerade as fresh authoritative Core data.

## Changes

- Added `test_degraded_source_data_contracts.py` as a cross-family source-data contract suite.
- Covered representative responses for positions, transactions, market data, instrument reference,
  transaction-cost valuation, cashflow projection, and reconciliation/control findings.
- Asserted response status semantics, data-quality status, freshness, supportability, lineage/hash
  posture, fallback reason details, and correlation propagation where applicable.
- Extended the guarded API example catalog with a HoldingsAsOf fallback-degradation example linked
  to the new test suite.

## Expected Improvement

- Downstream applications can rely on Core-owned degradation and freshness evidence instead of
  inferring status from payload shape.
- Future source-data products have a concrete contract-test pattern for degraded states.
- Design-time complexity is reduced by testing the shared metadata contract at product-family
  boundaries rather than adding one-off assertions in each router.
- Runtime supportability improves because degraded responses remain diagnosable through
  source-owned reason codes, timestamps, supportability fields, and correlation IDs.

## Tests Added

- HoldingsAsOf fallback valuation exposes field-level degradation details.
- TransactionLedgerWindow partial pages and missing instrument references expose namespaced reason
  codes.
- MarketDataCoverageWindow reports stale observations, missing instruments, and missing FX pairs.
- InstrumentEligibilityProfile reports missing reference profiles.
- TransactionCostCurve reports page-scoped degraded valuation evidence.
- PortfolioCashflowProjection cannot claim current source evidence without an evidence timestamp.
- ReconciliationEvidenceBundle exposes blocking finding state and current source metadata.

Existing dependency-timeout and hard-failure problem-response coverage remains in the ingestion
router and verified API example catalog; this slice links the source-data degradation surface rather
than duplicating ingestion write-path failure tests.

## Validation Evidence

```powershell
python -m pytest tests/unit/services/query_service/services/test_degraded_source_data_contracts.py -q
```

Final focused, API-example, docs, lint, and diff checks are recorded in the issue comment before
commit.

## Downstream Compatibility Impact

No route path, request DTO, response DTO field removal, OpenAPI route ownership, database schema,
Kafka contract, persistence model, runtime topology, or source-product ownership changed. The API
example catalog is documentation evidence only. The new tests lock existing additive degradation,
freshness, lineage, supportability, and correlation metadata behavior.

## Same-Pattern Scan

The scan covered the active source-data/read-model families named by #609: positions,
transactions, prices/market data, instrument reference, valuation, cashflow, and
reconciliation/control. HoldingsAsOf has the richest fallback-detail contract; transaction,
market-data, instrument-reference, valuation, cashflow, and reconciliation responses already expose
family-specific supportability/freshness metadata that now has representative contract coverage.

Future source-data issue fixes must add or update this representative suite when they introduce
fallback, stale, partial, unavailable, dependency-timeout, or blocking-control states.

## Docs, Context, And Skill Decision

- Codebase review ledger updated with #609 closure evidence.
- Repository context updated with the reusable degraded-state contract-test rule.
- Verified API example catalog updated with a representative HoldingsAsOf degraded response.
- No wiki update is required for this slice because operator navigation and supported-feature
  truth did not change; the guarded API catalog is the durable reader-facing example source.
- No platform skill update is required: the backend delivery, issue-fix, and codebase-review skills
  already require same-pattern scans and durable context updates. The new rule is repo-local.

## Remaining Hotspots

Dependency hard failures for source-data readers should continue to use standard problem responses
when no safe degraded payload exists. Add a focused source-data dependency failure suite if a future
issue introduces an actual external source-data client timeout or fallback adapter.
