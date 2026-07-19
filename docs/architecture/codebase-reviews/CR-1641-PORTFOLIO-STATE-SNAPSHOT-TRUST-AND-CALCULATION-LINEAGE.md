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
- PR review found that duplicate or legacy financial-reconciliation controls for one date/epoch
  could be collapsed by database row order. The shared policy now groups every exact-scope control
  and aggregates the worst status, while QCP orders all control facts by normalized status and
  timestamp before hashing them. Adverse controls cannot be hidden and equivalent input sets retain
  one deterministic lineage identity regardless of row order.
- Canonical proof later exposed mixed per-security epochs on one portfolio day. QCP now uses the
  shared collective scope at the maximum valid row epoch instead of requiring one control per last-
  mutation epoch. The corresponding financial position-valuation read certifies every latest
  security row at or below that target, so the scope does not overstate what was calculated.

## Compatibility And Ownership

The HTTP change is additive: `calculation_lineage` is new and previously unresolved trust metadata
is now populated from authoritative controls. Existing paths, requests, section names and values,
simulation behavior, arithmetic, errors, database schema, migrations, events, Kafka contracts, and
runtime topology are unchanged. For duplicate same-scope controls only, reconciliation now
intentionally fails closed instead of selecting an arbitrary row. No compatibility alias or legacy
response path was added.

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
- Duplicate-control regressions prove worst-status classification and order-independent QCP control
  evidence hashing.
- Final combined coverage gate passed `5,113` unit, `12` unit-database, `55` critical-database,
  `138` integration-lite, and `284` operations-contract tests with zero warnings. The changed
  critical-source gate reached `92.38%` branch and `97.55%` line coverage; all critical groups
  cleared their governed thresholds.
- OpenAPI quality gate passed.
- Full MyPy passed across `237` source files.
- Full Ruff lint/format passed across `2,058` files; the full lint guard chain passed.
- `make lotus-core-validate` passed all static/product checks and rebuilt managed-runtime smoke with
  `66` endpoint checks passed and `0` failed. Evidence:
  `output/lotus-core-validation/lotus-core-validation.json` and timestamped
  `20260718-172109-docker-endpoint-smoke` artifacts.

PR CI, exact-main validation, wiki publication, downstream consumer revalidation, and verified issue
closure remain post-local gates.

No additional wiki source change is required for the review fix: the existing wiki already states
that currentness is fail-closed and reconciliation-backed; exact duplicate-control precedence is
methodology and review-ledger detail.

The mixed-epoch correction does update Query Control Plane and Mesh Data Products wiki source
because the earlier “exact business-date/epoch” wording could be misread as one control per
security-row epoch. PR CI, fresh-control runtime proof, exact-main validation, wiki publication,
and downstream revalidation remain pending.
