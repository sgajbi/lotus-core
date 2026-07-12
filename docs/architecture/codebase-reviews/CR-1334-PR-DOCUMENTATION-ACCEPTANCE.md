# CR-1334 PR Documentation Acceptance

## Scope

Issue cluster: GitHub issue #623.

## Objective

Make documentation impact review an explicit PR acceptance requirement without adding another broad
context page. The checklist must force either updated source-of-truth documentation or a concrete
no-doc-change rationale, and CI must guard the checklist from drifting.

## Changes

1. Expanded `.github/pull_request_template.md` with a documentation acceptance checklist covering
   README, architecture docs, API catalog/OpenAPI/vocabulary, RFCs, runbooks, supported-features,
   wiki source, repository context, platform context, and no-doc-change rationale.
2. Added wiki publication planning to the PR template for repo-local `wiki/` changes.
3. Added a workflow-governance unit test that fails if the PR template drops the required
   documentation acceptance terms.
4. Added a concise repo-context rule pointing agents to the checklist and evidence requirement.

## Behavior And Compatibility

No runtime behavior, route path, request DTO, response DTO, OpenAPI schema, database schema, Kafka
contract, metric, deployment topology, package import path, or public API behavior changed.

The existing Quality Baseline workflow already runs the workflow-governance gate and wiki docs gate
on pull requests. This slice extends that governance signal to prove the PR template carries the
documentation acceptance checklist.

## Validation Evidence

Focused local validation:

1. `python -m pytest tests/unit/test_ci_workflow_action_versions.py -q`
2. `make quality-workflow-governance-gate`
3. `python scripts/wiki_validation_guard.py`
4. `git diff --check`

## Documentation, Wiki, Context, And Skill Decision

Updated the PR template, repo-local context, and codebase-review ledger because repository process
truth changed.

No wiki source update is required because this slice changes repository PR governance, not
operator-facing runtime guidance or published product documentation. The PR template now requires
post-merge wiki publication evidence when future slices do change `wiki/`.

No platform skill source change is required. The existing Lotus skill-context guidance already
prefers compact checklists, deterministic validation, and no-change decisions over passive prose.

## Remaining Work

GitHub issue #623 is locally fixed for PR documentation acceptance checklist coverage and a
workflow-governance validation signal pending PR CI/QA and issue closure.
