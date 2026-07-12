# CR-1012: OpenAPI Union Example Builder Boundary

Date: 2026-06-05

## Scope

Split shared OpenAPI union schema example generation into focused union-key discovery,
per-union-key dispatch, non-empty allOf result normalization, allOf object merging, and first
available oneOf/anyOf variant selection without changing generated schema-example semantics.

## Finding

After CR-1011, `_build_union_example` still mixed allOf, oneOf, and anyOf discovery with variant
validation, allOf merging, oneOf/anyOf first-variant selection, and fallback behavior in one
B-ranked helper. This was a shared API-governance path because OpenAPI enrichment uses it for
request and response body examples.

## Action

Added focused helpers for union variant lookup, union-key example dispatch, and non-empty allOf
normalization. Added direct tests for allOf object merging and oneOf first-available variant
selection. The allOf test intentionally pins the current nested primitive behavior where an
untitled primitive property falls back to the generic `value` inference.

## Result

`_build_union_example` improved from `B (8)` to `A (4)`. `openapi_examples.py` remains B-ranked
maintainability at `B (17.72)`.

## Evidence

- `python -m pytest tests\unit\libs\portfolio-common\test_openapi_enrichment.py -q`
  => 8 passed
- `python -m ruff check src\libs\portfolio-common\portfolio_common\openapi_examples.py tests\unit\libs\portfolio-common\test_openapi_enrichment.py`
  => all checks passed
- `python -m ruff format --check src\libs\portfolio-common\portfolio_common\openapi_examples.py tests\unit\libs\portfolio-common\test_openapi_enrichment.py`
  => 2 files already formatted
- `python -m radon cc src\libs\portfolio-common\portfolio_common\openapi_examples.py -s`
  => `_build_union_example` `A (4)`
- `python -m radon mi src\libs\portfolio-common\portfolio_common\openapi_examples.py -s`
  => `openapi_examples.py` `B (17.72)`
- `python -m radon raw src\libs\portfolio-common\portfolio_common\openapi_examples.py`
  => 381 SLOC / 238 LLOC
- `make openapi-gate`
  => passed
- `make quality-complexity-gate`
  => passed
- `make quality-maintainability-gate`
  => passed

## Wiki Decision

No wiki source update is required. This is an internal shared OpenAPI union example builder
refactor that preserves generated schema enrichment semantics.
