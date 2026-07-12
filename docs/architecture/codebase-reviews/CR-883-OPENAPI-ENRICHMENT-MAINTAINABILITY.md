# CR-883 OpenAPI Enrichment Maintainability

Date: 2026-06-04

## Scope

Reduce the maintainability hotspot in shared OpenAPI enrichment infrastructure without changing
the public enrichment API or generated schema behavior.

## Finding

`src/libs/portfolio-common/portfolio_common/openapi_enrichment.py` was a C-ranked maintainability
module. It mixed OpenAPI schema mutation with schema example inference, field description inference,
reference traversal, union handling, request/response media examples, operation documentation, and
FastAPI schema attachment.

That made API-governance behavior harder to review and evolve because example-generation policy and
OpenAPI mutation orchestration lived in the same file.

## Action

Extracted schema example and description inference into
`portfolio_common.openapi_examples`, including:

1. canonical example lookup,
2. scalar example inference,
3. field description inference,
4. `$ref` traversal,
5. object, array, and union schema example construction.

Kept `portfolio_common.openapi_enrichment` focused on:

1. operation documentation defaults,
2. parameter/request/response example attachment,
3. schema property documentation attachment,
4. FastAPI `openapi()` attachment.

The public `enrich_openapi_schema(...)` and `attach_enriched_openapi(...)` entry points remain
unchanged.

## Result

`openapi_enrichment.py` now reports `A (25.84)` under Radon maintainability instead of `C (3.38)`.
The new `openapi_examples.py` helper module reports `B (17.56)`, so the split reduces the current
C-ranked maintainability hotspot count rather than merely moving the hotspot.

## Evidence

- `python -m pytest tests\unit\libs\portfolio-common\test_openapi_enrichment.py -q`
  => `4 passed`
- `python -m radon mi src\libs\portfolio-common\portfolio_common\openapi_enrichment.py src\libs\portfolio-common\portfolio_common\openapi_examples.py -s`
  => `openapi_enrichment.py - A (25.84)` and `openapi_examples.py - B (17.56)`
- `python -m radon mi src -s | Select-String " - C| - D| - E| - F"` no longer reports
  `openapi_enrichment.py`

## Wiki Decision

No wiki source update is required for this slice. The change is an internal API-governance
maintainability refactor with repository-local architecture and quality evidence; it does not
change operator-facing runtime behavior, API surface, onboarding flow, or wiki-owned product truth.

