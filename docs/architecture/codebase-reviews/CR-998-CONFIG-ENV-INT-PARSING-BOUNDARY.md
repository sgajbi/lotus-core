# CR-998: Config Env Integer Parsing Boundary

Date: 2026-06-05

## Scope

Split shared integer environment parsing into default coercion, environment-value parsing, and
minimum enforcement helpers without changing default fallback behavior, invalid-value warning
behavior, out-of-range warning behavior, or import-time guardrail configuration semantics.

## Finding

`_env_int` mixed default coercion, environment lookup, invalid integer parsing, warning emission,
minimum checking, out-of-range warning emission, and fallback selection in one B-ranked helper. This
made shared runtime configuration parsing harder to review as guardrail and cache settings grew.

## Action

Added focused helpers for safe integer defaults, environment integer loading, and minimum
enforcement while keeping `_env_int` as the public configuration parsing boundary.

## Result

`_env_int` improved from `B (7)` to `A (1)`. The extracted helpers are A-ranked, and `config.py`
remains A-ranked maintainability at `A (35.12)`.

## Evidence

- `python -m pytest tests\unit\libs\portfolio-common\test_config.py -q`
  => 16 passed
- `python -m ruff check src\libs\portfolio-common\portfolio_common\config.py tests\unit\libs\portfolio-common\test_config.py`
  => all checks passed
- `python -m ruff format --check src\libs\portfolio-common\portfolio_common\config.py tests\unit\libs\portfolio-common\test_config.py`
  => 2 files already formatted
- `python -m radon cc src\libs\portfolio-common\portfolio_common\config.py -s`
  => `_env_int` `A (1)`, `_safe_int_default` `A (2)`, `_load_env_int_value` `A (3)`, and `_enforce_env_int_minimum` `A (4)`
- `python -m radon mi src\libs\portfolio-common\portfolio_common\config.py -s`
  => `config.py` `A (35.12)`
- `python -m radon raw src\libs\portfolio-common\portfolio_common\config.py`
  => 513 SLOC / 191 LLOC
- `make quality-complexity-gate`
  => passed
- `make quality-maintainability-gate`
  => passed

## Wiki Decision

No wiki source update is required. This is an internal shared configuration parsing helper refactor
that preserves runtime environment fallback semantics.
