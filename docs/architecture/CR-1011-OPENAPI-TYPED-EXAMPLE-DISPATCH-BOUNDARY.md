# CR-1011: OpenAPI Typed Example Dispatch Boundary

Date: 2026-06-05

## Scope

Split shared OpenAPI typed-example dispatch into static and dynamic type-example maps without
changing generated array, object, boolean, integer, number, or fallback examples.

## Finding

After CR-1010, `_typed_example` still mixed schema-type lookup with array recursion, static object
and boolean examples, integer policy, number policy, and unknown-type fallback in one B-ranked
dispatcher. That kept shared API example-generation policy harder to review than the surrounding
A-ranked inference helpers.

## Action

Added static typed-example and dynamic typed-example builder maps with focused array, integer, and
number builder helpers. Existing direct OpenAPI inference tests continue to pin generated examples
for array, boolean, integer, number, date, datetime, enum, and known-key fields.

## Result

`_typed_example` improved from `B (6)` to `A (3)`, and `openapi_examples.py` improved from
`B (17.47)` to `B (17.91)` maintainability.

## Evidence

- `python -m pytest tests\unit\libs\portfolio-common\test_openapi_enrichment.py -q`
  => 6 passed
- `python -m ruff check src\libs\portfolio-common\portfolio_common\openapi_examples.py tests\unit\libs\portfolio-common\test_openapi_enrichment.py`
  => all checks passed
- `python -m ruff format --check src\libs\portfolio-common\portfolio_common\openapi_examples.py tests\unit\libs\portfolio-common\test_openapi_enrichment.py`
  => 2 files already formatted
- `python -m radon cc src\libs\portfolio-common\portfolio_common\openapi_examples.py -s`
  => `_typed_example` `A (3)`
- `python -m radon mi src\libs\portfolio-common\portfolio_common\openapi_examples.py -s`
  => `openapi_examples.py` `B (17.91)`
- `python -m radon raw src\libs\portfolio-common\portfolio_common\openapi_examples.py`
  => 360 SLOC / 230 LLOC
- `make openapi-gate`
  => passed
- `make quality-complexity-gate`
  => passed
- `make quality-maintainability-gate`
  => passed

## Wiki Decision

No wiki source update is required. This is an internal shared OpenAPI typed-example dispatch
refactor that preserves generated schema enrichment semantics.
