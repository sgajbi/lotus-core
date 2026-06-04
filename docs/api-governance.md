# lotus-core API Governance

## Objective

`lotus-core` APIs should be consistent, documented, source-data-product aware, and safe for
downstream platform consumers.

## Required API Posture

1. Endpoint summaries, descriptions, tags, operation IDs, response models, examples, and standard
   errors are required for public APIs.
2. Pagination, filtering, sorting, versioning, and deprecation behavior should be consistent across
   route families.
3. Source-data products must expose runtime metadata, data-quality status, evidence timestamps, and
   product identity where applicable.
4. Health, readiness, liveness, metrics, public, internal, and operational routes should remain
   separated and documented.

## Enforcement

Existing repository gates include OpenAPI and vocabulary checks. The new `.spectral.yaml` and
report-only quality workflow add a portable baseline for API linting before regression and
enterprise-readiness thresholds are enforced.
