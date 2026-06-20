# CR-1107 App Validation Evidence

## Scope

Create one repeatable `lotus-core` app-level validation command for supported demo surfaces.

## Quality Intake

| Item | Repo evidence |
| --- | --- |
| Owner pattern | `lotus-core` owns portfolio, booking, transaction, ingestion, operational read, query-control-plane, source-data, support, lineage, and simulation surfaces. |
| Source of truth | `REPOSITORY-ENGINEERING-CONTEXT.md`, `docs/supported-features.md`, `wiki/Supported-Features.md`, `docs/standards/route-contract-family-registry.json`, and `contracts/domain-data-products/lotus-core-products.v1.json`. |
| Closest tests | `tests/unit/scripts/test_certify_lotus_core_app.py`, `tests/integration/tools/test_demo_data_pack.py`, `tests/unit/scripts/test_validate_live_dpm_source_products.py`, and existing Docker smoke/unit guard coverage. |
| Repo-native command | `make lotus-core-validate`. |
| Measurable signal | JSON evidence under `output/lotus-core-validation/` with explicit pass/fail checks and runtime surface families. |

## Change

`make lotus-core-validate` runs `scripts/certify_lotus_core_app.py`.

The command:

1. runs static contract checks for OpenAPI, API vocabulary, route-family classification,
   source-data products, and domain-product declarations,
2. verifies supported-feature truth anchors in docs and wiki source,
3. runs deterministic Docker endpoint smoke, which seeds synthetic data and calls real APIs across
   ingestion, event replay and ops, query reads, support and lineage, integration policy and
   capabilities, core snapshot, and simulation,
4. writes machine-readable JSON evidence under `output/lotus-core-validation/`,
5. exits non-zero when proof is weak.

## CI Posture

The PR Merge Gate now runs `make lotus-core-validate` as report-only evidence and uploads the JSON
artifacts.

It is not blocking yet. Promotion requires:

1. repeated stable CI runs,
2. low false-positive rate,
3. explicit exception and remediation policy,
4. clear lane placement,
5. lotus-ci-enforcement-governance approval that the signal is deterministic, low-noise, and
   policy-backed.

## Validation

Focused validation:

```powershell
python -m pytest tests/unit/scripts/test_certify_lotus_core_app.py -q
python -m ruff check scripts/certify_lotus_core_app.py tests/unit/scripts/test_certify_lotus_core_app.py
python -m ruff format --check scripts/certify_lotus_core_app.py tests/unit/scripts/test_certify_lotus_core_app.py
python scripts/certify_lotus_core_app.py --skip-runtime-smoke --json-output output\lotus-core-validation\static-validation.json
make lotus-core-validate
make lint
make typecheck
make warning-gate
python -m pytest tests/unit/test_ci_workflow_action_versions.py tests/unit/test_main_releasability_workflow.py tests/unit/scripts/test_certify_lotus_core_app.py -q
git diff --check
```

Observed evidence:

1. `make lotus-core-validate` passed and wrote
   `output/lotus-core-validation/lotus-core-validation.json`.
2. The nested runtime smoke evidence reported `Passed: 66 Failed: 0`.
3. `make warning-gate` reported `3001 passed, 10 deselected` with `warnings=0`.
