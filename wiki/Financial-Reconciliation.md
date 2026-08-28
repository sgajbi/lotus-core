# Financial Reconciliation

## Purpose

The financial reconciliation service is the independent control plane for arithmetic and completeness
checks inside `lotus-core`.

It does not replace calculator-owned state. It validates that persisted core outputs remain
internally consistent before downstream consumers treat them as trustworthy.

## What it handles

The current runtime centers on:

- transaction-to-cashflow completeness controls
- position-to-valuation consistency controls
- portfolio timeseries integrity controls
- Bundle A corporate-action lifecycle controls
- durable recording of reconciliation runs and findings
- control evidence that operators can review without re-running calculator logic manually

This makes the service an independent verifier, not another calculator stage.

## Current scope and evidence

This page covers the reconciliation controls implemented by
`financial_reconciliation_service`. Control definitions, persistence models, and the reconciliation
contract tests are the evidence; a successful run is control evidence for the requested scope, not
an independent certification or downstream analytics conclusion.

## Reader Map

| Reader need | Start with |
| --- | --- |
| Understand controls | What it handles |
| Run a check | Runtime role and scope parameters |
| Investigate findings | Durable evidence and Operations Runbook |

## Runtime role

For a requested reconciliation scope, the service:

1. accepts a deterministic run request for a portfolio or business-date scope
2. loads the relevant persisted core data for the requested control type
3. recomputes or cross-checks the expected invariant
4. records a durable reconciliation run result
5. persists any findings with portfolio, security, transaction, date, and epoch context

Automatic portfolio-day requests also carry the durable `aggregation_revision` assigned by the
lease-fenced aggregation job. Run identity includes reconciliation type, portfolio, business date,
epoch, and aggregation revision. A newer revision replaces same-epoch control status; an older or
identical revision cannot overwrite or republish it, and contradictory outcomes for one revision
fail closed. Legacy events deserialize as revision `0`, preserving their existing dedupe identity.

The current control families cover:

- `transaction_cashflow`
  every transaction that should have a cashflow row has one aligned persisted cashflow
- `position_valuation`
  valued snapshots remain arithmetically consistent with quantity, price, and cost basis
- `timeseries_integrity`
  portfolio timeseries remain consistent with the underlying position-timeseries inputs
- `corporate_action_bundle_a`
  linked transfer-style child legs reconcile source basis against retained target, fractional,
  cash-consideration, and governed-adjustment basis and expose missing dependency references

## Data it owns

Primary durable outputs include:

- `financial_reconciliation_runs`
- `financial_reconciliation_findings`
- control evidence surfaced through reconciliation APIs

Finding rows also persist accountable owner, governed resolution state, terminal actor/timestamp
evidence, finite tolerance and observed delta where value-based, and a bounded repair recommendation.
QCP reconciliation routes expose deterministic evidence identities, open-break severity counts,
evidence age, and fail-closed publication gates. The run-list gate blocks incomplete paged evidence
windows. This release does not claim an operator command for transitioning findings into terminal
resolution states.

The persisted run `summary` is immutable completion-time history. Operator-facing current counts,
per-run status, top blocking finding, and publication gate come from finding lifecycle state at the
response timestamp. `RESOLVED`, `WAIVED`, and `SUPPRESSED` findings remain auditable without staying
open; a resolution committed after the response timestamp appears only in the next snapshot.

When multiple trust states contribute to one response, Core applies the shared precedence
`BLOCKED > STALE > UNKNOWN > UNRECONCILED > BREAK_OPEN > PARTIAL > COMPLETE`. Blank or unrecognized
states fail closed as `UNKNOWN`. Run and finding evidence are reduced together, so a warning cannot
hide a stale run and a stale-only page remains visibly `STALE`.

Run and support responses expose `aggregation_revision` so operators can join the aggregate input
generation to its independent control calculation and published control decision.

These outputs feed:

- operator review and triage
- portfolio-day control evaluation
- replay and remediation decisions
- production support evidence

