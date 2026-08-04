"""Verify the additive external transfer destination migration and ORM parity."""

from pathlib import Path

from portfolio_common.database_models import Transaction

MIGRATION = Path(
    "alembic/versions/c148b2c3d515_feat_add_external_transfer_destination.py"
)


def test_transaction_model_exposes_nullable_external_destination_reference() -> None:
    column = Transaction.__table__.c.external_destination_reference

    assert column.nullable is True
    assert column.type.python_type is str


def test_migration_is_linear_additive_and_reversible() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    assert 'down_revision: str | Sequence[str] | None = "c147b2c3d514"' in source
    assert 'sa.Column("external_destination_reference", sa.String(), nullable=True)' in source
    assert 'op.drop_column("transactions", "external_destination_reference")' in source
