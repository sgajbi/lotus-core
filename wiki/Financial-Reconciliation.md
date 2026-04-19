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
- durable recording of reconciliation runs and findings
- control evidence that operators can review without re-running calculator logic manually

This makes the service an independent verifier, not another calculator stage.

## Runtime role

For a requested reconciliation scope, the service:

1. accepts a deterministic run request for a portfolio or business-date scope
2. loads the relevant persisted core data for the requested control type
3. recomputes or cross-checks the expected invariant
4. records a durable reconciliation run result
5. persists any findings with portfolio, security, transaction, date, and epoch context

The current control families cover:

- `transaction_cashflow`
  every transaction that should have a cashflow row has one aligned persisted cashflow
- `position_valuation`
  valued snapshots remain arithmetically consistent with quantity, price, and cost basis
- `timeseries_integrity`
  portfolio timeseries remain consistent with the underlying position-timeseries inputs

## Data it owns

Primary durable outputs include:

- `financial_reconciliation_runs`
- `financial_reconciliation_findings`
- control evidence surfaced through reconciliation APIs

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
- downstream analytics and reporting may consume the evidence, but core owns the control execution

## Operational hints

Check this service when:

- core APIs look populated but operators need confidence that outputs are internally consistent
- transaction-to-cashflow drift is suspected
- valuation arithmetic looks implausible despite completed upstream jobs
- portfolio timeseries appears partially aggregated or inconsistent with underlying positions

Check beyond this service when:

- the source data is missing before any control run could validate it
- a calculator stage has already failed clearly and the problem is not independent verification

## Related references

- [System Data Flow](System-Data-Flow)
- [Operations Runbook](Operations-Runbook)
- [Troubleshooting](Troubleshooting)
- [Lotus Core Microservice Boundaries and Trigger Matrix](../docs/architecture/microservice-boundaries-and-trigger-matrix.md)
