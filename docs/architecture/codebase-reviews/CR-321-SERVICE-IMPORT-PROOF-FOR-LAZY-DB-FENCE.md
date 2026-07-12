# CR-321 Service Import Proof For Lazy DB Fence

## Scope
Representative service import path for the shared lazy DB engine initialization change.

## Finding
`CR-320` moved DB engine creation behind lazy helpers, but there was still no representative service-level proof that a real service module importing `SessionLocal` from `portfolio_common.db` no longer triggered engine creation at import time.

## Fix
Added a direct `query_service.capabilities_service` import proof showing that reloading the real service module after reloading `portfolio_common.db` does not create sync or async SQLAlchemy engines until first DB use.

## Evidence
- `python -m pytest tests/unit/services/query_service/services/test_capabilities_service.py -q`
- `python -m ruff check tests/unit/services/query_service/services/test_capabilities_service.py`
