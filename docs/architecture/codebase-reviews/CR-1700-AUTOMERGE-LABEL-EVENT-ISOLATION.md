# CR-1700 - Automerge Label Event Isolation

Date: 2026-08-21
Status: Fixed locally; live labeled-event, protected PR, exact-main, and wiki proof pending
Issue: #969

## Finding

The full Pull Request Merge Gate subscribed to the `labeled` event even though label-driven queue
ownership belongs to the smaller PR Auto Merge workflow. Adding `automerge` at an unchanged head
therefore started a second full gate and, because the gate intentionally cancels prior PR-ref work,
discarded already completed and in-flight evidence for the same immutable source.

## Resolution

1. The full PR gate now subscribes only to `opened`, `synchronize`, `reopened`, and
   `ready_for_review`.
2. PR Auto Merge retains `labeled` and remains the sole workflow that interprets the `automerge`
   label.
3. Workflow contract tests bind both exact event sets and retain the PR-ref concurrency rule that
   cancels stale work when `synchronize` publishes a new head.
4. Repository context, CI strategy, and authored wiki truth distinguish metadata authority from
   code authority so the duplicate trigger cannot return unnoticed.

## Compatibility And Scope

Required checks, test shards, thresholds, exact-main validation, rebase auto-merge, and stale-head
cancellation are unchanged. The only intentional behavior change is that applying a label no longer
starts or cancels the full PR gate. Broader ready-for-review reuse, changed-surface selection, and
warning/unit/coverage artifact reuse remain under #749. There is no runtime, API, OpenAPI, schema,
event, dependency, image, domain, or calculation change.

## Validation Evidence

- 29 workflow-governance tests passed, including exact event-routing and concurrency contracts.
- Scoped Ruff lint and formatting plus diff hygiene passed.
- `make quality-wiki-docs-gate` and the changed-page wiki quality audit passed.
- The implementation PR must add `automerge` while its original full-gate run is active and record
  that only PR Auto Merge is triggered, the full-gate run ID remains unchanged, and all existing
  exact-head checks continue.
- Protected PR, exact-main, wiki publication/parity, issue-loop closure, and worktree cleanup remain
  pending and must be reconciled here before #969 closes.

## Governance Decision

This is a repository-local workflow correction. Existing Lotus CI and premerge skills already
require exact-head evidence, async monitoring, stable required checks, and fail-closed validation;
no new skill is required. Cross-repository lifecycle-event and artifact reuse remains the broader
#749 program rather than being inferred from this bounded Core fix.
