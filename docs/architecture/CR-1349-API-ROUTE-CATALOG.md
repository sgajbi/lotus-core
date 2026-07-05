# CR-1349 API Route Catalog

Date: 2026-07-05

## Objective

Fix GitHub issue #614 by generating a deterministic API route catalog from implementation evidence
instead of relying on hand-maintained API prose.

The slice reduces design-time complexity for route reviewers by giving one machine-readable source
that reconciles FastAPI OpenAPI output with RFC-0082/RFC-0083 route-family governance.

## Findings

The repository already had strong API components:

- OpenAPI quality and Spectral gates
- API vocabulary inventory
- route-family registry
- endpoint consolidation watchlist
- verified API examples
- API Surface wiki navigation

Those artifacts were still separate. A reviewer changing or deprecating a route had to manually
join OpenAPI paths, route-family classification, request/response schema names, error responses,
pagination/filtering/sorting parameters, idempotency posture, and downstream consumer posture.

## Changes

Added `docs/standards/api-route-catalog.v1.json` with 217 current OpenAPI routes. Business routes
are enriched from `docs/standards/route-contract-family-registry.json`; shared `/health`,
`/metrics`, `/version`, and OpenAPI routes are cataloged as shared operational routes.

Added `scripts/generate_api_route_catalog.py` with a `--check` mode that fails when the tracked
catalog drifts from generated OpenAPI plus route-family governance.

Added focused unit tests for route-family enrichment, request/response/error schema extraction,
pagination/filtering/sorting detection, idempotency posture, shared operational routes, and
missing/stale route detection.

Wired `make api-route-catalog-guard` into `api-vocabulary-gate`, lint, and documentation evidence
generation. Updated README, API wiki source, repository context, and this codebase-review ledger.

## Compatibility

This is documentation and validation only.

No route path, request DTO, response DTO, OpenAPI schema, database schema, Kafka contract, metric
name, runtime topology, Dockerfile, package import path, or public runtime behavior changed.

## Validation Evidence

Focused validation before commit:

- `python scripts/generate_api_route_catalog.py --check`
- `make api-vocabulary-gate`
- `python -m pytest tests/unit/scripts/test_generate_api_route_catalog.py tests/unit/scripts/test_generate_documentation_evidence_pack.py -q`
- `python -m ruff check scripts/generate_api_route_catalog.py tests/unit/scripts/test_generate_api_route_catalog.py scripts/generate_documentation_evidence_pack.py tests/unit/scripts/test_generate_documentation_evidence_pack.py --ignore E501,I001`
- `python -m ruff format --check scripts/generate_api_route_catalog.py tests/unit/scripts/test_generate_api_route_catalog.py scripts/generate_documentation_evidence_pack.py tests/unit/scripts/test_generate_documentation_evidence_pack.py`
- `make docs-evidence-pack`
- `make quality-wiki-docs-gate`
- `python C:\Users\Sandeep\.codex\skills\lotus-readme-wiki-governance\scripts\audit_wiki_quality.py --wiki-dir wiki --changed-page API-Surface.md`
- `git diff --check`

`Sync-RepoWikis.ps1 -CheckOnly -Repository lotus-core` reported expected pre-merge publication
drift across the existing repo-authored wiki source, including `API-Surface.md` and
`Validation-and-CI.md`. Publish wiki source after merge with the governed wiki sync flow.

## Docs, Wiki, And Context

Wiki source changed in `wiki/API-Surface.md` and `wiki/Validation-and-CI.md`; publish after merge
with the governed wiki sync flow.

No Lotus skill update is required for this slice. Existing API governance, README/wiki governance,
backend delivery, CI enforcement, and codebase-review skills already route this class of work to
generated evidence and deterministic guards. The repo-local catalog guard is the reusable control
that prevents API surface prose drift from recurring.
