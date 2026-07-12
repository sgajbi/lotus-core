# CR-1264 App Validation Gate Promotion

## Objective

Fix GitHub issue #443 by promoting `make lotus-core-validate` from report-only PR evidence to a
fail-closed PR Merge Gate while preserving diagnostic evidence upload.

## Expected Improvement

The slice converts a hidden soft-green failure into a reusable CI enforcement pattern:

1. the PR Merge Gate now checks out `lotus-platform` validation contracts,
2. the workflow sets `LOTUS_PLATFORM_ROOT` before running Core app validation,
3. `scripts/validate_domain_data_product_contracts.py` honors `LOTUS_PLATFORM_ROOT` while
   preserving the existing sibling-repository default,
4. the validation job no longer uses `continue-on-error`, `set +e`, warning-only handling, or
   `exit 0`,
5. workflow-governance tests now prove the app validation job is blocking and has the platform
   contract checkout it needs.

## Downstream Compatibility

No product runtime, API, OpenAPI, database schema, Kafka topic, source-data product contract, or
downstream response shape changed. The intentional behavior change is CI-only: a weak
`lotus-core-validate` run now fails the PR Merge Gate instead of uploading evidence while returning
success.

## Validation Evidence

- `gh run view 28477961040 --job 84409374086 --log`: latest successful PR Merge Gate still showed
  `make lotus-core-validate` failing internally because the domain-product validator expected a
  sibling `lotus-platform` checkout; runtime smoke passed with `Passed: 66 Failed: 0`.
- `python -m ruff format scripts/validate_domain_data_product_contracts.py tests/unit/test_domain_data_product_contracts.py tests/unit/test_ci_workflow_action_versions.py`: applied formatting.
- `python -m ruff check scripts/validate_domain_data_product_contracts.py tests/unit/test_domain_data_product_contracts.py tests/unit/test_ci_workflow_action_versions.py --ignore E501,I001`: passed.
- `python -m pytest tests\unit\test_ci_workflow_action_versions.py tests\unit\test_domain_data_product_contracts.py -q`: 20 passed.
- `python scripts\certify_lotus_core_app.py --skip-runtime-smoke --json-output output\lotus-core-validation\static-validation-cr1264.json`: passed with all static contracts, supported-feature truth, and domain-product validation green; runtime smoke was explicitly skipped for focused local proof.
- `make quality-workflow-governance-gate`: passed with 13 tests.
- `make domain-product-validate`: passed.
- Workflow YAML parse smoke: 5 workflow YAML files parsed.
- `make lint`: passed.
- `make typecheck`: passed.
- `make quality-wiki-docs-gate`: passed.
- `git diff --check`: passed; Git reported expected CRLF normalization warnings on touched files.
- `powershell -ExecutionPolicy Bypass -File ..\lotus-platform\automation\Sync-RepoWikis.ps1 -CheckOnly -Repository lotus-core`: failed because the published GitHub wiki is not synchronized
  with repo-authored wiki source. Drift reported on `Data-Models.md`,
  `Mesh-Data-Products.md`, `Operations-Runbook.md`, `Outbox-Events.md`, `Overview.md`,
  `Security-and-Governance.md`, `Supported-Features.md`, and `Validation-and-CI.md`. The first
  four are pre-existing publication drift; `Security-and-Governance.md` is from the prior security
  slice; `Overview.md`, `Supported-Features.md`, and `Validation-and-CI.md` are intentionally
  changed by this slice and need normal post-merge wiki publication from `main`.

## Documentation And Wiki Decision

Updated README current-state truth, quality scorecard, refactor health report, review ledger, and
repo-local wiki source pages `Overview.md`, `Supported-Features.md`, and `Validation-and-CI.md`.
Wiki publication remains pending until this branch is merged and the governed repository wiki sync
step is run from `main`.
