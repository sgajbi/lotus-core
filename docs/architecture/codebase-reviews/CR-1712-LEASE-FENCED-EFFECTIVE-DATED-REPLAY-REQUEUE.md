# CR-1712 Lease-Fenced Effective-Dated Replay Requeue

Date: 2026-08-26

Status: Fixed-local candidate; protected PR review, exact-head CI, exact-main validation, issue QA,
wiki publication, and branch/worktree hygiene remain pending.

Issue: #1032

PR: #1036

## Finding

A claimed `RESET_WATERMARKS` or `RESET_FX_WATERMARKS` job could decide to retry through the generic
status writer after a correction had staged another pending row for the same security or direct FX
pair. The partial pending-row unique index rejected the claimed row's transition. If the surviving
pending sibling started later, the claimed row's earlier `earliest_impacted_date` could be lost and
the missing financial interval might never be replayed.

## Financial And Temporal Invariant

Retry must preserve the minimum authoritative effective date and required source/correlation
lineage for one replay identity. Only a worker holding the exact live token and unexpired
database-clock lease may requeue or coalesce the claimed row. Lost authority must leave both the
claim and pending sibling unchanged. Replay, rollback, and concurrent staging must converge without
weakening the pending unique indexes or deleting durable lineage.

## Design

1. `ReprocessingJobRepository` owns one effective-dated retry operation for Reset and FX work.
2. Staging and retry take the same transaction-scoped PostgreSQL advisory lock derived from a
   length-prefixed security or direct-pair identity.
3. Retry revalidates `PROCESSING`, the exact lease token, and database-clock expiry after acquiring
   the family lock.
4. Without a sibling, the claimed row returns to `PENDING`. With a sibling, existing staging policy
   coalesces the minimum replay date and lineage, then completes the superseded claimed row inside
   the same caller transaction/savepoint.
5. Typed `REQUEUED` and `COALESCED_PENDING` outcomes distinguish success from ownership loss. The
   public generic status writer accepts only ordinary `COMPLETE` and `FAILED` transitions.
6. Reset and FX callers use the repository operation. A deterministic architecture guard rejects
   another literal generic `PENDING` transition and verifies both owner paths remain wired.

## Same-Pattern Review

The production-source scan found the two issue-owned caller paths and no additional literal
`update_job_status(..., "PENDING")` bypass in the effective-dated replay family. Stale recovery now
uses a two-phase cohort claim: bounded non-locking discovery determines the complete identity set;
globally sorted advisory locks are acquired; then exact stale rows are reselected with
`FOR UPDATE SKIP LOCKED`. Keyset continuation lets concurrent pollers advance beyond a busy first
tranche, while a rolled-back savepoint releases an empty tranche's advisory locks before the next
identity set is considered. This preserves both deadlock-safe advisory-to-row ordering and disjoint
bounded recovery throughput. The guard is registered under `architecture-guard` and its exact
repository command is admitted by the governed Make recipe contract, preventing the same bypass
and CI-command drift from recurring. The existing FX staging unit identifies lock, quarantine, and
upsert statements by SQL contract instead of fragile execution position, while explicitly proving
the pair-scoped identity lock.

## Meaningful Proof

- Repository units prove direct requeue, sibling coalescing, savepoint commit/rollback, lease-loss
  classification, malformed payload failure, and rejection of generic `PENDING`. The regression
  proof also asserts that the nested transaction is started before sibling coalescing, so a
  coalescing failure can be rolled back without invalid transaction lifecycle calls.
- Application units prove both Reset and FX callers use the owned operation and cannot fall back to
  the generic writer.
- Real PostgreSQL integration tests cover earlier/equal/later siblings, correlation ownership, FX
  source lineage, stale token, repeated replay, outer rollback, no-sibling reuse, and concurrent
  staging under the identity lock. Cross-path concurrency deliberately reverses identity order and
  observes advisory-lock waiting without deadlock. A backlog larger than the 1,000-row statement
  limit proves two concurrent stale pollers claim disjoint cohorts whose union advances beyond one
  tranche.
- Guard pass/fail tests cover positional and keyword bypasses plus missing owner wiring.
- Earlier implementation-slice evidence at `bec577528269760ccf3794899c31b919767be154`:
  91 focused unit/fitness tests, 56 critical-lifecycle PostgreSQL tests, 9 explicitly selected
  real-PostgreSQL owned-requeue/coalescing tests, MyPy across 325 source files, architecture and
  wiki/docs guards, and the required-status workflow-governance suite with 529 tests and 94.27%
  branch-aware coverage.
- Final behavioral-head evidence at `8b9c754b06db472454c91eddcd8312eb281ee541`: 49 focused
  repository unit tests and all 28 tests in the affected real-PostgreSQL repository integration
  file passed. That database suite includes disjoint 1,001-row recovery, reversed multi-identity
  lock ordering, malformed timestamp isolation, timezone-less stale replay failure, and
  non-UTC-session quarantine of legacy timezone-less pending FX lineage. Ruff lint/format, MyPy on
  the changed repository module, the reprocessing transition-boundary guard, and diff hygiene also
  passed.

## Compatibility And Scope

No API/OpenAPI, schema/migration, event/Kafka, dependency, image, datastore, formula, or deployment
topology changed. Valid retry behavior intentionally changes from a uniqueness-error risk to
deterministic direct requeue or atomic coalescing. This is internal design modularity; no runtime
split is justified. Operator runbook, repository context, and authored wiki source document the
recovery semantics. Wiki publication is reserved for the validated post-merge mainline state.

## Remaining Closure

Keep issue #1032 open until PR #1036 has exact-head merge authority, rebase merge, exact-main
releasability evidence, wiki publication/parity, QA evidence, and verified branch/worktree cleanup.
