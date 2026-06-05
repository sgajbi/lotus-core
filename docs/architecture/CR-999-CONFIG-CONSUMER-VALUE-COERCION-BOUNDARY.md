# CR-999: Config Consumer Value Coercion Boundary

Date: 2026-06-05

## Scope

Split Kafka consumer override value coercion into focused boolean, integer, string, positive-integer,
and `auto.offset.reset` normalization helpers without changing allowed override keys, accepted
value forms, validation failures, or sanitized override output.

## Finding

`_coerce_consumer_config_value` mixed boolean string parsing, integer parsing, positive integer
validation, string validation, `auto.offset.reset` normalization, allowed-value validation, and
passthrough handling in one C-ranked helper. That made the shared Kafka consumer override policy
harder to review and harder to extend safely.

## Action

Added type-specific coercion helpers plus focused integer parsing, positive-integer enforcement,
and `auto.offset.reset` normalization helpers while keeping `_coerce_consumer_config_value` as the
single dispatch boundary used by override sanitization.

## Result

`_coerce_consumer_config_value` improved from `C (16)` to `A (4)`. The extracted consumer coercion
helpers are A-ranked, and `config.py` remains A-ranked maintainability at `A (34.38)`.
`get_kafka_consumer_runtime_overrides` remains a separate B-ranked runtime override loading
boundary for the next slice.

## Evidence

- `python -m pytest tests\unit\libs\portfolio-common\test_config.py -q`
  => 18 passed
- `python -m ruff check src\libs\portfolio-common\portfolio_common\config.py tests\unit\libs\portfolio-common\test_config.py`
  => all checks passed
- `python -m ruff format --check src\libs\portfolio-common\portfolio_common\config.py tests\unit\libs\portfolio-common\test_config.py`
  => 2 files already formatted
- `python -m radon cc src\libs\portfolio-common\portfolio_common\config.py -s`
  => `_coerce_consumer_config_value` `A (4)`, `_coerce_consumer_bool_value` `A (5)`,
  `_coerce_consumer_int_value` `A (1)`, `_parse_consumer_int_value` `A (4)`,
  `_require_positive_consumer_int_value` `A (3)`, `_coerce_consumer_str_value` `A (3)`, and
  `_normalize_auto_offset_reset_value` `A (2)`
- `python -m radon mi src\libs\portfolio-common\portfolio_common\config.py -s`
  => `config.py` `A (34.38)`
- `python -m radon raw src\libs\portfolio-common\portfolio_common\config.py`
  => 524 SLOC / 202 LLOC
- `make quality-complexity-gate`
  => passed
- `make quality-maintainability-gate`
  => passed

## Wiki Decision

No wiki source update is required. This is an internal shared configuration coercion refactor that
preserves Kafka consumer override semantics.
