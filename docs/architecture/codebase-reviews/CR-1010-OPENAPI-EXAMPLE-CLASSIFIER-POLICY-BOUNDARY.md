# CR-1010: OpenAPI Example Classifier Policy Boundary

Date: 2026-06-05

## Scope

Split shared OpenAPI number and string-like example classification into explicit token-rule tables
without changing the generated examples for weights, prices, rates, quantities, monetary values,
identifiers, currencies, dates, timestamps, statuses, or generic string fallback fields.

## Finding

After CR-1009, `_infer_number_example` and `_infer_string_like_example` still encoded repeated
token checks directly in B-ranked helpers. That kept shared API example policy less reviewable than
the surrounding A-ranked inference helpers.

## Action

Added explicit number and string-like token-rule tables plus small helpers for identifier-string
examples, pattern-based string examples, and token matching. Existing direct OpenAPI inference
tests continue to pin representative generated examples.

## Result

`_infer_number_example` improved from `B (8)` to `A (3)`, and `_infer_string_like_example`
improved from `B (8)` to `A (4)`. `openapi_examples.py` improved from `B (16.35)` to
`B (17.47)` maintainability.

## Evidence

- `python -m pytest tests\unit\libs\portfolio-common\test_openapi_enrichment.py -q`
  => 6 passed
- `python -m ruff check src\libs\portfolio-common\portfolio_common\openapi_examples.py tests\unit\libs\portfolio-common\test_openapi_enrichment.py`
  => all checks passed
- `python -m ruff format --check src\libs\portfolio-common\portfolio_common\openapi_examples.py tests\unit\libs\portfolio-common\test_openapi_enrichment.py`
  => 2 files already formatted
- `python -m radon cc src\libs\portfolio-common\portfolio_common\openapi_examples.py -s`
  => `_infer_number_example` `A (3)` and `_infer_string_like_example` `A (4)`
- `python -m radon mi src\libs\portfolio-common\portfolio_common\openapi_examples.py -s`
  => `openapi_examples.py` `B (17.47)`
- `python -m radon raw src\libs\portfolio-common\portfolio_common\openapi_examples.py`
  => 351 SLOC / 227 LLOC
- `make openapi-gate`
  => passed
- `make quality-complexity-gate`
  => passed
- `make quality-maintainability-gate`
  => passed

## Wiki Decision

No wiki source update is required. This is an internal shared OpenAPI example classifier refactor
that preserves generated schema enrichment semantics.
