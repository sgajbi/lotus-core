# lotus-core API Governance Rules

Status: Initial report-only rule set on 2026-06-02.

## Endpoint Requirements

Every public endpoint should provide:

1. summary,
2. description,
3. tags,
4. stable operation ID,
5. request model where applicable,
6. response model,
7. examples,
8. standard error responses,
9. correlation ID support or propagation,
10. documented pagination, filtering, sorting, versioning, and deprecation behavior where relevant.

## Endpoint Separation

1. Public APIs, internal APIs, health, readiness, liveness, metrics, and operational endpoints must
   be separated by route family and documented.
2. Source-data product APIs must preserve product identity and runtime metadata.
3. Deprecated routes must remain explicit and tested until removed.

## Initial Enforcement

1. Existing `make openapi-gate` and `make api-vocabulary-gate` remain authoritative where present.
2. `.spectral.yaml` introduces report-only OpenAPI lint posture for CI publication.
3. Future gates should fail only new regressions before enforcing enterprise thresholds.
