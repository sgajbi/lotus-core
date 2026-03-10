# Codebase Review Playbook

## Purpose

This playbook defines how `lotus-core` is reviewed for maintainability, correctness,
performance, and production hardening.

The goal is not a one-off cleanup. The goal is a durable engineering process with:

- explicit review scopes
- repeatable review criteria
- evidence-based sign-off
- a persistent ledger of what has been reviewed and what remains open

The companion ledger is:

- [CODEBASE-REVIEW-LEDGER.md](./CODEBASE-REVIEW-LEDGER.md)

## Review principles

1. Review by pattern first, not by directory first.
2. Every meaningful finding must be classified:
   - stale code
   - duplication
   - modularity problem
   - query/performance risk
   - correctness or race-condition risk
   - observability gap
   - test gap
   - documentation drift
3. If a behavior is relied upon in production or E2E, it must be pushed down into lower-level tests.
4. Sign-off requires evidence, not opinion.
5. “No known issue found” is a valid outcome, but it still requires an explicit ledger entry.

## Review unit

Use one of these review units:

1. Pattern review
- best default
- examples:
  - async orchestration and state transitions
  - replay/idempotency/fencing
  - duplicate repository logic
  - heavy DB query shapes
  - consumer runtime startup/shutdown behavior
  - OpenAPI/example consistency

2. Domain review
- use when a domain boundary is cohesive and owned as one unit
- examples:
  - cashflow calculator
  - valuation pipeline
  - query/control-plane split

3. File review
- use only when a high-risk file is the real unit of concern
- examples:
  - a single repository with complex eligibility SQL
  - a scheduler or consumer manager with race-prone logic

## Status model

Each ledger row uses one of:

- `Not Started`
- `In Review`
- `Refactor Needed`
- `Hardened`
- `Signed Off`
- `Archived`

Use them precisely:

- `Refactor Needed` means the review found material issues that are not yet fully addressed.
- `Hardened` means implementation changes landed and validation evidence exists, but long-term convergence or broader rollout may still remain.
- `Signed Off` means the current scope is complete for now and any residual items are either explicitly deferred or judged non-blocking.

## Required fields for each review entry

Every ledger entry must capture:

- review id
- review date
- owner
- scope/pattern
- systems/files touched
- current status
- findings summary
- actions taken
- required follow-up
- evidence:
  - commits
  - tests
  - reports
  - PRs

## Review checklist

Apply the following checklist to every scope.

### 1. Architecture and ownership

- Is responsibility clear?
- Is code duplicated across services?
- Is the current split justified by runtime behavior and ownership?
- Are internal and external control-plane concerns clearly separated?

### 2. Runtime correctness

- Are state transitions monotonic where required?
- Can duplicate delivery or replay corrupt state?
- Are stale events safely ignored or fenced?
- Are long-running jobs recoverable after interruption?
- Is the system robust to late-arriving same-day inputs?

### 3. Database and query quality

- Are queries correctly correlated?
- Are there accidental cross joins or full-table scans in hot paths?
- Is `FOR UPDATE SKIP LOCKED` used correctly where workers compete?
- Are count/aggregation queries bounded and index-friendly?
- Are duplicated query implementations likely to drift?

### 4. Observability and operations

- Can operators tell whether the system is blocked, draining, or stuck?
- Are health endpoints meaningful?
- Are failure-recovery reports and thresholds actionable?
- Is there a canonical view of backlog/lag/recovery state?

### 5. Test coverage

- Is the failure mode only covered by E2E today?
- Can the invariant be expressed as:
  - unit test
  - repository/query-shape test
  - DB-backed integration test
  - targeted E2E
- Are tests asserting the business-complete state rather than an intermediate async side effect?

### 6. Documentation and RFC traceability

- Does the RFC reflect reality?
- Are runbooks or architecture docs stale?
- Is the implementation evidence linked?

## Review workflow

1. Choose review scope.
2. Create or update a ledger entry with `In Review`.
3. Inspect code and tests for the pattern.
4. Record findings before changing code.
5. Fix the issues in small slices.
6. Add lower-level tests for each important discovered invariant.
7. Run the smallest meaningful validation first.
8. Run heavy gates only after the lower-level contract is in place.
9. Update the ledger:
   - findings
   - actions taken
   - evidence
   - final status

## Initial high-priority review queue

1. Duplicate repository/service logic
2. Async orchestration, quiescence, and stage transitions
3. Replay/idempotency/fencing correctness
4. DB query shape and indexing in hot scheduler paths
5. Consumer runtime lifecycle and shutdown behavior
6. Failure-recovery and heavy-gate scripts
7. Query/control-plane overlap and drift
8. OpenAPI/example consistency

## Sign-off standard

A review scope is only `Signed Off` when:

- known material defects in that scope are fixed
- the relevant lower-level tests exist
- the heavy validation signal relevant to that scope is green
- the ledger records concrete evidence

If any of those is missing, do not mark it `Signed Off`.
