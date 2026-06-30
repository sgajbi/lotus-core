# CR-1165 Workflow Governance Quality Gate

## Objective

Expose the workflow fail-closed governance tests as a first-class repo-native quality gate so CI
policy regressions fail quickly instead of only surfacing inside the broader unit suite.

## Baseline Risk

CR-1164 added tests for bounded workflow jobs and documented non-blocking exceptions, but the guard
was only reachable through direct pytest invocation or the broader unit suite. That made the
governance signal less visible than the existing quality-baseline gates for lint, format, typecheck,
security, maintainability, complexity, and unit collection.

## Change

- Added `make quality-workflow-governance-gate`.
- Added `Quality Baseline / Workflow Governance Gate` to `.github/workflows/quality-baseline.yml`.
- Added a regression assertion that the quality-baseline workflow runs the Make target.

## Expected Improvement

The anti-slop CI rule is now both deterministic and lane-owned:

- local and CI execution use the same Make target,
- workflow-governance failures have a named quality-baseline job,
- accidental removal of the job or target is covered by the workflow-governance test itself,
- the gate remains fast because it runs only the focused workflow contract test module.

## Compatibility And Behavior

No product runtime, API, OpenAPI, database schema, data product, or downstream response contract
changed. The new CI job increases quality-baseline coverage with a focused fast test, not a Docker
or integration workload.

## Tests Added

- `test_quality_baseline_runs_workflow_governance_gate`

## Validation

```powershell
make quality-workflow-governance-gate
python -m ruff check tests\unit\test_ci_workflow_action_versions.py
python -m ruff format --check tests\unit\test_ci_workflow_action_versions.py
python -c "from pathlib import Path; import yaml; [yaml.safe_load(p.read_text(encoding='utf-8')) for p in Path('.github/workflows').glob('*.yml')]; print('workflow yaml parsed:', len(tuple(Path('.github/workflows').glob('*.yml'))))"
```

Observed:

- `9 passed`
- Ruff lint passed with a local cache-write warning only
- Ruff format check passed
- 5 workflow YAML files parsed

## Documentation Decision

Updated the codebase review ledger, quality scorecard, and refactor health report. No README or wiki
update was needed because this is CI-governance implementation detail and not operator-facing
product behavior.
