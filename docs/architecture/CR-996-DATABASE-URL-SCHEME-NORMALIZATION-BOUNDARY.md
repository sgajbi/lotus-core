# CR-996: Database URL Scheme Normalization Boundary

Date: 2026-06-05

## Scope

Split shared database URL scheme normalization into legacy-postgres, async-driver, sync-driver, and
scheme-replacement helpers without changing sync URL selection, async URL selection, fallback URL
construction, SQLAlchemy engine laziness, or asyncpg driver behavior.

## Finding

`_normalize_database_url_scheme` mixed legacy `postgres://` conversion, async-mode driver
promotion, already-async handling, sync-mode asyncpg driver removal, and passthrough behavior in one
B-ranked helper. This made runtime database URL policy harder to review and test.

## Action

Added explicit scheme constants plus focused helpers for legacy normalization, async URL
normalization, sync URL normalization, and scheme replacement. Added focused tests for stripping
the asyncpg driver in sync mode and preserving it in async mode.

## Result

`_normalize_database_url_scheme` improved from `B (6)` to `A (2)`. All functions in `db.py` now
report A-ranked cyclomatic complexity, and the module remains A-ranked maintainability at
`A (66.86)`.

## Evidence

- `python -m pytest tests\unit\libs\portfolio-common\test_db.py -q`
  => 7 passed
- `python -m ruff check src\libs\portfolio-common\portfolio_common\db.py tests\unit\libs\portfolio-common\test_db.py`
  => all checks passed
- `python -m ruff format --check src\libs\portfolio-common\portfolio_common\db.py tests\unit\libs\portfolio-common\test_db.py`
  => 2 files already formatted
- `python -m radon cc src\libs\portfolio-common\portfolio_common\db.py -s`
  => `_normalize_database_url_scheme` `A (2)` and all functions A-ranked
- `python -m radon mi src\libs\portfolio-common\portfolio_common\db.py -s`
  => `db.py` `A (66.86)`
- `python -m radon raw src\libs\portfolio-common\portfolio_common\db.py`
  => 86 SLOC / 82 LLOC
- `make quality-complexity-gate`
  => passed
- `make quality-maintainability-gate`
  => passed

## Wiki Decision

No wiki source update is required. This is an internal shared runtime database URL helper refactor
that preserves sync and async database connection semantics.
