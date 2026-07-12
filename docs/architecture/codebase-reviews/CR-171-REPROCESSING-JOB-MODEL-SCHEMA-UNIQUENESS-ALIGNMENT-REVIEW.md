# CR-171 Reprocessing Job Model Schema Uniqueness Alignment Review

## Finding
The database already enforced a partial unique index for pending `RESET_WATERMARKS`
jobs keyed by `payload->>'security_id'`, and the integration suite already relied on
that contract. The SQLAlchemy model still only declared the non-unique priority
index, so the ORM metadata was drifting away from the real durable invariant.

## Change
Added the missing partial unique index declaration to `ReprocessingJob` and added a
metadata-level unit test that proves the model advertises the same uniqueness
contract as the database migration.

## Outcome
The durable replay queue now has one source of truth across:
- migration history
- ORM metadata
- integration tests

That makes future replay-queue refactors less error-prone and keeps the banking
control-path invariant explicit instead of accidental.

## Evidence
- `src/libs/portfolio-common/portfolio_common/database_models.py`
- `tests/unit/libs/portfolio-common/test_database_models.py`
- `alembic/versions/e4f5a6b7c8d9_feat_add_pending_reset_watermarks_uniqueness.py`
