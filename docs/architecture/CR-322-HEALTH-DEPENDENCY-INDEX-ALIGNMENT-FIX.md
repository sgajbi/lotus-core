# CR-322 Health Dependency Index Alignment Fix

## Scope
Shared health router readiness aggregation in `portfolio_common.health`.

## Finding
`create_health_router(...).readiness_probe()` gathered checks only for known dependencies but built dependency status by indexing results against the original dependency tuple. If an unknown dependency name appeared between valid ones, status mapping could misalign or raise `IndexError`.

## Fix
Resolved readiness checks into an ordered list of known `(name, check)` pairs first, then used that same resolved sequence for both `asyncio.gather(...)` and dependency status mapping.

## Evidence
- `python -m pytest tests/unit/libs/portfolio-common/test_health.py -q`
- `python -m ruff check src/libs/portfolio-common/portfolio_common/health.py tests/unit/libs/portfolio-common/test_health.py`
