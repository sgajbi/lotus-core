# CR-1014: OpenAPI Schema Example Orchestration Boundary

Date: 2026-06-05

## Scope

Split the shared OpenAPI schema example public builder into focused candidate selection,
structured-schema handling, fallback inference, and fallback property-name helpers without changing
the existing precedence order: explicit examples, `$ref`, union schemas, object/array schemas, then
primitive fallback.

## Finding

After CR-1013, `build_schema_example` was the last B-ranked function in
`openapi_examples.py`. It still mixed invalid-node handling, explicit example precedence,
reference resolution, union example generation, object/array dispatch, primitive title fallback,
and final inferred example construction in one shared API-governance entry point.

## Action

Added focused helpers for candidate schema examples, structured schema examples, fallback schema
examples, and fallback property-name resolution. Added direct tests pinning explicit-example
precedence and primitive title fallback behavior.

## Result

`build_schema_example` improved from `B (10)` to `A (4)`. Every function in
`openapi_examples.py` now reports A-ranked cyclomatic complexity, and the module remains B-ranked
maintainability at `B (17.17)`.

## Evidence

- `python -m pytest tests\unit\libs\portfolio-common\test_openapi_enrichment.py -q`
  => 12 passed
- `python -m ruff check src\libs\portfolio-common\portfolio_common\openapi_examples.py tests\unit\libs\portfolio-common\test_openapi_enrichment.py`
  => all checks passed
- `python -m ruff format --check src\libs\portfolio-common\portfolio_common\openapi_examples.py tests\unit\libs\portfolio-common\test_openapi_enrichment.py`
  => 2 files already formatted
- `python -m radon cc src\libs\portfolio-common\portfolio_common\openapi_examples.py -s`
  => `build_schema_example` `A (4)` and every function in `openapi_examples.py` A-ranked
- `python -m radon mi src\libs\portfolio-common\portfolio_common\openapi_examples.py -s`
  => `openapi_examples.py` `B (17.17)`
- `python -m radon raw src\libs\portfolio-common\portfolio_common\openapi_examples.py`
  => 423 SLOC / 250 LLOC
- `make openapi-gate`
  => passed
- `make quality-complexity-gate`
  => passed
- `make quality-maintainability-gate`
  => passed

## Wiki Decision

No wiki source update is required. This is an internal shared OpenAPI schema example orchestration
refactor that preserves generated schema enrichment semantics.
