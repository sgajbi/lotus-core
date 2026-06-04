# CR-868: API Governance Regression Gate

Status: Hardened on 2026-06-02.

## Finding

The OpenAPI quality and API vocabulary gates were already clean as repo-native targets, but the
quality-baseline workflow still left API governance in report-only posture. That weakened the
progressive CI path for the bank-buyable API documentation and vocabulary requirements.

## Change

Added a dedicated `Quality Baseline / API Governance Gate` workflow job that:

1. installs the repository through `python scripts/bootstrap_dev.py`,
2. runs `python scripts/openapi_quality_gate.py`,
3. runs `python scripts/api_vocabulary_inventory.py --validate-only`.

The Spectral scaffold remains report-only until a stable generated OpenAPI artifact path exists for
CI publication.

## Boundary Preserved

This change does not alter:

1. runtime behavior,
2. API contracts,
3. database schema,
4. existing repo-native `make openapi-gate` behavior,
5. existing repo-native `make api-vocabulary-gate` behavior.

## Wiki Decision

No repo-local `wiki/` source update is included. This is CI quality-gate governance recorded in the
repo-local quality reports and architecture review ledger; it does not change operator-facing
runtime behavior.

## Validation

Local validation passed for the slice:

1. `make openapi-gate`,
2. `make api-vocabulary-gate`,
3. `make quality-ruff-gate`,
4. `make quality-ruff-format-gate`,
5. `make quality-import-boundary-gate`,
6. workflow YAML parsing,
7. `git diff --check`.
