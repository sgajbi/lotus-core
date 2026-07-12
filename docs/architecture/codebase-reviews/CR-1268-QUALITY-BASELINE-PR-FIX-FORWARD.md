# CR-1268 Quality Baseline PR Fix-Forward

Date: 2026-07-01

## Objective

Fix the first PR #695 Quality Baseline failures without weakening the gates. The failing checks were
Ruff import ordering, Bandit `assert_used`, and Deptry direct-transitive dependency usage.

## Change

- Organized the five import blocks flagged by the broad Ruff regression gate.
- Replaced simulation mutation-path `assert session is not None` statements with an explicit
  `_require_active_session(...)` helper that preserves the existing not-found, inactive, and expired
  session errors while avoiding production assertions.
- Changed the CORS middleware import in `portfolio_common.http_app_bootstrap` from the direct
  Starlette path to FastAPI's public middleware path so source dependency checks do not rely on a
  transitive dependency.

## Validation Evidence

- `python -m ruff check . --statistics`: passed.
- `python -m bandit -r src -c pyproject.toml`: passed with no issues.
- `python -m deptry src --extend-exclude "src/services/query_service/build" --extend-exclude ".*/tests/"`:
  passed with no dependency issues.
- `python -m ruff format --check .`: passed.
- `make typecheck`: passed.
- `python -m pytest tests/unit/services/query_service/services/test_simulation_service.py -q`:
  31 passed.
- `python -m pytest tests/unit/libs/portfolio-common/test_http_app_bootstrap.py -q`: 15 passed.

## Downstream Compatibility

No route, API contract, database schema, Kafka topic, or response DTO changed. Simulation mutation
behavior is preserved; the change removes optimization-sensitive assertions from production code.

## Documentation And Wiki Decision

Updated this architecture record and the codebase review ledger. No README or wiki update is
required because this is a CI fix-forward and production-code hardening slice without an
operator-facing behavior change.
