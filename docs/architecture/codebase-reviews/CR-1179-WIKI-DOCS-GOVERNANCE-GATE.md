# CR-1179 Wiki Docs Governance Gate

## Objective

Begin GitHub issue #619 by adding a fast, repo-native validation gate for authored wiki source
quality and publication readiness.

## Expected Improvement

- `_Sidebar.md` links must resolve to existing wiki pages.
- Publishable wiki pages must be linked from the sidebar so operator truth is not stranded.
- Wiki page filenames and first headings must be publication-safe.
- Local relative links from wiki pages to docs, source, scripts, tests, and quality artifacts must
  resolve before merge.
- Optional published-wiki parity checks can compare authored `wiki/` source with a generated or
  cloned publication target when that target is available.
- Quality Baseline gains a cheap documentation guard that does not require Docker or service
  runtime bring-up.

## Changes

- Added `scripts/wiki_validation_guard.py`.
- Added `make quality-wiki-docs-gate`.
- Added `Quality Baseline / Wiki Docs Gate` to `.github/workflows/quality-baseline.yml`.
- Added unit coverage for complete wiki source, missing sidebar targets, orphan pages, broken
  relative links, unsafe names, missing H1 headings, publication parity drift, and workflow wiring.
- Updated `wiki/Validation-and-CI.md` with the gate purpose, remediation path, and optional
  published-wiki parity command.

## Compatibility

No product API, OpenAPI route, runtime behavior, database schema, Kafka contract, or domain model
changed. This is a CI/documentation governance change only.

## Validation

- `python scripts/wiki_validation_guard.py`
- `make quality-wiki-docs-gate`
- `python -m pytest tests/unit/scripts/test_wiki_validation_guard.py tests/unit/test_ci_workflow_action_versions.py -q`
- `python -m ruff check scripts/wiki_validation_guard.py tests/unit/scripts/test_wiki_validation_guard.py tests/unit/test_ci_workflow_action_versions.py`
- `python -m ruff format --check scripts/wiki_validation_guard.py tests/unit/scripts/test_wiki_validation_guard.py tests/unit/test_ci_workflow_action_versions.py`

## Documentation And Wiki Decision

Updated this ledger entry, quality scorecard/health report, and repo-local Validation and CI wiki
source because documentation governance changed.

## Follow-Up

Issue #619 remains open pending PR review, GitHub CI evidence, and a platform-side wiki publication
workflow that can provide a real published-wiki clone/path for parity checks after merge.
