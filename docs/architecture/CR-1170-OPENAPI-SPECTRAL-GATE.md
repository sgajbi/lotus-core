# CR-1170 OpenAPI Spectral Gate

## Objective

Address GitHub issue #444 by giving Spectral a stable generated OpenAPI artifact input and promoting
a portable, enforceable OpenAPI lint subset into the quality-baseline workflow.

## Issue Triage

Issue #444 is valid and in scope. `lotus-core` already had repo-native `openapi-gate` and
`api-vocabulary-gate`, but `.spectral.yaml` remained a scaffold because CI had no deterministic
generated-spec artifact path for Spectral to lint.

## Baseline Risk

Without generated artifacts, Spectral linting either remains report-only or depends on ad hoc local
schema export steps. That weakens API governance because a portable OpenAPI lint layer cannot be
run consistently in local checks and CI.

## Change

- Added deterministic per-service OpenAPI artifact generation under `output/openapi/`.
- Added `scripts/generate_openapi_artifacts.py`.
- Added `scripts/openapi_spectral_gate.py`, a cross-platform wrapper that invokes `npx` directly
  (`npx.cmd` on Windows, `npx` elsewhere) and passes generated artifact paths without shell globs.
- Added `make quality-openapi-spectral-gate`.
- Added an enforced `OpenAPI Spectral gate` step to the quality-baseline API governance job.
- Converted `.spectral.yaml` into an explicit blocker subset for operation IDs, descriptions,
  summaries, tags, and common successful `2xx` response declarations.
- Added unit coverage for artifact writing, Spectral command construction, Windows `npx.cmd`
  selection, and workflow wiring.

## Expected Improvement

API governance now has three complementary layers:

- `make openapi-gate` remains the authoritative Lotus-specific contract quality gate for examples,
  schema field metadata, response/error examples, and duplicate operation IDs.
- `make api-vocabulary-gate` remains the Lotus vocabulary and semantic naming gate.
- `make quality-openapi-spectral-gate` gives CI a portable generated-artifact lint gate for a stable
  Spectral blocker subset.

## Compatibility And Behavior

No product runtime, API route, OpenAPI schema, database schema, data product, or downstream response
contract changed. Generated artifacts are written under ignored `output/openapi/` evidence.

The broad `spectral:oas` ruleset is not claimed as clean in this slice. Existing advisory findings
around Decimal/string examples, global tag declarations, trailing slash paths, and contact metadata
remain follow-up work for a separate API-quality hardening slice.

## Tests Added

- `test_write_openapi_artifacts_uses_stable_service_paths`
- `test_npx_executable_uses_windows_command_shim`
- `test_spectral_command_uses_direct_artifact_paths`
- `test_quality_baseline_runs_openapi_spectral_gate`

## Validation

```powershell
python -m pytest tests\unit\services\query_service\test_openapi_quality_gate.py tests\unit\test_ci_workflow_action_versions.py tests\unit\scripts\test_openapi_spectral_gate.py -q
python -m ruff check scripts\openapi_quality_gate.py scripts\generate_openapi_artifacts.py scripts\openapi_spectral_gate.py tests\unit\services\query_service\test_openapi_quality_gate.py tests\unit\test_ci_workflow_action_versions.py tests\unit\scripts\test_openapi_spectral_gate.py
python -m ruff format --check scripts\openapi_quality_gate.py scripts\generate_openapi_artifacts.py scripts\openapi_spectral_gate.py tests\unit\services\query_service\test_openapi_quality_gate.py tests\unit\test_ci_workflow_action_versions.py tests\unit\scripts\test_openapi_spectral_gate.py
python scripts\openapi_quality_gate.py
make quality-openapi-spectral-gate
python -c "from pathlib import Path; import yaml; [yaml.safe_load(p.read_text()) for p in Path('.github/workflows').glob('*.yml')]; print('workflow yaml parse ok')"
```

Observed:

- focused OpenAPI/workflow/Spectral tests passed with `22` tests
- Ruff lint passed
- Ruff format check passed
- `python scripts\openapi_quality_gate.py` passed
- `make quality-openapi-spectral-gate` generated 14 service artifacts and reported no Spectral
  results at `warn` or higher
- `make quality-workflow-governance-gate` passed with `12` tests
- `make quality-wiki-docs-gate` passed
- `git diff --check` passed
- stranded-truth reconciliation found only
  `origin/dependabot/github_actions/github-actions-02325a8da5` and
  `origin/dependabot/pip/python-runtime-b808a9fc65`
- wiki publication check still reports pre-existing published-wiki drift for `Data-Models.md`,
  `Mesh-Data-Products.md`, `Operations-Runbook.md`, and `Outbox-Events.md`
- workflow YAML parse passed for all workflow files

## Residual Issue Scope

Issue #444 is fixed locally pending PR CI/QA evidence. It should remain open until GitHub CI proves
the new quality-baseline step on the branch.
Broader `spectral:oas` cleanup remains a separate backlog item and should not be represented as
complete by this blocker-subset gate.

## Documentation Decision

Updated the codebase review ledger, API governance docs, quality scorecard, refactor health report,
and repo-local wiki validation/CI guidance because CI/API governance truth changed.
