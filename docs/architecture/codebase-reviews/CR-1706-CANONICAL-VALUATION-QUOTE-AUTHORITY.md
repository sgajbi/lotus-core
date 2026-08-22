# CR-1706: Canonical valuation quote authority

Date: 2026-08-22
Issue: [#990](https://github.com/sgajbi/lotus-core/issues/990)
Status: Fixed locally; protected PR, exact-main, canonical runtime, and wiki evidence pending

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
2. Publish one effective-dated policy assignment for every seeded instrument. Bonds use
   `CLEAN_PERCENT_FACE_CALCULATED_ACCRUAL`; other instruments use
   `UNIT_PRICE_MARKET_VALUE`.
3. Publish one authoritative source fact for every raw market-price observation. Bond facts carry
   `PERCENT_OF_PRINCIPAL_CLEAN`; other facts carry `UNIT_PRICE`.
4. Derive stable source record identity from security/date and bind the complete source evidence
   into a deterministic SHA-256 content hash. Identical replay is stable; changed price evidence
   changes the hash.
5. Ingest authority only after raw price readiness and before activating the business-date
   horizon. Keep each source-fact request within the existing 500-record contract.
6. On canonical replay, delete only evidence owned by `LOTUS_FRONT_OFFICE_SEED` in the exact
   canonical tenant/book before republishing version `1`.

## Compatibility and boundaries

This is canonical local seed authority, not a valuation-formula change. Existing production
fail-closed behavior for missing, overlapping, stale, or wrong-book authority remains unchanged.
No API/OpenAPI shape, database schema or migration, Kafka contract, calculation algorithm,
dependency, image, or deployment topology changes. Broader source-owned tenant migration remains
under #798. Downstream applications must consume Core authority and must not fabricate quote basis.

## Evidence

- `tests/unit/tools/test_front_office_portfolio_seed.py`: `78 passed` at exact signed local head
  `1c4a33251` after rebasing onto main `1746ea913`; this covers complete assignment/fact coverage,
  deterministic replay, changed-source hash sensitivity, exact ingestion order, 500-row batching,
  and exact-scope cleanup.
- Ruff, format, signature, and diff-hygiene checks passed for the changed seed and test files.
- DTO construction accepted all 11 assignments and all 4,136 authoritative facts in bounded
  batches for the canonical 2025-03-31 through 2026-04-10 window.
- The pre-fix canonical runtime reached healthy Core startup, populated 11 positions, valued the
  nine non-bond positions, and recorded the exact missing-authority reason for both bonds. Patched
  live 11-of-11 valuation, terminal-queue stability, protected PR, exact-main, wiki publication,
  issue closure, and branch/worktree hygiene remain pending at this fixed-local checkpoint.

## Documentation decision

The canonical seed and operator diagnosis contract changed, so the seed runbook, authored
Operations Runbook wiki, repository engineering context, and review ledger are updated. README,
RFC, public API, supported-feature, migration, and central platform context truth do not change.
