# CR-1009: OpenAPI Inference Policy Boundary

Date: 2026-06-05

## Scope

Split shared OpenAPI example and description inference into focused policy helpers without changing
the precedence used by schema enrichment: known field examples first, enum values second, schema
type examples third, schema format examples fourth, and string-like fallback last. Description
inference keeps the existing identifier, business-date, timestamp, currency, monetary, quantity,
rate/price, status, and model-field fallback order.

## Finding

`infer_example` and `infer_description` mixed key normalization, ordered policy selection,
type-specific example construction, format-specific example construction, and domain description
classification in two C-ranked helpers. That made shared OpenAPI enrichment harder to audit as
more services rely on inferred examples and descriptions to satisfy API governance.

## Action

Added focused helpers for known-key examples, enum examples, typed examples, formatted examples,
rule-based description selection, and each description predicate/formatter. Added direct tests for
example precedence and description precedence in the shared OpenAPI enrichment test pack.

## Result

`infer_example` improved from `C (11)` to `A (3)`, and `infer_description` improved from
`C (14)` to `A (2)`. The shared OpenAPI examples module remains B-ranked maintainability at
`B (16.35)`.

## Evidence

- `python -m pytest tests\unit\libs\portfolio-common\test_openapi_enrichment.py -q`
  => 6 passed
- `python -m ruff check src\libs\portfolio-common\portfolio_common\openapi_examples.py tests\unit\libs\portfolio-common\test_openapi_enrichment.py`
  => all checks passed
- `python -m ruff format --check src\libs\portfolio-common\portfolio_common\openapi_examples.py tests\unit\libs\portfolio-common\test_openapi_enrichment.py`
  => 2 files already formatted
- `python -m radon cc src\libs\portfolio-common\portfolio_common\openapi_examples.py -s`
  => `infer_example` `A (3)` and `infer_description` `A (2)`
- `python -m radon mi src\libs\portfolio-common\portfolio_common\openapi_examples.py -s`
  => `openapi_examples.py` `B (16.35)`
- `python -m radon raw src\libs\portfolio-common\portfolio_common\openapi_examples.py`
  => 337 SLOC / 223 LLOC
- `make openapi-gate`
  => passed
- `make quality-complexity-gate`
  => passed
- `make quality-maintainability-gate`
  => passed

## Wiki Decision

No wiki source update is required. This is an internal shared OpenAPI inference helper refactor
that preserves generated schema enrichment semantics.
