from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

from src.services.query_service.app.services.transaction_cost_curve import (
    build_transaction_cost_curve_points,
    has_observed_transaction_cost_evidence,
    transaction_cost_curve_key,
    transaction_fee_amount,
)


def _transaction(
    *,
    transaction_id: str,
    security_id: str = " EQ_US_AAPL ",
    transaction_type: str = " buy ",
    currency: str = " usd ",
    gross_transaction_amount: str = "100000.0000",
    trade_fee: str | None = "20.0000",
    costs: list[SimpleNamespace] | None = None,
    transaction_date: datetime | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        transaction_id=transaction_id,
        security_id=security_id,
        transaction_type=transaction_type,
        currency=currency,
        gross_transaction_amount=Decimal(gross_transaction_amount),
        trade_fee=Decimal(trade_fee) if trade_fee is not None else None,
        costs=costs,
        transaction_date=transaction_date or datetime(2026, 5, 1, tzinfo=UTC),
    )


def test_transaction_cost_curve_uses_explicit_cost_rows_before_trade_fee() -> None:
    transaction = _transaction(
        transaction_id="TXN-AAPL-001",
        trade_fee="999.0000",
        costs=[SimpleNamespace(amount="12.5000"), SimpleNamespace(amount=Decimal("7.5000"))],
    )

    assert transaction_fee_amount(transaction) == Decimal("20.0000")
    assert has_observed_transaction_cost_evidence(transaction) is True
    assert transaction_cost_curve_key(transaction) == ("EQ_US_AAPL", "BUY", "USD")


def test_transaction_cost_curve_points_group_and_filter_evidence() -> None:
    points = build_transaction_cost_curve_points(
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        transactions=[
            _transaction(
                transaction_id="TXN-AAPL-002",
                gross_transaction_amount="200000.0000",
                trade_fee="30.0000",
                transaction_date=datetime(2026, 5, 3, tzinfo=UTC),
            ),
            _transaction(
                transaction_id="TXN-AAPL-001",
                gross_transaction_amount="100000.0000",
                trade_fee="20.0000",
                transaction_date=datetime(2026, 5, 1, tzinfo=UTC),
            ),
            _transaction(
                transaction_id="TXN-MSFT-ZERO-FEE",
                security_id="EQ_US_MSFT",
                trade_fee="0.0000",
            ),
        ],
        min_observation_count=2,
    )

    assert len(points) == 1
    point = points[0]
    assert point.portfolio_id == "PB_SG_GLOBAL_BAL_001"
    assert point.security_id == "EQ_US_AAPL"
    assert point.transaction_type == "BUY"
    assert point.currency == "USD"
    assert point.observation_count == 2
    assert point.total_notional == Decimal("300000.0000")
    assert point.total_cost == Decimal("50.0000")
    assert point.average_cost_bps == Decimal("1.6667")
    assert point.min_cost_bps == Decimal("1.5000")
    assert point.max_cost_bps == Decimal("2.0000")
    assert point.first_observed_date.isoformat() == "2026-05-01"
    assert point.last_observed_date.isoformat() == "2026-05-03"
    assert point.sample_transaction_ids == ["TXN-AAPL-001", "TXN-AAPL-002"]
    assert point.source_lineage["source_table"] == "transactions,transaction_costs"
