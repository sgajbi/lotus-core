# CR-323 Database URL Scheme Compatibility Fence

## Scope
Shared DB URL normalization in `portfolio_common.db`.

## Finding
Shared DB helpers only normalized `postgresql://` and `postgresql+asyncpg://` URLs. A common `postgres://...` database URL would therefore pass through broken, causing sync or async engine initialization failures across services.

## Fix
Added shared DB URL scheme normalization that:
- upgrades `postgres://` to `postgresql://`
- converts sync URLs to `postgresql+asyncpg://` for async mode
- strips `+asyncpg` back to `postgresql://` for sync mode

## Evidence
- `python -m pytest tests/unit/libs/portfolio-common/test_db.py -q`
- `python -m ruff check src/libs/portfolio-common/portfolio_common/db.py tests/unit/libs/portfolio-common/test_db.py`
