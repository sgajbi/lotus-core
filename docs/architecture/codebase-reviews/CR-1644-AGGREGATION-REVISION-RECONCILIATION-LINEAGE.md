# CR-1644 Aggregation Revision Reconciliation Lineage

## Status

Fixed locally; retained-runtime, PR, mainline, and wiki publication proof pending.

## Scope

GitHub issue #809: make canonical portfolio-derived-state and financial-control queues converge
without weakening calculation correctness, replay safety, or audit lineage.

## Finding

Retained-volume evidence proved that aggregation completion identity stopped at
`(portfolio_id, business_date, epoch)` even when the same durable aggregation job was materially
reopened and completed again:

- `12,335` `FinancialReconciliationRequested` outbox rows represented only `4,365` distinct
  portfolio/date/epoch scopes;
- individual scopes emitted up to `39` requests;
- `13,092` system-pipeline reconciliation runs represented `4,364` unique three-control bundles,
  with zero duplicate non-null dedupe keys;
- `portfolio_aggregation_jobs.attempt_count` already persisted the fenced, monotonic claim
  generation, reached `42` for the most-reprocessed row, and was discarded before event staging;
- duplicate requests reused the first run bundle but still locked and rewrote control evidence and
  staged completion/control events.

This was both queue amplification and a correctness defect. A later material aggregation could be
acknowledged using the first calculation result, while a blocking status merged within the epoch
could never be cleared by a newer, corrected aggregate.

## Remediation

1. Treat the existing positive aggregation-job `attempt_count` as the durable
   `aggregation_revision` for each successful fenced claim.
2. Propagate that revision through portfolio aggregation completion and financial reconciliation
   request events. The additive event fields default to `0` so retained legacy messages continue to
   deserialize and preserve their original dedupe keys.
3. Persist `aggregation_revision` on `financial_reconciliation_runs` and the
   `FINANCIAL_RECONCILIATION` control row through reversible migration `c117b2c3d4f6`.
4. Dedupe new automatic runs by reconciliation type, portfolio, business date, epoch, and
   aggregation revision. Each materially new revision is calculated once; legacy revision `0`
   retains the pre-migration identity.
5. Replace control status only when a higher revision arrives. Ignore an older revision, make an
   identical same-revision redelivery a true no-op, and fail closed when one revision reports
   contradictory outcomes.
6. Stage reconciliation-completed and controls-evaluated events only for an accepted revision, and
   carry the revision in both event payloads.
7. Expose the persisted revision on financial-reconciliation and Query Control Plane run responses,
   including the support overview's latest-reconciliation lineage.
8. Remove the obsolete severity-merge policy; revisions, not arrival-time severity, now decide which
   same-epoch control result is authoritative.

## Compatibility

The change is additive for event and HTTP consumers. Existing route paths, request contracts,
portfolio epoch meaning, topic names, partition keys, consumer groups, and legacy dedupe keys are
preserved. Manual reconciliation runs may keep a null aggregation revision. No debounce, partition
increase, consumer-group reset, broad Docker cleanup, or reinterpretation of historical run rows is
introduced.

## Validation

- `315` warning-strict affected unit tests passed, including financial reconciliation,
  portfolio-derived-state, Query Control Plane, event, API, and migration contracts.
- Migration SQL contract passed with one Alembic head at `c117b2c3d4f6`.
- Rebuilt isolated PostgreSQL proof passed `7` tests in `499.44s`, covering upgrade application,
  newer-revision replacement, duplicate no-op, conflicting same-revision fail-closed behavior,
  older-revision suppression, latest-epoch behavior, and concurrent run dedupe.
- A cached exact-source PostgreSQL rerun passed the same `7` tests in `77.78s`, including the final
  persisted-revision assertion on the concurrently deduplicated run.
- Query Control Plane repository/application and both OpenAPI surfaces passed.
- Full repository lint and strict MyPy passed, together with architecture, event-contract,
  API-vocabulary, docs/wiki, migration, RFC-0083, and `git diff --check` gates.

## Remaining evidence

Rebuild only the affected retained-stack services after the inherited legacy queue drains, apply the
migration, and prove one new material revision creates exactly one three-control bundle and one
downstream control decision while an unchanged retained restart creates none. Then complete #809's
fresh 900-second canonical certification, PR gates, exact-main validation, wiki publication, and
verified issue closure.
