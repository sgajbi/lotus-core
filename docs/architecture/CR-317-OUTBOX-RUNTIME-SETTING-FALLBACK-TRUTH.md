# CR-317 Outbox Runtime Setting Fallback Truth

## Scope
Shared outbox dispatcher runtime settings.

## Finding
`outbox_settings.py` silently clamped invalid or non-positive env values to `1`. That hid bad operator configuration and could change shared dispatcher behavior in surprising ways instead of falling back to the documented defaults.

## Fix
Changed `_env_positive_int(...)` to:
- validate against a safe positive default
- fall back to the configured default instead of silently clamping invalid input to `1`
- emit warning logs when env values are invalid or non-positive

## Evidence
- `python -m pytest tests/unit/libs/portfolio-common/test_outbox_dispatcher.py -q`
- `python -m ruff check src/libs/portfolio-common/portfolio_common/outbox_settings.py tests/unit/libs/portfolio-common/test_outbox_dispatcher.py`
