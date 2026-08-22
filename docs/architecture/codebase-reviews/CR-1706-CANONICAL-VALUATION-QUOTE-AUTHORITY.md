# CR-1706: Canonical valuation quote authority

Date: 2026-08-22
Issue: [#990](https://github.com/sgajbi/lotus-core/issues/990)
Status: Fixed locally; protected PR, exact-main, and wiki evidence pending

## Finding

The canonical `PB_SG_GLOBAL_BAL_001` seed published raw price observations but no portfolio
tenant/book scope, valuation-policy assignments, or authoritative market-price source facts. The
production valuation path correctly refused to infer bond quote convention from price magnitude.
A clean canonical run therefore valued nine of eleven positions while both
`FO_BOND_UST_2030` and `FO_BOND_SIEMENS_2031` accumulated terminal failures with
`bond valuation requires explicit quote-convention authority`.

## Decision

Make the canonical seed the source owner for its complete valuation evidence:

1. Scope `PB_SG_GLOBAL_BAL_001` to tenant `LOTUS_PB_SG` and legal book
   `SG_PRIVATE_BANK_BOOK`.
2. Publish one effective-dated `UNIT_PRICE_MARKET_VALUE` policy assignment for every seeded
   instrument.
3. Require an explicit source quote convention for every canonical security and publish one
   authoritative `UNIT_PRICE` source fact for every raw market-price observation. Both canonical
   bonds declare clean percent, denominator 100, and 1,000 face per held unit, producing
   `raw_quote * 1000 / 100`. Missing, product-mismatched, or unsupported metadata fails before
   publication. Bind the raw quote, raw quote basis, denominator, face-per-unit convention,
   normalization identity, and normalized price into the source content hash; do not relabel
   runtime position quantity as face authority.
4. Derive stable source record identity from security/date and bind the complete source evidence
   into a deterministic SHA-256 content hash. Identical replay is stable; changed price evidence
   changes the hash.
5. Ingest authority only after raw price readiness and before activating the business-date
   horizon. Keep each source-fact request within the existing 500-record contract.
6. Extend cash unit-price authority through the latest planned-withdrawal transaction date; the
   future cash legs are valuation work in the same exact portfolio scope.
7. Treat valuation assignments and source facts as shared append-only book authority. Routine
   portfolio cleanup preserves them and their canonical portfolio/instrument parents: identical
   version-1 replay is idempotent, while changed evidence must append a governed newer version or
   use an explicit full local-state reset.
8. Make the `--skip-cleanup` reuse path an explicit authority upgrade: republish the scoped
   portfolio master and instruments, prove durable tenant/book scope, publish only observations
   missing from the complete raw-price windows, wait for those parents, then publish and durably
   verify assignments and source facts without replaying transactions or rearming unchanged prices.
9. Require three consecutive terminal queue observations. Emit a content-bound JSON receipt only
   after a read-only PostgreSQL projection of the latest append-only source versions exactly
   matches every expected durable assignment and source fact; derive receipt counts and hashes
   from those durable rows, never the local bundle.

## Compatibility and boundaries

This is canonical local seed authority, not a valuation-formula change. Existing production
fail-closed behavior for missing, overlapping, stale, or wrong-book authority remains unchanged.
No API/OpenAPI shape, database schema or migration, Kafka contract, calculation algorithm,
dependency, image, or deployment topology changes. Broader source-owned tenant migration remains
under #798. Downstream applications must consume Core authority and must not fabricate quote basis.

## Evidence

- `tests/unit/tools/test_front_office_portfolio_seed.py`: `94 passed` after rebasing onto main
  `1746ea913`; this covers complete assignment/fact coverage,
  deterministic replay, changed-source hash sensitivity, exact ingestion order, 500-row batching,
  per-security quote metadata and fail-closed rejection, denomination/hash sensitivity,
  portfolio-safe append-only authority preservation, machine-readable evidence, reuse-path
  authority upgrade, durable-row comparison, and repeated scheduler observations.
- The combined canonical seed, quote-authority domain, and valuation-logic pack passed `121` tests;
  full MyPy passed `318` source files.
- Ruff, format, signature, and diff-hygiene checks passed for the changed seed and test files.
- DTO construction accepted all 11 assignments and all 4,176 authoritative facts in bounded
  batches for the canonical 2025-03-31 through 2026-04-10 window.
- The pre-fix canonical runtime reached healthy Core startup, populated 11 positions, valued the
  nine non-bond positions, and recorded the exact missing-authority reason for both bonds. Patched
  replay proved the assignments and initial 4,136 facts were present, removed the missing-quote
  error, and then exposed that a percent-of-face policy requires independent `signed_face_amount`
  authority.
  The source-owned unit-price normalization avoids that prohibited runtime inference. A subsequent
  replay reached 11-of-11 valued positions with zero bond failures, then identified two future cash
  jobs whose dates were beyond the former cash fact window; the final bundle extends exact-scope
  cash authority through that planned-withdrawal horizon. A clean final replay and independent
  verify-only receipt at signed `e5ebb86c8` published 4,176 source facts and reached 11-of-11
  valued positions, `COMPLETE`
  position and cash data quality, analytics/performance/return-path dates of `2026-04-10`, and zero
  pending, processing, stale, or failed valuation and aggregation jobs for three consecutive
  observations. The source-fact set hash is
  `173e6923e428aa9da29f3fd6cef241bab8966d3c843fe75e6ee98ad325d35078`; the receipt content hash is
  `93a999bcccadb858893bbde88955f7e287499485e57f4cf66536e20138c25c3c`, and exact retained JSON byte
  hash is `2270401bd1865ce988768bb4e3b08b612b8d5ff2f8e028b23cb9efc19ffa1abc`. The machine-readable
  receipt is durably attached to #990 as pre-review runtime evidence. Review subsequently required
  the retained receipt to be regenerated from an exact durable-row comparison rather than local
  bundle claims. The fix-forward clean replay then completed 11-of-11 valuation, `COMPLETE`
  position/cash quality, current `2026-04-10` analytics/performance/return paths, and three terminal
  observations with every valuation and aggregation queue at zero. Its exact durable projection
  proves 11 policy assignments and 4,176 source facts; the assignment hash is
  `c5cdc57d8d25a593a8e890f24a1a4111ff7039de447c86b8626f587d7c8fc433`, the source-fact hash is
  `7c768348fa5cbbe6361b43a47af9fbfb9ebb8b0bb165582947794bef6e795a9f`, the receipt content hash is
  `955657d7b140454dd39e1ea099e7ebd58d06fab608b4f3ef403ac94e89ce31c7`, and the retained JSON byte
  hash is `8ded370b0098bbd1fff6420bcf9cc71816885144208bb0c1aa509bed61d63253`.
  Protected PR, exact-main, wiki publication, issue
  closure, and branch/worktree hygiene remain pending at this fixed-local checkpoint.

## Documentation decision

The canonical seed and operator diagnosis contract changed, so the seed runbook, authored
Operations Runbook wiki, repository engineering context, and review ledger are updated. README,
RFC, public API, supported-feature, migration, and central platform context truth do not change.
