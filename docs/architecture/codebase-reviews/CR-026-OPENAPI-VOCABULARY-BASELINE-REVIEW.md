# CR-026 OpenAPI Vocabulary Baseline Review

## Scope

Establish the current RFC-0067 baseline for `lotus-core` so Swagger/OpenAPI
quality improvement becomes an explicit part of the code-review program.

## Baseline Result

The current repository already passes the core RFC-0067 controls:

1. `python scripts/openapi_quality_gate.py`
2. `python scripts/api_vocabulary_inventory.py --validate-only`

That means the repo is not failing on basic contract governance.

## What Still Needs Improvement

The remaining gap is quality depth, not baseline compliance:

- richer request examples
- richer response examples
- stronger field-level descriptions where the gate currently accepts minimal
  completeness
- continued vocabulary alignment as new APIs are added

## Alias Scan Result

The baseline alias scan did not show broad API alias drift.

The only remaining code hit in active service code was explicit header aliasing
for `X-Correlation-ID` in `financial_reconciliation_service`, which is a
transport/header concern rather than request-body or response-body contract
aliasing.

## Action

Make Swagger/OpenAPI quality depth an active review stream from this point
forward rather than treating it as a one-time RFC gate.

## Evidence

- `python scripts/openapi_quality_gate.py`
- `python scripts/api_vocabulary_inventory.py --validate-only`
- alias scan across `src`, `scripts`, and `tests`
