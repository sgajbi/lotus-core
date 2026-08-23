# CR-1709 Governed Required Status Checks

Date: 2026-08-23

Status: Fixed locally and live branch protection reconciled; protected PR refresh, exact-main
validation, wiki publication/parity, issue closure, and branch/worktree hygiene remain pending.

Issue: #999

## Finding

Branch protection required 18 contexts while Pull Request Merge Gate published five additional
blocking jobs/suites and Quality Baseline published 14 jobs named `... Gate`. Auto-merge therefore
could merge an exact head whose documented transaction, database-lifecycle, recovery, app-level,
import-boundary, security, dead-code, complexity, API-governance, or documentation gate was red.
Check names, documentation, local commands, and live enforcement were separate mutable truths.

## Financial-System Invariant

A protected merge is release evidence for a financial system of record. Every check described as
blocking must be technically non-bypassable for the exact source head, must be bound to the
expected check producer, and must remain reproducible from repository-owned authority. Advisory
evidence must be explicit and cannot be mistaken for release authorization.

## Design

1. `contracts/ci/required-status-checks.v1.json` owns strict mode, repository/branch identity,
   workflow policy, the one advisory context, and 37 sorted `(context, app_id)` requirements. The
   guard pins repository/branch authority to canonical `sgajbi/lotus-core` / `main`; manifest edits
   cannot redirect live certification to another protection target.
2. `required_status_checks_guard.py` validates the closed manifest shape, expands matrix suites,
   classifies every governed workflow job, requires blocking jobs and enforcement commands to be
   unconditional and fail-propagating, limits conditional auxiliary steps to audited checkout,
   cache-save, and artifact-upload actions, requires every blocking job to retain at least one
   unconditional substantive command or explicitly approved enforcement action, inventories advisory producers in global
   context-uniqueness checks, scans every
   repository workflow for static or dynamic required-context collisions, rejects unsupported
   job-name expressions, requires every manifest entry to bind to the exact GitHub Actions
   application ID `15368`, and compares exact sets. New, renamed, skipped, failure-tolerant,
   advisory-colliding, or impersonated jobs cannot silently authorize merge.
3. Live verification requires GitHub's app-bound `checks` response, not legacy context strings.
   Missing, stale, wrong-app, malformed, or non-strict protection fails closed.
4. `make lint` now includes both import-boundary and manifest/workflow enforcement. The focused
   workflow-governance target includes mutation-style manifest tests.
5. Main Releasability performs the live comparison read-only. Repository history (CR-1087) proves
   `github.token` lacks branch-protection read authority, so the workflow requires a dedicated
   fine-grained `LOTUS_BRANCH_PROTECTION_READ_TOKEN` with Administration read-only permission.
   A broad personal token is not an acceptable substitute.
6. Live branch protection is reconciled only after the exact PR head has posted and passed all 37
   checks. The guard's `--print-desired-protection` mode emits the exact atomic PATCH body, including
   an explicit empty legacy `contexts` array and the complete app-bound `checks` array. This avoids
   hand-copy drift, retained check-name-only authority, and making an absent context required before
   it has posted.
7. Both governed required-check workflows subscribe to `merge_group`; required Quality Baseline
   contexts therefore post on the synthetic merge-queue commit instead of deadlocking the queue.

## Meaningful Proof

Focused tests prove the repository manifest matches 37 expanded contexts, matrix values expand
deterministically, the advisory context must be both declared and observed, blocking jobs cannot
carry job-level conditions, conditional enforcement commands, or job/step failure tolerance;
only audited auxiliary actions may be conditional, and empty, auxiliary-only, or unknown-action-only
blocking jobs fail.
Advisory and blocking producers cannot
share one same-app context, and unmanaged static or dynamic workflow names cannot collide with a
required context. Non-GitHub-Actions manifest authority, noncanonical repository/branch targets,
advisory-as-required authority, and formatted or otherwise unsupported job-name expressions fail
before they can impersonate or redirect a required check. An undeclared new Gate fails before protection can drift, and live
parity rejects missing, stale, wrong-app, and wrong strict-mode authority. Workflow tests prove
import-boundary and required-check guards are reachable from `make lint`, and Main uses only the
dedicated read credential. The pre-remediation live guard characterized exactly 19 missing
contexts; after all 37 contexts passed on PR head `b4badf4f6`, branch protection was updated
atomically and live read-back passed with `strict=true`, `checks=37`.

Local feature-branch evidence:

- focused workflow/manifest pack after final review hardening: `59 passed`;
- `make lint`: passed, including repository-wide Ruff/format, import-linter, the 37-check manifest
  guard, financial/data/security/contract guards, and no warning suppression;
- `make typecheck`: `Success: no issues found in 323 source files`;
- `make architecture-guard`: passed every governed application/domain/port/adapter boundary;
- `make quality-wiki-docs-gate`: passed;
- `make docs-evidence-pack`: passed with zero failed documentation checks while the authored docs
  delta was present.

## Compatibility And Scope

No runtime application, API/OpenAPI, event/Kafka, calculation, database schema/migration,
dependency, image, datastore, or topology contract changes. CI merge authorization intentionally
becomes stricter. Change-aware lane selection (#749), umbrella auto-close (#783), and promotion of
`Quality Baseline / Report Only` remain outside this issue.

## Skills And Context Decision

No central skill change is required. `lotus-ci-enforcement-governance` already requires repository-
native guards, mutation proof, stable required-check policy, and fail-closed validation. The missing
authority was repository-local, so this slice updates the Core manifest, Make targets, workflow,
repository context, operator runbook, wiki source, review note, and ledger.

## Pending Delivery Evidence

- dedicated fine-grained branch-protection read secret provisioned;
- exact-head Feature, Quality Baseline, and Pull Request Merge Gate green;
- refreshed exact-head Feature, Quality Baseline, and Pull Request Merge Gate green after final
  review hardening;
- protected merge and exact-main live-parity success;
- wiki publication and strict parity;
- #999 QA evidence/closure and merged branch/worktree removal.
