from dataclasses import dataclass
from decimal import Decimal
from typing import List

from portfolio_common.analytics_cashflow_semantics import (
    normalize_cashflow_timing,
    normalize_position_flow_amount,
)
from portfolio_common.database_models import (
    Cashflow,
    DailyPositionSnapshot,
    PositionTimeseries,
)
from portfolio_common.decimal_amounts import decimal_or_none

# src/services/timeseries_generator_service/app/core/position_timeseries_logic.py

ZERO = Decimal("0")


def _decimal_or_zero(value: object) -> Decimal:
    amount = decimal_or_none(value)
    return amount if amount is not None else ZERO


def _beginning_market_value(previous_snapshot: DailyPositionSnapshot | None) -> Decimal:
    if previous_snapshot and previous_snapshot.market_value_local is not None:
        return _decimal_or_zero(previous_snapshot.market_value_local)
    return ZERO


def _average_cost(*, cost_basis: Decimal, quantity: Decimal) -> Decimal:
    return (cost_basis / quantity) if quantity else ZERO


def _is_expense_cashflow(cashflow: Cashflow) -> bool:
    return str(cashflow.classification or "").strip().upper() == "EXPENSE"


@dataclass
class _CashflowBuckets:
    bod_position: Decimal = ZERO
    eod_position: Decimal = ZERO
    bod_portfolio: Decimal = ZERO
    eod_portfolio: Decimal = ZERO
    fees: Decimal = ZERO

    def add(self, cashflow: Cashflow) -> None:
        cashflow_amount = _decimal_or_zero(cashflow.amount)
        timing = normalize_cashflow_timing(cashflow.timing)
        if cashflow.is_position_flow:
            self._add_position_flow(cashflow, cashflow_amount, timing)
        if cashflow.is_portfolio_flow:
            self._add_portfolio_flow(cashflow_amount, timing)
        if _is_expense_cashflow(cashflow):
            self.fees += abs(cashflow_amount)

    def _add_position_flow(self, cashflow: Cashflow, amount: Decimal, timing: str) -> None:
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


def _cashflow_buckets(cashflows: List[Cashflow]) -> _CashflowBuckets:
    buckets = _CashflowBuckets()
    for cashflow in cashflows:
        buckets.add(cashflow)
    return buckets


class PositionTimeseriesLogic:
    """
    A stateless calculator for generating a single daily position time series record.
    """

    @staticmethod
    def calculate_daily_record(
        current_snapshot: DailyPositionSnapshot,
        previous_snapshot: DailyPositionSnapshot | None,
        cashflows: List[Cashflow],
        epoch: int,
    ) -> PositionTimeseries:
        """
        Calculates a single, complete position time series record for a given day.
        """
        bod_market_value = _beginning_market_value(previous_snapshot)
        eod_market_value = _decimal_or_zero(current_snapshot.market_value_local)
        eod_quantity = _decimal_or_zero(current_snapshot.quantity)
        eod_cost_basis = _decimal_or_zero(current_snapshot.cost_basis_local)
        eod_avg_cost = _average_cost(cost_basis=eod_cost_basis, quantity=eod_quantity)
        cashflow_buckets = _cashflow_buckets(cashflows)

        return PositionTimeseries(
            portfolio_id=current_snapshot.portfolio_id,
            security_id=current_snapshot.security_id,
            date=current_snapshot.date,
            epoch=epoch,
            bod_market_value=bod_market_value,
            bod_cashflow_position=cashflow_buckets.bod_position,
            eod_cashflow_position=cashflow_buckets.eod_position,
            bod_cashflow_portfolio=cashflow_buckets.bod_portfolio,
            eod_cashflow_portfolio=cashflow_buckets.eod_portfolio,
            eod_market_value=eod_market_value,
            fees=cashflow_buckets.fees,
            quantity=eod_quantity,
            cost=eod_avg_cost,
        )
