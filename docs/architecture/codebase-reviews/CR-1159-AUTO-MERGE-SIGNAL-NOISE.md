# CR-1159 Auto-Merge Signal Noise

Date: 2026-06-22

## Scope

Review and harden the PR auto-merge workflow signal for `lotus-core`.

## Finding

The `PR Auto Merge` workflow triggered on events where the `automerge` label could be absent. The
job-level guard correctly prevented merge queueing without the label, but GitHub represented that
as a skipped `Queue Auto Merge` check run on the pull request. Those stale skipped contexts made
GitHub's PR rollup noisy during merge closure even when the protected PR Merge Gate contexts were
green.

## Change

Removed the `unlabeled` trigger from `.github/workflows/pr-auto-merge.yml` and moved the
`automerge` label check from the job-level `if` expression into the queue script. The workflow
still runs for opened, reopened, synchronized, ready-for-review, and labeled pull requests, but an
absent label now exits successfully as an explicit no-op instead of creating a skipped job. The
script still requires the explicit `automerge` label before it calls
`gh pr merge --auto --rebase --delete-branch`.

Added a workflow-governance unit test that rejects reintroducing `unlabeled` into the auto-merge
workflow and proves absent-label handling remains an explicit no-op.

## Behavior And Risk

This does not weaken branch protection or merge requirements. Removing or omitting the label now
simply stops auto-merge queue attempts without creating a non-actionable skipped check. Re-adding
the label remains the explicit opt-in path for queueing auto-merge.

## Evidence

Local validation:

- `python -m pytest tests/unit/test_ci_workflow_action_versions.py -q`
- `python -m ruff check tests/unit/test_ci_workflow_action_versions.py`
- workflow YAML parse check for `.github/workflows/pr-auto-merge.yml`
