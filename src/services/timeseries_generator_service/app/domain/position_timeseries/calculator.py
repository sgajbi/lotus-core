"""Pure calculation policy for one position-timeseries business day."""

from dataclasses import dataclass
from decimal import Decimal

from portfolio_common.domain.analytics.cashflow_semantics import (
    normalize_cashflow_timing,
    normalize_position_flow_amount,
)
from portfolio_common.domain.decimal_amount import decimal_or_none

from .models import PositionCashflowRecord, PositionSnapshotRecord, PositionTimeseriesRecord

ZERO = Decimal("0")


def _decimal_or_zero(value: object) -> Decimal:
    amount = decimal_or_none(value)
    return amount if amount is not None else ZERO


def _beginning_market_value(previous_snapshot: PositionSnapshotRecord | None) -> Decimal:
    if previous_snapshot and previous_snapshot.market_value_local is not None:
        return _decimal_or_zero(previous_snapshot.market_value_local)
    return ZERO


def _average_cost(*, cost_basis: Decimal, quantity: Decimal) -> Decimal:
    return (cost_basis / quantity) if quantity else ZERO


def _is_expense_cashflow(cashflow: PositionCashflowRecord) -> bool:
    return str(cashflow.classification or "").strip().upper() == "EXPENSE"


@dataclass(slots=True)
class _CashflowBuckets:
    bod_position: Decimal = ZERO
    eod_position: Decimal = ZERO
    bod_portfolio: Decimal = ZERO
    eod_portfolio: Decimal = ZERO
    fees: Decimal = ZERO

    def add(self, cashflow: PositionCashflowRecord) -> None:
        cashflow_amount = _decimal_or_zero(cashflow.amount)
        timing = normalize_cashflow_timing(cashflow.timing)
        if cashflow.is_position_flow:
            self._add_position_flow(cashflow, cashflow_amount, timing)
        if cashflow.is_portfolio_flow:
            self._add_portfolio_flow(cashflow_amount, timing)
        if _is_expense_cashflow(cashflow):
            self.fees += abs(cashflow_amount)

    def _add_position_flow(
        self, cashflow: PositionCashflowRecord, amount: Decimal, timing: str
    ) -> None:
        normalized_position_amount = normalize_position_flow_amount(
            amount=amount,
            classification=str(cashflow.classification),
        )
        if timing == "BOD":
            self.bod_position += normalized_position_amount
        else:
            self.eod_position += normalized_position_amount

    def _add_portfolio_flow(self, amount: Decimal, timing: str) -> None:
        if timing == "BOD":
            self.bod_portfolio += amount
        else:
            self.eod_portfolio += amount


def _cashflow_buckets(cashflows: list[PositionCashflowRecord]) -> _CashflowBuckets:
    buckets = _CashflowBuckets()
    for cashflow in cashflows:
        buckets.add(cashflow)
    return buckets


def calculate_position_timeseries(
    *,
    current_snapshot: PositionSnapshotRecord,
    previous_snapshot: PositionSnapshotRecord | None,
    cashflows: list[PositionCashflowRecord],
    epoch: int,
) -> PositionTimeseriesRecord:
    """Calculate one complete position-timeseries record."""

    eod_quantity = _decimal_or_zero(current_snapshot.quantity)
    eod_cost_basis = _decimal_or_zero(current_snapshot.cost_basis_local)
    cashflow_buckets = _cashflow_buckets(cashflows)

    return PositionTimeseriesRecord(
        portfolio_id=current_snapshot.portfolio_id,
        security_id=current_snapshot.security_id,
        date=current_snapshot.date,
        epoch=epoch,
        bod_market_value=_beginning_market_value(previous_snapshot),
        bod_cashflow_position=cashflow_buckets.bod_position,
        eod_cashflow_position=cashflow_buckets.eod_position,
        bod_cashflow_portfolio=cashflow_buckets.bod_portfolio,
        eod_cashflow_portfolio=cashflow_buckets.eod_portfolio,
        eod_market_value=_decimal_or_zero(current_snapshot.market_value_local),
        fees=cashflow_buckets.fees,
        quantity=eod_quantity,
        cost=_average_cost(cost_basis=eod_cost_basis, quantity=eod_quantity),
    )
