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
- Enforced the declared 28-digit local Decimal context across totals, weights, deltas, projected
  quantity and baseline-value scaling, and price/FX valuation; ambient 6- and 50-digit caller
  contexts now produce identical results.
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

- Exact-HEAD QCP unit suite: `944 passed`; focused snapshot application suite: `93 passed`.
- Focused source adapter/scope proof: `6 passed` before response integration; combined focused proof
  reached `41 passed`.
- QCP router and application integration suite: `172 passed`.
- Isolated PostgreSQL adapter proof passed in `74.82s` using uniquely reserved Compose project
  `lotus-integration-db-556bb532`; the project was removed and the pre-existing Core runtime stayed
  running.
- A 10,000-position large-book measurement completed source hashing in `0.649054s` and exact-scope
  coalescing in `0.026176s` with one control scope.
- Source-data product guard and its `18` unit tests passed.
- OpenAPI quality gate passed.
- Full MyPy passed across `237` source files.
- Full Ruff lint/format passed across `2,058` files; the full lint guard chain passed.
- `make lotus-core-validate` passed all static/product checks and rebuilt managed-runtime smoke with
  `66` endpoint checks passed and `0` failed. Evidence:
  `output/lotus-core-validation/lotus-core-validation.json` and timestamped
  `20260718-172109-docker-endpoint-smoke` artifacts.

PR CI, exact-main validation, wiki publication, downstream consumer revalidation, and verified issue
closure remain post-local gates.
