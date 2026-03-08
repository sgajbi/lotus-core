# src/services/timeseries_generator_service/app/core/position_timeseries_logic.py
from decimal import Decimal
from typing import List

from portfolio_common.database_models import (
    PositionTimeseries,
    DailyPositionSnapshot,
    Cashflow,
)


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
            previous_snapshot.market_value_local
            if previous_snapshot and previous_snapshot.market_value_local is not None
            else Decimal(0)
        )

        eod_market_value = current_snapshot.market_value_local or Decimal(0)
        eod_quantity = current_snapshot.quantity
        eod_cost_basis = current_snapshot.cost_basis_local or Decimal(0)

        eod_avg_cost = (eod_cost_basis / eod_quantity) if eod_quantity else Decimal(0)

        bod_cf_pos, eod_cf_pos = Decimal(0), Decimal(0)
        bod_cf_port, eod_cf_port = Decimal(0), Decimal(0)

        for cf in cashflows:
            if cf.is_position_flow:
                if cf.timing == "BOD":
                    bod_cf_pos += cf.amount
                else:  # EOD
                    eod_cf_pos += cf.amount

            if cf.is_portfolio_flow:
                if cf.timing == "BOD":
                    bod_cf_port += cf.amount
                else:  # EOD
                    eod_cf_port += cf.amount

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
            fees=Decimal(0),
            quantity=eod_quantity,
            cost=eod_avg_cost,
        )
