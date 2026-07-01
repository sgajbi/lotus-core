# CR-1164 Workflow Fail-Closed Governance

## Objective

Prevent accidental CI weakening during the bank-buyable refactor by making workflow timeouts and
non-blocking exceptions explicit, reviewed, and regression-tested.

## Baseline Risk

`lotus-core` already had workflow-action version governance, Node 24 action-runtime opt-in checks,
and documented report-only app validation evidence. Two gaps remained:

1. `.github/workflows/pr-auto-merge.yml` had no job-level timeout, so a required governance signal
   could hang without a bounded failure posture.
2. `continue-on-error` usage was not guarded by a workflow contract test, so future changes could
   silently convert merge-critical jobs or steps into advisory signals.

## Change

- Added `timeout-minutes: 10` to the `PR Auto Merge / Queue Auto Merge` job.
- Added workflow-governance unit coverage requiring every GitHub Actions job to define a positive
  timeout.
- Added workflow-governance unit coverage that allows `continue-on-error` only for the documented
  `lotus-core-validation-report` PR job and the named `Quality Baseline / Report Only` baseline
  steps.

## Expected Improvement

CI is more reliable and harder to weaken accidentally:

- governance jobs are bounded by default,
- merge-critical jobs remain fail-closed,
- report-only exceptions stay visible and deliberately scoped,
- future workflow edits get fast local feedback before noisy or weak CI reaches GitHub.

## Compatibility And Behavior

Current posture update: CR-1264 removed the `lotus-core-validation-report` non-blocking exception
after adding the required `lotus-platform` checkout and `LOTUS_PLATFORM_ROOT` wiring for app-level
validation. The report-only statement below is retained as historical CR-1164 rollout context.

No product runtime, API, OpenAPI, database schema, data product, or downstream response contract
changed. The `lotus-core-validation-report` job remains report-only per CR-1107 because promotion to
blocking still requires stable low-noise CI evidence and lotus-ci-enforcement-governance approval.

## Tests Added

- `test_all_workflow_jobs_have_bounded_timeouts`
- `test_continue_on_error_is_limited_to_documented_report_only_scope`

## Validation

```powershell
python -m pytest tests\unit\test_ci_workflow_action_versions.py -q
python -m ruff check tests\unit\test_ci_workflow_action_versions.py
python -m ruff format --check tests\unit\test_ci_workflow_action_versions.py
python -c "from pathlib import Path; import yaml; [yaml.safe_load(p.read_text(encoding='utf-8')) for p in Path('.github/workflows').glob('*.yml')]; print('workflow yaml parsed:', len(tuple(Path('.github/workflows').glob('*.yml'))))"
```

Observed:

- `8 passed`
- Ruff lint passed
- Ruff format check passed
- 5 workflow YAML files parsed

## Documentation Decision

Updated the codebase review ledger, quality scorecard, and refactor health report. No README or wiki
update was needed because this is CI-governance implementation detail and not operator-facing
product behavior.
