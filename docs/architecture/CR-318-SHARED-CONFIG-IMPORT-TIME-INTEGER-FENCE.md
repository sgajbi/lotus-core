# CR-318 Shared Config Import-Time Integer Fence

## Scope
Shared import-time environment parsing in `portfolio_common.config`.

## Finding
`BUSINESS_DATE_MAX_FUTURE_DAYS` and `CASHFLOW_RULE_CACHE_TTL_SECONDS` still used raw `int(os.getenv(...))` at module import time. Invalid env values could therefore crash service startup across the platform before runtime supervision or service-level classification even began.

## Fix
Added shared `_env_int(...)` parsing with fallback and warning evidence, and routed both import-time settings through it:
- `BUSINESS_DATE_MAX_FUTURE_DAYS` now falls back safely to `0`
- `CASHFLOW_RULE_CACHE_TTL_SECONDS` now falls back safely to `300`
- out-of-range values also fall back instead of poisoning shared startup

## Evidence
- `python -m pytest tests/unit/libs/portfolio-common/test_config.py -q`
- `python -m ruff check src/libs/portfolio-common/portfolio_common/config.py tests/unit/libs/portfolio-common/test_config.py`
