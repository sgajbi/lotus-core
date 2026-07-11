from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal

from src.services.portfolio_transaction_processing_service.app.domain.cost_basis import (  # noqa: E501
    COST_BASIS_STATE_VERSION,
    CostBasisProcessingCheckpoint,
    CostBasisTransaction,
)


def _transaction(transaction_id: str, transaction_date: datetime) -> CostBasisTransaction:
    return CostBasisTransaction(
        transaction_id=transaction_id,
        portfolio_id="P1",
        instrument_id="I1",
        security_id="S1",
        transaction_type="BUY",
        transaction_date=transaction_date,
        quantity=Decimal("10"),
        gross_transaction_amount=Decimal("100"),
        trade_currency="USD",
        portfolio_base_currency="USD",
        transaction_fx_rate=Decimal("1"),
    )


def test_checkpoint_only_permits_canonically_later_matching_state() -> None:
    current = _transaction("BUY-1", datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc))
    later = _transaction("BUY-2", datetime(2026, 1, 1, 10, 1, tzinfo=timezone.utc))
    checkpoint = CostBasisProcessingCheckpoint.from_transaction(current, cost_basis_method="FIFO")

    assert checkpoint.calculation_state_version == COST_BASIS_STATE_VERSION
    assert checkpoint.permits_append(later, cost_basis_method="FIFO") is True
    assert checkpoint.permits_append(current, cost_basis_method="FIFO") is False
    assert checkpoint.permits_append(later, cost_basis_method="AVCO") is False


def test_checkpoint_rejects_unknown_calculation_state_version() -> None:
    current = _transaction("BUY-1", datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc))
    later = _transaction("BUY-2", datetime(2026, 1, 1, 10, 1, tzinfo=timezone.utc))
    checkpoint = replace(
        CostBasisProcessingCheckpoint.from_transaction(current, cost_basis_method="FIFO"),
        calculation_state_version="unsupported-v0",
    )

    assert checkpoint.permits_append(later, cost_basis_method="FIFO") is False
