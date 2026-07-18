# CR-1641: Portfolio State Snapshot Trust And Calculation Lineage

## Objective

Resolve GitHub issue #790 by making `PortfolioStateSnapshot:v1` a deterministic, tenant-bound
portfolio-state receipt with exact reconciliation proof and explicit input, calculation, and output
lineage for baseline and simulation modes.

## Finding

The QCP snapshot assembled governed sections and published product metadata, but left
`reconciliation_status` unknown and `snapshot_id` null. Currentness was inferred from baseline data
quality and a timestamp without verifying the exact portfolio-day/epoch reconciliation controls.
The response also lacked financial calculation lineage, so consumers could not independently bind
selected source facts, snapshot policy, and returned sections.

## Change

- Added business-date scope to QCP position source records and one set-based adapter read for exact
  `FINANCIAL_RECONCILIATION` controls.
- Reused the framework-independent holdings reconciliation classifier. QCP retains source-row scope
  extraction, control reads, orchestration, DTOs, and source-product ownership.
- Added deterministic hashes for normalized selected position/instrument facts, reconciliation
  scopes, and control outcomes. Ordering does not change the hashes; material source corrections do.
- Added the `PORTFOLIO_STATE_SNAPSHOT` three-layer lineage receipt. Inputs bind portfolio, tenant,
  as-of date, mode, restatement version, request, source/control evidence, governance, valuation,
  and simulation version; the output binds returned sections and trust posture.
- Populated a deterministic `portfolio_state_snapshot:<output-hash>` identity and fail-closed
  reconciliation/currentness metadata. Historical fallback retains partial data quality while using
  available source/control timestamps; empty sources remain unknown and unreconciled.
- Extended the existing source-data-product guard so this trust-certified response cannot silently
  drop its calculation-lineage field.

## Compatibility And Ownership

The HTTP change is additive: `calculation_lineage` is new and previously unresolved trust metadata
is now populated from authoritative controls. Existing paths, requests, section names and values,
simulation behavior, arithmetic, errors, database schema, migrations, events, Kafka contracts, and
runtime topology are unchanged. No compatibility alias or legacy response path was added.

The QCP application owns snapshot assembly and the 28-digit weight/totals calculation policy. Shared
code is limited to framework-independent calculation hashing and holdings reconciliation policy.

## Validation

- Core snapshot application suite: `90 passed`.
- Focused source adapter/scope proof: `6 passed` before response integration; combined focused proof
  reached `41 passed`.
- QCP router and application integration suite: `172` tests exercised, with the one stale mock
  updated; the focused route serialization proof passed afterward.
- Source-data product guard and its `18` unit tests passed.
- OpenAPI quality gate passed.
- Scoped MyPy passed for the QCP service, reconciliation helper, and response contract.
- Scoped Ruff lint/format and diff checks passed.

PR CI, exact-main validation, wiki publication, downstream consumer revalidation, and verified issue
closure remain post-local gates.
