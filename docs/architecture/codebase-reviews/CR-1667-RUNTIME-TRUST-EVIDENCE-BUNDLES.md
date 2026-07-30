# CR-1667: Runtime Trust-Evidence Bundles

## Scope

Issues `#453`, `#454`, and `#455` were reviewed as one bounded RFC-0083 runtime-trust batch:

1. deterministic portfolio-product reconstruction identity,
2. job-scoped ingestion evidence,
3. reconciliation and data-quality evidence sufficient for downstream gating.

The review also searched the same source-batch defect pattern across Query Service and QCP.

## Findings

1. Several runtime products exposed response content hashes as `source_batch_fingerprint`, creating
   upstream authority that Core could not prove.
2. `TransactionLedgerWindow` had no non-null, page-invariant reconstruction identity.
3. the catalog name `IngestionEvidenceBundle` described several portfolio support listings but no
   canonical ingestion-job aggregate,
4. reconciliation findings lacked durable owner, resolution, tolerance/delta, and repair evidence,
5. reconciliation run-list publication posture could appear safe when only a partial page had been
   examined.

## Resolution

1. A recursive contract guard rejects response/content hashes used as source-batch identity. All
   in-scope fabricated values were removed, and the obsolete helper override was deleted.
2. Typed reconstruction-scope evidence now binds product, portfolio, date, policy, current
   restatement version, qualifiers, and material evidence. Transaction identity is invariant across
   pages; established PortfolioStateSnapshot and Holdings identifiers remain unchanged.
3. `GET /ingestion/jobs/{job_id}/evidence` publishes `IngestionEvidenceBundle:v1` from the canonical
   job, failure, replay-audit, retained-payload, and consumer-DLQ stores. It exposes explicit
   completeness and fail-closed gating. Generic DLQ processing failures are not quarantine, and a
   queued retry is not completed repair.
4. Alembic revision `c132b2c3d505` adds reconciliation finding owner, governed lifecycle state,
   terminal actor/time evidence, exact finite tolerance/delta, repair recommendation, constraints,
   backfills, and a lifecycle query index.
5. QCP publishes deterministic `ReconciliationEvidenceBundle:v1` and
   `DataQualityCoverageReport:v1` evidence with counts, age/threshold, source references, and
   fail-closed publication posture. Incomplete reconciliation run pages block.

## Compatibility And Boundaries

The changes are additive except for removing fabricated batch values, which now correctly return
null under the existing nullable contract. Existing stronger snapshot-id formats and product
versions are preserved. No tenant authority is claimed under open issue `#798`.

Runtime restatement selection remains `current`; there is no persisted restatement selector. Core
also has no durable bookkeeping-repair completion audit and no operator command for terminal
reconciliation finding transitions. Accordingly, runtime does not claim those outcomes. These are
explicit non-goals of the three evidence-publication issues, not hidden completion claims.

## Validation Evidence

1. combined focused runtime/contract cohort: `329 passed`,
2. reconstruction integration cohort: `138 passed`,
3. reviewed incomplete-page regression: `6 passed`,
4. Ruff check and format: passed for changed Python,
5. source-data product contract guard: passed,
6. domain-data product contract validation: passed,
7. Alembic SQL contract: single head `c132b2c3d505`,
8. financial numeric persistence guard: `98` Numeric columns across `31` tables, all `98`
   ORM-enforced,
9. `git diff --check`: passed.

Full pre-merge and GitHub CI evidence belongs on the PR and linked issues.

## Durable Guidance Decision

The repeatable defect is enforced in repository-native automation, while product-specific runtime
truth is recorded in the RFC-0083 target models, repository engineering context, and authored wiki.
No new Lotus-wide skill or platform context copy is needed: existing delivery, CI, pre-merge,
review-ledger, issue-resolution, skill-context, and wiki governance already route this work. This
avoids duplicating implementation detail into central agent guidance.