## Why it matters

If reconciliation is missing or weak:

- downstream consumers can treat partial or drifted state as authoritative
- calculator success alone can be mistaken for end-to-end correctness
- support teams lose an independent way to detect ledger-to-cashflow, valuation, or aggregation
  drift

That is why reconciliation exists as a separate control plane instead of being buried inside the
calculators it evaluates.

## Boundary rules

- calculators and generators remain owners of their own persisted domain state
- reconciliation service owns independent verification and finding persistence
- reconciliation findings may trigger operational action, but they do not mutate calculator-owned
  data directly
- bond valuation controls require a `SUPPORTED` valuation receipt; a missing or
  `LEGACY_UNSCOPED` receipt creates `missing_bond_quote_authority` and never invokes magnitude-based
  quote scaling
- downstream analytics and reporting may consume the evidence, but core owns the control execution

## Operational hints

Check this service when:

- core APIs look populated but operators need confidence that outputs are internally consistent
- transaction-to-cashflow drift is suspected
- valuation arithmetic looks implausible despite completed upstream jobs
- `missing_bond_quote_authority` is open; route it to `VALUATION_OPERATIONS` and apply the
  `ASSIGN_VALUATION_QUOTE_POLICY` repair for the exact book/security/effective date
- portfolio timeseries appears partially aggregated or inconsistent with underlying positions
- a Bundle A corporate action has a basis mismatch, insufficient source/target legs, or missing
  child-leg dependency references

For Bundle A issues, list reconciliation runs with `reconciliation_type=corporate_action_bundle_a`
and inspect both the immutable run `summary` and the run's current findings. The summary identifies
the policy/version, source basis, incoming and retained target basis, fractional basis,
cash-consideration basis, governed adjustment posture, net delta, excluded governed upstream
settlement adjustments,
unsupported adjustments, and canonical per-child input lineage. Retained target basis is incoming
target basis less basis consumed by an explicit cash-in-lieu leg; do not add fractional basis to
incoming target basis a second time. A fractional allocation greater than incoming target basis is
invalid even when the resulting conservation delta is zero. For multi-target events, this check is
performed for each linked target instrument as well as in aggregate; excess basis on one target
cannot conceal a negative retained allocation on another. Governed upstream settlement
adjustments are excluded only when their originating type and reason form the exact governed pair,
their link type matches that originating type, and their originating transaction resolves
unambiguously to a matching-type transaction in the current reconciliation cohort. The shared
upstream cash-pair policy must also prove reciprocal identity and matching portfolio,
economic-event, and linked-group scope. Missing, external, duplicate, type-mismatched, or
scope-mismatched origins remain unsupported
adjustments.

Stable finding types are
`ca_bundle_a_basis_mismatch`, `ca_bundle_a_insufficient_cash_basis`,
`ca_bundle_a_insufficient_legs`, `ca_bundle_a_invalid_basis_allocation`,
`ca_bundle_a_unsupported_adjustment`, `ca_bundle_a_missing_dependency`, and
`ca_linked_leg_mismatch`; each row includes the portfolio, triggering transaction,
business date, correlation id through the run, linked transaction group, parent event reference,
reason code, and source-safe observed values for triage.

Treat aggregate status as the run's deterministic primary posture, not as a one-finding limit.
Independently counted defects coexist in the same immutable evidence set: a non-zero missing-cash
or unsupported-adjustment count has exactly one matching finding even when incomplete legs,
invalid allocation, or another higher-priority status is present. Finding order is stable, and the
summary's finding/error counts are derived from the emitted rows.

Check beyond this service when:

- the source data is missing before any control run could validate it
- a calculator stage has already failed clearly and the problem is not independent verification

## Related references

- [System Data Flow](System-Data-Flow)
- [Operations Runbook](Operations-Runbook)
- [Troubleshooting](Troubleshooting)
- [Lotus Core Microservice Boundaries and Trigger Matrix](../docs/architecture/microservice-boundaries-and-trigger-matrix.md)
