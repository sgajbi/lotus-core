"""Prove long redemption streams retain bounded per-event lot evidence."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from src.services.portfolio_transaction_processing_service.app.application import (
    build_cost_basis_timeline_processor,
)


def _transaction(
    *,
    transaction_id: str,
    transaction_date: datetime,
    transaction_type: str,
    quantity: str,
    price: str,
    gross_amount: str,
) -> dict[str, object]:
    return {
        "transaction_id": transaction_id,
        "portfolio_id": "PORT-REDEMPTION-CAPACITY-01",
        "instrument_id": "FO_FI_REDEMPTION_CAPACITY_01",
        "security_id": "FO_FI_REDEMPTION_CAPACITY_01",
        "transaction_date": transaction_date.isoformat(),
        "settlement_date": transaction_date.isoformat(),
        "transaction_type": transaction_type,
        "quantity": quantity,
        "price": price,
        "gross_transaction_amount": gross_amount,
        "principal_proceeds_local": Decimal(gross_amount),
        "trade_currency": "USD",
        "portfolio_base_currency": "USD",
        "transaction_fx_rate": "1",
        "trade_fee": "0",
        "product_type": "BOND",
        "asset_class": "FIXED_INCOME",
    }


@pytest.mark.parametrize("cost_basis_method", ["FIFO", "AVCO"])
def test_thousand_redemptions_keep_one_source_allocation_per_event(
    cost_basis_method: str,
) -> None:
    started_at = datetime(2026, 1, 1, tzinfo=UTC)
    timeline = [
        _transaction(
            transaction_id="BUY-REDEMPTION-CAPACITY-01",
            transaction_date=started_at,
            transaction_type="BUY",
            quantity="1000",
            price="0.97",
            gross_amount="970",
        )
    ]
    timeline.extend(
        _transaction(
            transaction_id=f"PARTIAL-REDEMPTION-CAPACITY-{ordinal:04d}",
            transaction_date=started_at + timedelta(seconds=ordinal),
            transaction_type=("MATURITY_REDEMPTION" if ordinal == 1000 else "PARTIAL_REDEMPTION"),
            quantity="1",
            price="1",
            gross_amount="1",
        )
        for ordinal in range(1, 1001)
    )

    result = build_cost_basis_timeline_processor(cost_basis_method).process_transactions(
        [], timeline
    )

    assert result.errored == []
    assert len(result.processed) == 1001
    assert len(result.disposals) == 1000
    assert all(len(disposal.result.allocations) == 1 for disposal in result.disposals)
    assert sum(
        (disposal.result.consumed_quantity for disposal in result.disposals),
        Decimal(0),
    ) == Decimal("1000")
    assert sum(
        (disposal.result.cost_local for disposal in result.disposals),
        Decimal(0),
    ) == Decimal("970")
    assert result.open_lot_states["BUY-REDEMPTION-CAPACITY-01"].quantity == Decimal(0)
    assert result.open_lot_states["BUY-REDEMPTION-CAPACITY-01"].cost_local == Decimal(0)
    assert result.open_lot_states["BUY-REDEMPTION-CAPACITY-01"].cost_base == Decimal(0)
