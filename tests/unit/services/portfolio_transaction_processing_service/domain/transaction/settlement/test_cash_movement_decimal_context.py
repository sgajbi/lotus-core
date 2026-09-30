"""Prove settlement cash economics do not inherit caller Decimal precision."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal, localcontext

import pytest

from src.services.portfolio_transaction_processing_service.app.domain.transaction import (
    BookedTransaction,
    build_generated_settlement_cash_leg,
)


def _transaction(
    transaction_type: str,
    *,
    gross_amount: str,
    trade_fee: str = "0",
    brokerage: str | None = None,
    stamp_duty: str | None = None,
) -> BookedTransaction:
    return BookedTransaction(
        transaction_id=f"CTX-{transaction_type}-001",
        portfolio_id="PORT-CTX-001",
        tenant_id="tenant-test",
        instrument_id="SEC-CTX-001",
        security_id="SEC-CTX-001",
        transaction_date=datetime(2026, 10, 1, 9, 0, tzinfo=UTC),
        settlement_date=datetime(2026, 10, 2, 9, 0, tzinfo=UTC),
        transaction_type=transaction_type,
        quantity=Decimal("1"),
        price=Decimal(gross_amount),
        gross_transaction_amount=Decimal(gross_amount),
        trade_currency="USD",
        currency="USD",
        transaction_fx_rate=Decimal("1.1234567890"),
        transaction_fx_rate_origin="SOURCE_BOOKED",
        trade_fee=Decimal(trade_fee),
        brokerage=Decimal(brokerage) if brokerage is not None else None,
        stamp_duty=Decimal(stamp_duty) if stamp_duty is not None else None,
        cash_entry_mode="AUTO_GENERATE",
        settlement_cash_account_id="CASH-ACC-USD-001",
        settlement_cash_instrument_id="CASH-USD",
    )


@pytest.mark.parametrize(
    (
        "transaction",
        "expected_local",
        "expected_base",
        "expected_magnitude",
        "expected_direction",
    ),
    [
        (
            _transaction(
                "BUY",
                gross_amount="1.1234567890",
                trade_fee="0.0000000001",
            ),
            Decimal("-1.1234567891"),
            Decimal("-1.2621551569"),
            Decimal("1.1234567891"),
            "OUTFLOW",
        ),
        (
            _transaction(
                "SELL",
                gross_amount="2.0000000000",
                trade_fee="99",
                brokerage="0.1234567890",
                stamp_duty="0.0000000001",
            ),
            Decimal("1.8765432109"),
            Decimal("2.1082152101"),
            Decimal("1.8765432109"),
            "INFLOW",
        ),
        (
            _transaction(
                "DIVIDEND",
                gross_amount="1.1234567890",
            ),
            Decimal("1.1234567890"),
            Decimal("1.2621551568"),
            Decimal("1.1234567890"),
            "INFLOW",
        ),
    ],
)
def test_generated_cash_economics_are_invariant_to_ambient_decimal_precision(
    transaction: BookedTransaction,
    expected_local: Decimal,
    expected_base: Decimal,
    expected_magnitude: Decimal,
    expected_direction: str,
) -> None:
    observed: list[tuple[Decimal | None, Decimal | None, Decimal | None, Decimal, str | None]] = []

    for precision in (6, 28):
        with localcontext() as context:
            context.prec = precision
            cash_leg = build_generated_settlement_cash_leg(transaction)
            observed.append(
                (
                    cash_leg.net_cost_local,
                    cash_leg.net_cost,
                    cash_leg.gross_cost,
                    cash_leg.gross_transaction_amount,
                    cash_leg.movement_direction,
                )
            )

    expected = (
        expected_local,
        expected_base,
        expected_base,
        expected_magnitude,
        expected_direction,
    )
    assert observed == [expected, expected]
