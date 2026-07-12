# CR-1274 API Router Boundary Guard

- Date: 2026-07-04
- Scope: API-layer architecture boundary enforcement
- GitHub issue: #635
- Related issue families: #636, #638

## Objective

Make the router responsibility contract executable so API modules stay HTTP adapters and do not keep
accumulating database, repository, client, file, or workflow responsibilities.

## Expected Improvement

`make architecture-guard` now detects API router boundary violations for:

1. database session dependencies,
2. repository imports and repository construction,
3. direct SQLAlchemy operations,
4. external client dependencies such as Kafka, Redis, cloud, and HTTP clients,
5. direct local file access.

Current legacy router coupling is captured in
`docs/standards/api-layer-router-boundary-exceptions.json`. The registry blocks new unregistered
coupling and fails stale exceptions after extraction work removes a violation.

## Tests Added

Extended `tests/unit/scripts/test_architecture_boundary_guard.py` with coverage for:

1. direct DB session imports and dependency injection,
2. repository imports and construction,
3. external client and file access,
4. transitional exception suppression,
5. unregistered violations,
6. stale exception detection,
7. diagnostic formatting.

## Validation Evidence

Local evidence for this slice:

1. `python -m pytest tests/unit/scripts/test_architecture_boundary_guard.py -q` passed with 14 tests.
2. `make architecture-guard` passed.

Additional broad validation:

1. scoped Ruff lint and format checks for the guard and tests passed.
2. `make quality-import-boundary-gate` passed with two kept contracts.
3. `make lint` passed.
4. `make quality-wiki-docs-gate` passed.
5. `git diff --check` passed with Windows CRLF normalization warnings only.

## Downstream Compatibility Impact

No runtime route, request DTO, response DTO, OpenAPI output, database schema, Kafka topic,
repository behavior, or downstream response shape changed. This is static architecture enforcement
and architecture documentation only.

## Documentation Updates

Updated architecture docs, layering standards, repository context, and codebase review evidence.
No wiki update is required because this slice changes engineering architecture guidance rather than
operator-facing or consumer-facing wiki truth.
