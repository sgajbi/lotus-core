# lotus-core API Governance Rules

Status: Progressive enforcement rule set on 2026-06-02.

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
2. `.github/workflows/quality-baseline.yml` now enforces the OpenAPI quality and API vocabulary
   gates in the API governance job.
3. `make quality-openapi-spectral-gate` now generates stable per-service OpenAPI artifacts under
   `output/openapi/` and enforces the `.spectral.yaml` blocker subset in the quality-baseline API
   governance job.
4. The enforced Spectral subset covers operation IDs, descriptions, summaries, tags, and common
   successful `2xx` response declarations. Broader `spectral:oas` findings remain advisory until
   their baselines are remediated and governed.
5. Future gates should fail only new regressions before enforcing enterprise thresholds.
