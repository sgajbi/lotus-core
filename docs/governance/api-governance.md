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
5. Caller-controlled sorting must publish allowed fields and directions in OpenAPI, reject invalid
   supplied values with structured 400 responses, and use deterministic tie-breakers for paginated
   ordering. Silent fallback is only acceptable when the parameter is omitted and the default is
   documented.
6. Collection and raw-series endpoints must publish an explicit bound: cursor/page-token
   pagination, offset pagination with maximum `limit`, mandatory bounded date windows, or a
   documented small-cardinality contract with tests. Optional date filters must not allow
   full-history scans by omission.

## Enforcement

Repository gates include:

1. `make openapi-gate`, the Lotus-specific contract quality gate for endpoint documentation,
   examples, schema field metadata, standard error responses, and duplicate operation IDs.
2. `make api-vocabulary-gate`, the Lotus API vocabulary and semantic naming gate.
3. `make quality-openapi-spectral-gate`, the portable Spectral blocker-subset gate. It generates
   per-service OpenAPI JSON artifacts under `output/openapi/` and enforces operation IDs,
   descriptions, summaries, tags, and common successful `2xx` response declarations.

The broader `spectral:oas` advisory rule family is not yet claimed as clean; Decimal/string example
alignment, global tag declarations, trailing slash paths, and contact metadata remain follow-up API
quality work.
