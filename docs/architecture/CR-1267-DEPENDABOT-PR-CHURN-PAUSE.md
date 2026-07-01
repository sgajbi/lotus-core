# CR-1267 Dependabot PR Churn Pause

Date: 2026-07-01

## Objective

Pause routine Dependabot version-update pull requests while the governed issue-closure PR is raised
and stabilized. The goal is to stop failing or behind bot PRs from competing with the closure PR
without hiding supply-chain coverage truth.

## Change

- Set each `.github/dependabot.yml` `open-pull-requests-limit` to `0` for GitHub Actions, Python,
  and Docker ecosystems.
- Kept all configured manifest and Dockerfile directories in place so coverage remains reviewable.
- Updated the Dependabot coverage test to prove routine PR churn is intentionally disabled.
- Updated repository context with the operating rule: cherry-pick reviewed bot suggestions into
  governed dependency or CI slices with local gates.

## Current Bot PR Handling

Open Dependabot PRs #688 and #689 are behind `main` and have failing checks. They should not be
merged directly into the issue-closure PR. Useful dependency or workflow updates from those PRs
should be reviewed and cherry-picked later as explicit dependency/CI slices with focused evidence.

## Validation Evidence

- `python -m pytest tests/unit/test_dependabot_security_coverage.py -q`: passed.
- `python -m ruff check tests/unit/test_dependabot_security_coverage.py`: passed.
- `python -m ruff format --check tests/unit/test_dependabot_security_coverage.py`: passed.

## Downstream Compatibility

No runtime code, product API, database schema, OpenAPI schema, Kafka topic, or business behavior
changed. This affects only automated dependency PR creation.

## Documentation And Wiki Decision

Updated this architecture record, the codebase review ledger, and repository engineering context.
No wiki change is required because this is an internal GitHub automation posture change rather than
operator-facing product behavior.
