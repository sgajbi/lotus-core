# CR-319 Shared Config Boolean Fallback Truth

## Scope
Shared boolean environment parsing in `portfolio_common.config`.

## Finding
`BUSINESS_DATE_ENFORCE_MONOTONIC_ADVANCE` still used ad hoc string membership logic at import time. Invalid operator values such as `maybe` were silently treated as `false`, which hid misconfiguration and made the applied policy ambiguous.

## Fix
Added shared `_env_bool(...)` parsing with explicit true/false vocab and warning evidence for invalid values, then routed `BUSINESS_DATE_ENFORCE_MONOTONIC_ADVANCE` through it.

## Evidence
- `python -m pytest tests/unit/libs/portfolio-common/test_config.py -q`
- `python -m ruff check src/libs/portfolio-common/portfolio_common/config.py tests/unit/libs/portfolio-common/test_config.py`
