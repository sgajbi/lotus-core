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
        bod_market_value = (
            _decimal_or_zero(previous_snapshot.market_value_local)
            if previous_snapshot and previous_snapshot.market_value_local is not None
            else ZERO
        )

        eod_market_value = _decimal_or_zero(current_snapshot.market_value_local)
        eod_quantity = _decimal_or_zero(current_snapshot.quantity)
        eod_cost_basis = _decimal_or_zero(current_snapshot.cost_basis_local)

        eod_avg_cost = (eod_cost_basis / eod_quantity) if eod_quantity else ZERO

        bod_cf_pos, eod_cf_pos = ZERO, ZERO
        bod_cf_port, eod_cf_port = ZERO, ZERO
        total_fees = ZERO

        for cf in cashflows:
            cashflow_amount = _decimal_or_zero(cf.amount)
            cashflow_timing = normalize_cashflow_timing(cf.timing)
            if cf.is_position_flow:
                normalized_position_amount = normalize_position_flow_amount(
                    amount=cashflow_amount,
                    classification=str(cf.classification),
                )
                if cashflow_timing == "BOD":
                    bod_cf_pos += normalized_position_amount
                else:  # EOD
                    eod_cf_pos += normalized_position_amount

            if cf.is_portfolio_flow:
                if cashflow_timing == "BOD":
                    bod_cf_port += cashflow_amount
                else:  # EOD
                    eod_cf_port += cashflow_amount

            if str(cf.classification or "").strip().upper() == "EXPENSE":
                total_fees += abs(cashflow_amount)

        return PositionTimeseries(
            portfolio_id=current_snapshot.portfolio_id,
            security_id=current_snapshot.security_id,
            date=current_snapshot.date,
            epoch=epoch,
            bod_market_value=bod_market_value,
            bod_cashflow_position=bod_cf_pos,
            eod_cashflow_position=eod_cf_pos,
            bod_cashflow_portfolio=bod_cf_port,
            eod_cashflow_portfolio=eod_cf_port,
            eod_market_value=eod_market_value,
            fees=total_fees,
            quantity=eod_quantity,
            cost=eod_avg_cost,
        )
