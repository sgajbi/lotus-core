# CR-1000: Kafka Consumer Runtime Override Loading Boundary

Date: 2026-06-05

## Scope

Split Kafka consumer runtime override loading into focused defaults, group override, group
sanitization, and group-context helpers without changing environment variable names, layer
precedence, invalid JSON handling, unsupported-key filtering, or final merged heartbeat/session
relationship validation.

## Finding

`get_kafka_consumer_runtime_overrides` still mixed defaults JSON loading, defaults sanitization,
group override JSON loading, group map validation, group-specific lookup, group sanitization,
per-source relationship validation, merge precedence, and final merged relationship validation in
one B-ranked function. That made the CR-314 merged-boundary relationship fence harder to review as
runtime override policy evolved.

## Action

Added named helpers for default override loading, group override loading, group override
sanitization, and group context formatting. The public function now only merges the two layers and
retains the final merged relationship validation boundary.

## Result

`get_kafka_consumer_runtime_overrides` improved from `B (7)` to `A (1)`. The extracted runtime
override loading helpers are A-ranked, and `config.py` remains A-ranked maintainability at
`A (33.36)`.

## Evidence

- `python -m pytest tests\unit\libs\portfolio-common\test_config.py -q`
  => 18 passed
- `python -m ruff check src\libs\portfolio-common\portfolio_common\config.py tests\unit\libs\portfolio-common\test_config.py`
  => all checks passed
- `python -m ruff format --check src\libs\portfolio-common\portfolio_common\config.py tests\unit\libs\portfolio-common\test_config.py`
  => 2 files already formatted
- `python -m radon cc src\libs\portfolio-common\portfolio_common\config.py -s`
  => `get_kafka_consumer_runtime_overrides` `A (1)`,
  `_load_consumer_defaults_overrides` `A (3)`, `_load_consumer_group_overrides` `A (5)`,
  `_sanitize_consumer_group_overrides` `A (1)`, and `_consumer_group_override_context` `A (1)`
- `python -m radon mi src\libs\portfolio-common\portfolio_common\config.py -s`
  => `config.py` `A (33.36)`
- `python -m radon raw src\libs\portfolio-common\portfolio_common\config.py`
  => 529 SLOC / 218 LLOC
- `make quality-complexity-gate`
  => passed
- `make quality-maintainability-gate`
  => passed

## Wiki Decision

No wiki source update is required. This is an internal shared configuration loading refactor that
preserves Kafka consumer runtime override semantics and the CR-314 final merged validation fence.
