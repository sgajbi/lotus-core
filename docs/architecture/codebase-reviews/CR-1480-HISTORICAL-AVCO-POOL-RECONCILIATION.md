# CR-1480: Historical AVCO Pool Reconciliation

Date: 2026-07-10
Issue: #468
Status: Hardened locally; production-estate execution pending

## Objective

Reconstruct trustworthy AVCO aggregate and source-lot state for portfolios processed before durable
pool checkpoints existed, without trusting potentially stale source rows or publishing duplicate
business events.

## Architecture

The target transaction-processing package owns a framework-neutral reconciliation use case:

```text
Operator CLI / Make target
  -> ReconcileAverageCostPoolsUseCase
  -> AverageCostPoolReconciliationPort
  -> SQLAlchemy reconciliation adapter
  -> CostCalculationWorkflow deterministic history replay
  -> CostCalculatorRepository bounded bulk persistence
  -> PostgreSQL
```

Candidates are AVCO portfolio/security keys with canonical lot-opening transactions. Listing uses
deterministic portfolio/security keyset order and a bounded limit of 1-1,000. Each key runs in its
own database transaction, so one invalid history does not roll back successful independent keys.

Dry-run is the default. It replays canonical transaction history and compares independently derived
expected source count, quantity, local basis, and base basis with both `position_lot_state` and
`average_cost_pool_state`. Equal-but-stale pool/source totals cannot be classified current.

Apply mode first closes prior derived rows for the key, then bulk-upserts every canonical opening
source in chunks of 500, including missing rows and fully closed lineage. It writes the aggregate
pool and ordering checkpoint, rereads persisted totals, and commits only when source count and all
three financial aggregates exactly match replay truth. Certification failure rolls the key back.
No cost, cashflow, position, idempotency, or outbox event is emitted by this maintenance use case.

## Operator Contract

Audit a bounded page:

```bash
make audit-average-cost-pools AVCO_RECONCILIATION_ARGS="--limit 100 --output output/avco-audit.json"
```

Apply a reviewed scope:

```bash
make reconcile-average-cost-pools AVCO_RECONCILIATION_ARGS="--portfolio-id PORTFOLIO_ID --limit 100 --output output/avco-apply.json"
```

Use returned `next_cursor.portfolio_id` and `next_cursor.security_id` as
`--after-portfolio-id`/`--after-security-id` for the next page. Dry-run exits `1` when drift is
present; apply/dry-run exits `2` for a failed key; current or successfully reconciled pages exit `0`.
Reports carry schema version, UTC generation time, mode, bounded summary, exact Decimal strings,
per-key reason codes, and resume cursor. They do not contain credentials or connection strings.

## Validation And Compatibility

- 19 application/composition/CLI tests passed for bounds, ordering, resume, dry-run/apply, exact
  replay comparison, output, and exit codes;
- 40 repository/checkpoint tests passed for bounded bulk SQL and persisted aggregate reads;
- two PostgreSQL scenarios passed in 58.85 seconds, proving legacy stale-row repair, missing-pool
  creation, exact source/pool/order checkpoints, idempotent rerun, and rollback after writes;
- the existing ordered AVCO path and downstream source-lot contract are unchanged.

This is an additive maintenance capability. It does not alter APIs, events, Kafka ownership,
financial formulas, cashflow classification, position methodology, or tax-lot response shape.

## Remaining Work

Run dry-run against the production-like historical estate, review every failed/drifted key, execute
approved bounded apply pages, retain reports as release evidence, and rerun source-product
supportability certification. Deployed query plans, lock contention, p50/p95/p99, pool use, lag,
recovery, and drain evidence remain before #468 runtime cutover.
