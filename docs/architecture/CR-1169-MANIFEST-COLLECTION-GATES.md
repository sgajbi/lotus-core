# CR-1169 Manifest Collection Gates

## Objective

Address GitHub issue #445 by making collection-only CI gates use the repository test manifest
instead of hard-coded pytest paths, and by adding a first runtime-separated non-unit collection
gate.

## Issue Triage

Issue #445 is valid and in scope. The quality-baseline workflow already had a unit collection gate,
but it collected a hard-coded path directly. That left the gate less aligned with the governed suite
manifest that owns runtime mode, deselection policy, and suite boundaries. It also meant
`integration-lite` collection was not independently proven before execution.

## Baseline Risk

Collection gates that bypass the manifest can drift from the suite definitions used by runtime
lanes. That increases CI noise and allows test topology changes to land without proving the
declared runtime-separated suite can still be discovered.

## Change

- Added `suite_pytest_command(...)` to `scripts/test_manifest.py`.
- Added `--collect-only` support to manifest suite execution.
- Changed `make quality-unit-collection-gate` to collect the manifest-backed `unit` suite.
- Added `make quality-integration-lite-collection-gate`.
- Added `Quality Baseline / Integration Lite Collection Gate` to the quality-baseline workflow.
- Added a regression test proving collection commands are built from manifest suite definitions.

## Expected Improvement

CI collection checks are now less brittle and better aligned with the same suite ownership model as
runtime execution:

- local and CI collection use repo-native Make targets,
- collection gates include manifest-defined suite paths and deselection args,
- `integration-lite` import/discovery regressions fail before the runtime lane starts,
- future suite-boundary changes can be tested through `scripts/test_manifest.py` rather than
duplicating pytest path logic in workflows.

## Compatibility And Behavior

No product runtime, API route, OpenAPI schema, database schema, data product, or downstream response
contract changed. Test execution behavior is unchanged unless `--collect-only` is supplied.

The quality-baseline workflow adds one fast collection-only job. It does not promote Docker-backed
or mixed-runtime suites into quality-baseline, and it does not claim full all-suite collection.

## Tests Added

- `test_manifest_collection_command_uses_suite_definition`

## Validation

```powershell
make quality-integration-lite-collection-gate
make quality-unit-collection-gate
python -m pytest tests\unit\services\query_service\test_test_manifest.py tests\unit\test_ci_workflow_action_versions.py -q
python -m ruff check scripts\test_manifest.py tests\unit\services\query_service\test_test_manifest.py tests\unit\test_ci_workflow_action_versions.py
python -m ruff format --check scripts\test_manifest.py tests\unit\services\query_service\test_test_manifest.py tests\unit\test_ci_workflow_action_versions.py
python -c "from pathlib import Path; import yaml; [yaml.safe_load(p.read_text()) for p in Path('.github/workflows').glob('*.yml')]; print('workflow yaml parse ok')"
```

Observed:

- `make quality-integration-lite-collection-gate` collected `121` tests
- `make quality-unit-collection-gate` collected `3082/3092` tests with `10` manifest deselects
- focused manifest/workflow governance tests passed with `20` tests
- Ruff lint passed
- Ruff format check passed
- workflow YAML parse passed for all workflow files

## Residual Issue Scope

Issue #445 should remain open until PR and QA evidence proves the new collection jobs in GitHub CI.
Additional runtime families should only receive collection gates when their infrastructure and
runtime profile make them deterministic enough for quality-baseline enforcement.

## Documentation Decision

Updated the codebase review ledger, quality scorecard, and refactor health report. No README or wiki
update was needed because this is CI-governance implementation detail and not operator-facing
product behavior.
