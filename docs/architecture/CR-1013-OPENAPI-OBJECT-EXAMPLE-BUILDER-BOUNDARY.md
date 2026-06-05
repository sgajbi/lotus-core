# CR-1013: OpenAPI Object Example Builder Boundary

Date: 2026-06-05

## Scope

Split shared OpenAPI object schema example generation into focused property extraction,
required-field normalization, per-property example construction, and include/omit policy helpers
without changing generated object example semantics.

## Finding

After CR-1012, `_build_object_example` still mixed property-map validation, required-field
normalization, recursive property example construction, required-property fallback inference,
optional-property include/omit policy, and object assembly in one B-ranked helper. This path is
shared by API request and response example enrichment.

## Action

Added focused helpers for schema properties, required property names, property schema example
construction, and property inclusion policy. Added direct tests pinning current generic fallback
behavior for empty object properties so this refactor does not silently alter generated OpenAPI
examples.

## Result

`_build_object_example` improved from `B (7)` to `A (4)`. `openapi_examples.py` remains B-ranked
maintainability at `B (16.96)`.

## Evidence

- `python -m pytest tests\unit\libs\portfolio-common\test_openapi_enrichment.py -q`
  => 10 passed
- `python -m ruff check src\libs\portfolio-common\portfolio_common\openapi_examples.py tests\unit\libs\portfolio-common\test_openapi_enrichment.py`
  => all checks passed
- `python -m ruff format --check src\libs\portfolio-common\portfolio_common\openapi_examples.py tests\unit\libs\portfolio-common\test_openapi_enrichment.py`
  => 2 files already formatted
- `python -m radon cc src\libs\portfolio-common\portfolio_common\openapi_examples.py -s`
  => `_build_object_example` `A (4)`
- `python -m radon mi src\libs\portfolio-common\portfolio_common\openapi_examples.py -s`
  => `openapi_examples.py` `B (16.96)`
- `python -m radon raw src\libs\portfolio-common\portfolio_common\openapi_examples.py`
  => 407 SLOC / 249 LLOC
- `make openapi-gate`
  => passed
- `make quality-complexity-gate`
  => passed
- `make quality-maintainability-gate`
  => passed

## Wiki Decision

No wiki source update is required. This is an internal shared OpenAPI object example builder
refactor that preserves generated schema enrichment semantics.
