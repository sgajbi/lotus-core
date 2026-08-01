"""Pure arithmetic policy for portfolio-timeseries aggregation."""

from dataclasses import replace
from datetime import date
from decimal import Decimal

from portfolio_common.domain.calculation_lineage import build_calculation_lineage
from portfolio_common.domain.decimal_amount import decimal_or_zero

from .errors import (
    DuplicatePortfolioPositionContribution,
    InvalidPortfolioAggregationScope,
    PortfolioContributionScopeMismatch,
    PortfolioContributionWindowMismatch,
)
from .models import (
    PortfolioAggregationScope,
    PortfolioPositionContribution,
    PortfolioTimeseriesRecord,
)
from .numeric_policy import PORTFOLIO_TIMESERIES_LEDGER_OUTPUT_V1

ZERO = Decimal("0")


def calculate_portfolio_timeseries(
    *,
    portfolio: PortfolioAggregationScope,
    aggregation_date: date,
    epoch: int,
    contributions: list[PortfolioPositionContribution],
) -> PortfolioTimeseriesRecord:
    """Aggregate one validated portfolio-day contribution set in reporting currency."""

    total_bod_market_value = ZERO
    total_bod_cashflow = ZERO
    total_eod_cashflow = ZERO
    total_eod_market_value = ZERO
    total_fees = ZERO
    portfolio_id = portfolio.portfolio_id.strip()
    if not portfolio_id:
        raise InvalidPortfolioAggregationScope(
            "Portfolio aggregation requires an authoritative portfolio identity."
        )
    seen_security_ids: set[str] = set()

    policy = PORTFOLIO_TIMESERIES_LEDGER_OUTPUT_V1
    with policy.arithmetic_context():
        ordered_contributions = sorted(
            contributions,
            key=lambda contribution: contribution.position_timeseries.security_id.strip(),
        )
        for contribution in ordered_contributions:
            position = contribution.position_timeseries
            security_id = position.security_id.strip()
            if position.portfolio_id.strip() != portfolio_id:
                raise PortfolioContributionScopeMismatch(
                    "Position contribution belongs to a different portfolio scope."
                )
            if position.date > aggregation_date or position.epoch > epoch:
                raise PortfolioContributionWindowMismatch(
                    "Position contribution is later than the target business date or epoch."
                )
            if security_id in seen_security_ids:
                raise DuplicatePortfolioPositionContribution(
                    "Portfolio aggregation received a duplicate security contribution."
                )
            seen_security_ids.add(security_id)

            fx_rate = contribution.fx_rate_to_portfolio_currency
            total_bod_market_value += decimal_or_zero(position.bod_market_value) * fx_rate
            total_bod_cashflow += decimal_or_zero(position.bod_cashflow_portfolio) * fx_rate
            total_eod_cashflow += decimal_or_zero(position.eod_cashflow_portfolio) * fx_rate
            total_eod_market_value += decimal_or_zero(position.eod_market_value) * fx_rate
            total_fees += decimal_or_zero(position.fees) * fx_rate

    record = PortfolioTimeseriesRecord(
        portfolio_id=portfolio.portfolio_id,
        date=aggregation_date,
        epoch=epoch,
        bod_market_value=policy.normalize(
            total_bod_market_value,
            field_name="bod_market_value",
        ),
        bod_cashflow=policy.normalize(
            total_bod_cashflow,
            field_name="bod_cashflow",
        ),
        eod_cashflow=policy.normalize(
            total_eod_cashflow,
            field_name="eod_cashflow",
        ),
        eod_market_value=policy.normalize(
            total_eod_market_value,
            field_name="eod_market_value",
        ),
        fees=policy.normalize(total_fees, field_name="fees"),
    )
    return replace(
        record,
        calculation_lineage=build_calculation_lineage(
            algorithm_id="portfolio-timeseries-aggregation",
            algorithm_version=1,
            intermediate_precision=policy.working_precision,
            input_payload=_portfolio_timeseries_input(
                portfolio=portfolio,
                aggregation_date=aggregation_date,
                epoch=epoch,
                contributions=ordered_contributions,
            ),
            output_payload=_portfolio_timeseries_output(record),
            numeric_output_policy=policy.lineage_identity(),
        ),
    )


def _portfolio_timeseries_input(
    *,
    portfolio: PortfolioAggregationScope,
    aggregation_date: date,
    epoch: int,
    contributions: list[PortfolioPositionContribution],
) -> dict[str, object]:
    """Return ordered position-day and FX facts used by portfolio aggregation."""

    return {
        "aggregation_date": aggregation_date,
        "contributions": [
            {
                "fx_rate_to_portfolio_currency": contribution.fx_rate_to_portfolio_currency,
                "position": {
                    "bod_cashflow_portfolio": position.bod_cashflow_portfolio,
                    "bod_market_value": position.bod_market_value,
                    "calculation_lineage": _position_lineage_payload(position),
                    "date": position.date,
                    "eod_cashflow_portfolio": position.eod_cashflow_portfolio,
                    "eod_market_value": position.eod_market_value,
                    "epoch": position.epoch,
                    "fees": position.fees,
                    "portfolio_id": position.portfolio_id,
                    "security_id": position.security_id,
                },
            }
            for contribution in contributions
            for position in (contribution.position_timeseries,)
        ],
        "epoch": epoch,
        "portfolio": {
            "base_currency": portfolio.base_currency,
            "portfolio_id": portfolio.portfolio_id,
        },
    }


def _position_lineage_payload(position: object) -> object:
    lineage = getattr(position, "calculation_lineage", None)
    return lineage.lineage_payload() if lineage is not None else None


def _portfolio_timeseries_output(record: PortfolioTimeseriesRecord) -> dict[str, object]:
    """Return every calculated field persisted for one portfolio day."""

    return {
        "bod_cashflow": record.bod_cashflow,
        "bod_market_value": record.bod_market_value,
        "date": record.date,
        "eod_cashflow": record.eod_cashflow,
        "eod_market_value": record.eod_market_value,
        "epoch": record.epoch,
        "fees": record.fees,
        "portfolio_id": record.portfolio_id,
    }
