"""Static contract for transaction FX-rate provenance migration."""

from pathlib import Path


def test_fx_rate_origin_migration_is_unknown_backfilled_and_reversible() -> None:
    migration = (
        Path(__file__).resolve().parents[2]
        / "alembic"
        / "versions"
        / "c175b2c3d536_add_transaction_fx_rate_origin.py"
    ).read_text(encoding="utf-8")

    assert 'revision: str = "c175b2c3d536"' in migration
    assert 'down_revision: str | Sequence[str] | None = "c174b2c3d535"' in migration
    assert "SET transaction_fx_rate_origin = 'LEGACY_UNKNOWN'" in migration
    assert "WHERE transaction_fx_rate IS NOT NULL" in migration
    assert "'SOURCE_BOOKED', 'REFERENCE_DERIVED', 'LEGACY_UNKNOWN'" in migration
    assert 'op.drop_column("transactions", "transaction_fx_rate_origin")' in migration
