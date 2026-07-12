# CR-320 Lazy DB Engine Initialization Fence

## Scope
Shared database bootstrap in `portfolio_common.db`.

## Finding
`portfolio_common.db` created sync and async SQLAlchemy engines at module import time. Invalid DB URLs, missing drivers, or bootstrap-time environment issues could therefore crash shared imports before any service-level runtime supervision or startup classification began.

## Fix
Moved sync and async engine/sessionmaker creation behind lazy cached helpers while preserving the existing `SessionLocal()` and `AsyncSessionLocal()` call pattern used across the codebase.

## Evidence
- `python -m pytest tests/unit/libs/portfolio-common/test_db.py -q`
- `python -m ruff check src/libs/portfolio-common/portfolio_common/db.py tests/unit/libs/portfolio-common/test_db.py`
