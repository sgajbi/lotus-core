"""PostgreSQL proof that governed numerics cannot be silently normalized."""

from decimal import Decimal

import pytest
from portfolio_common.domain.financial.precision import DecimalPrecisionError
from portfolio_common.financial_numeric import ExactNumeric
from sqlalchemy import Column, Integer, MetaData, Table, select
from sqlalchemy.exc import StatementError

pytestmark = [pytest.mark.integration_db, pytest.mark.db_direct]


def _assert_precision_rejected(connection, table: Table, **values: Decimal) -> None:
    with pytest.raises(StatementError) as error:
        connection.execute(table.insert().values(**values))
    assert isinstance(error.value.orig, DecimalPrecisionError)


def test_exact_numeric_round_trip_replay_and_rejection_are_deterministic(
    db_engine,
    clean_db,
) -> None:
    metadata = MetaData()
    facts = Table(
        "exact_financial_numeric_proof",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("bounded_18_10", ExactNumeric(18, 10), nullable=False),
        Column("bounded_18_4", ExactNumeric(18, 4), nullable=False),
        Column("exact_unbounded", ExactNumeric(), nullable=False),
        prefixes=["TEMPORARY"],
    )
    accepted = {
        "id": 1,
        "bounded_18_10": Decimal("99999999.9999999999"),
        "bounded_18_4": Decimal("99999999999999.9999"),
        "exact_unbounded": Decimal("9" * 200 + "." + "8" * 200),
    }

    with db_engine.begin() as connection:
        metadata.create_all(connection)
        connection.execute(facts.insert().values(**accepted))
        persisted = connection.execute(select(facts).where(facts.c.id == 1)).mappings().one()

        assert dict(persisted) == accepted

        replay = connection.execute(
            facts.update()
            .where(facts.c.id == 1)
            .values(**{k: v for k, v in accepted.items() if k != "id"})
        )
        assert replay.rowcount == 1
        assert (
            dict(connection.execute(select(facts).where(facts.c.id == 1)).mappings().one())
            == accepted
        )

        _assert_precision_rejected(
            connection,
            facts,
            id=2,
            bounded_18_10=Decimal("1.00000000001"),
            bounded_18_4=Decimal("1.0000"),
            exact_unbounded=Decimal("1"),
        )
        _assert_precision_rejected(
            connection,
            facts,
            id=3,
            bounded_18_10=Decimal("100000000.0000000000"),
            bounded_18_4=Decimal("1.0000"),
            exact_unbounded=Decimal("1"),
        )
        _assert_precision_rejected(
            connection,
            facts,
            id=4,
            bounded_18_10=Decimal("1.0000000000"),
            bounded_18_4=Decimal("1.00001"),
            exact_unbounded=Decimal("1"),
        )
        _assert_precision_rejected(
            connection,
            facts,
            id=5,
            bounded_18_10=Decimal("1.0000000000"),
            bounded_18_4=Decimal("100000000000000.0000"),
            exact_unbounded=Decimal("1"),
        )

        assert connection.execute(select(facts.c.id)).scalars().all() == [1]
