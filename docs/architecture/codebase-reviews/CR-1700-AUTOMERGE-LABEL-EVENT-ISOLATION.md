# CR-1700 - Automerge Label Event Isolation

Date: 2026-08-21
Status: Merged and exact-main validated; wiki publication and issue closure reconciliation pending
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
- `make lint`, scoped Ruff formatting, diff hygiene, and the dedicated workflow-governance gate
  passed; the latter ran all 29 workflow contract tests.
- `make quality-wiki-docs-gate` and the changed-page wiki quality audit passed. The governed
  premerge source comparison also passed at exact head `7afb476f6` from a detached worktree with
  canonical repository naming; it reported the one intentional unpublished
  `Validation-and-CI.md` source delta and no incompatible publication state.
- PR #980 added `automerge` while Pull Request Merge Gate `32468717633` was active at unchanged
  head `7afb476f6`. Only PR Auto Merge run `32468752293` started; the original full-gate and Quality
  Baseline run IDs remained unchanged, neither was cancelled, and no duplicate full gate appeared.
- The final exact head `faff89eb632c390a9a0ddac67cc0bd5624dc719d` passed Remote
  Feature Lane `32470265554`, Pull Request Merge Gate `32470268039`, Quality Baseline
  `32470268022`, and PR Auto Merge `32470267402`; PR #980 then merged by rebase as
  `d75da061c16724f2648b15bc3cef7fbc9aced20b`.
- Cumulative Main Releasability `32480746388` completed successfully at exact main
  `80be01753f86b1c6774d856f6d32efe5182056ee`. Current authored wiki publication/parity,
  issue-loop closure, and final branch/worktree cleanup remain pending and must be reconciled
  before #969 closes.

## Governance Decision

This is a repository-local workflow correction. Existing Lotus CI and premerge skills already
require exact-head evidence, async monitoring, stable required checks, and fail-closed validation;
no new skill is required. Cross-repository lifecycle-event and artifact reuse remains the broader
#749 program rather than being inferred from this bounded Core fix.
