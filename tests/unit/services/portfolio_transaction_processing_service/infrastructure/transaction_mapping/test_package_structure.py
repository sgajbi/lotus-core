"""Protect the transaction anti-corruption mapping package boundary."""

from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[6]


def test_transaction_mappers_use_one_domain_owned_package() -> None:
    source_root = (
        REPOSITORY_ROOT / "src/services/portfolio_transaction_processing_service/app/infrastructure"
    )
    required_sources = (
        source_root / "transaction_mapping/booked_transaction.py",
        source_root / "transaction_mapping/foreign_exchange_instrument.py",
    )
    retired_sources = (
        source_root / "booked_transaction_event_mapper.py",
        source_root / "fx_event_mapper.py",
    )
    retired_tests = (
        REPOSITORY_ROOT / "tests/unit/services/portfolio_transaction_processing_service/"
        "test_booked_transaction_event_mapper.py",
        REPOSITORY_ROOT
        / "tests/unit/services/portfolio_transaction_processing_service/test_fx_event_mapper.py",
    )

    assert all(path.is_file() for path in required_sources)
    assert all(not path.exists() for path in (*retired_sources, *retired_tests))
