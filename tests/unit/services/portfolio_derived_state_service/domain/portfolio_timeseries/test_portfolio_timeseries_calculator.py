"""Prove pure portfolio-timeseries aggregation arithmetic and scope invariants."""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from portfolio_common.domain.market_data.timeseries import TimeseriesFxRate

from src.services.portfolio_derived_state_service.app.domain.portfolio_timeseries import (
    DuplicatePortfolioPositionContribution,
    InvalidPortfolioAggregationScope,
    InvalidPortfolioPositionContribution,
    PortfolioContributionScopeMismatch,
    PortfolioContributionWindowMismatch,
    PortfolioPositionContribution,
    calculate_portfolio_timeseries,
)
from src.services.portfolio_derived_state_service.app.domain.portfolio_timeseries.models import (
    PortfolioAggregationScope,
)
from src.services.portfolio_derived_state_service.app.domain.position_timeseries.models import (
    PositionTimeseriesRecord,
)


def _position(
    security_id: str,
    *,
    portfolio_id: str = "PORT-AGG",
    business_date: date = date(2026, 3, 8),
    epoch: int = 2,
    bod_market_value: Decimal = Decimal("100"),
    bod_cashflow: Decimal = Decimal("1"),
    eod_cashflow: Decimal = Decimal("2"),
    eod_market_value: Decimal = Decimal("110"),
    fees: Decimal = Decimal("0.5"),
) -> PositionTimeseriesRecord:
    return PositionTimeseriesRecord(
        portfolio_id=portfolio_id,
        security_id=security_id,
        date=business_date,
        epoch=epoch,
        bod_market_value=bod_market_value,
        bod_cashflow_position=Decimal("0"),
        eod_cashflow_position=Decimal("0"),
        bod_cashflow_portfolio=bod_cashflow,
        eod_cashflow_portfolio=eod_cashflow,
        eod_market_value=eod_market_value,
        fees=fees,
        quantity=Decimal("0"),
        cost=Decimal("0"),
    )


def _scope() -> PortfolioAggregationScope:
    return PortfolioAggregationScope(portfolio_id="PORT-AGG", base_currency="USD")


def _fx_rate(
    rate: Decimal,
    *,
    rate_date: date = date(2026, 3, 8),
    source_record_id: int = 101,
    source_updated_at: datetime = datetime(2026, 3, 8, 8, tzinfo=UTC),
) -> TimeseriesFxRate:
    is_identity = rate == Decimal("1")
    return TimeseriesFxRate(
        rate=rate,
        from_currency="USD" if is_identity else "EUR",
        to_currency="USD",
        rate_date=rate_date,
        source_record_id=None if is_identity else source_record_id,
        source_updated_at=None if is_identity else source_updated_at,
    )


def test_calculator_sums_position_economics_in_portfolio_currency() -> None:
    result = calculate_portfolio_timeseries(
        portfolio=_scope(),
        aggregation_date=date(2026, 3, 8),
        epoch=2,
        contributions=[
            PortfolioPositionContribution(
                position_timeseries=_position("SEC-USD"),
                fx_rate=_fx_rate(Decimal("1")),
            ),
            PortfolioPositionContribution(
                position_timeseries=_position("SEC-EUR"),
                fx_rate=_fx_rate(Decimal("1.2")),
            ),
        ],
    )

    assert result.bod_market_value == Decimal("220.0")
    assert result.bod_cashflow == Decimal("2.2")
    assert result.eod_cashflow == Decimal("4.4")
    assert result.eod_market_value == Decimal("242.0")
    assert result.fees == Decimal("1.10")
    assert result.calculation_lineage is not None
    assert result.calculation_lineage.algorithm_id == "portfolio-timeseries-aggregation"
    assert result.calculation_lineage.numeric_output_policy is not None
    assert result.calculation_lineage.numeric_output_policy.policy_id == (
        "portfolio-timeseries-ledger-output@1.0.0"
    )


def test_calculator_lineage_and_output_are_independent_of_contribution_order() -> None:
    contributions = [
        PortfolioPositionContribution(
            position_timeseries=_position("SEC-USD"),
            fx_rate=_fx_rate(Decimal("1")),
        ),
        PortfolioPositionContribution(
            position_timeseries=_position("SEC-EUR"),
            fx_rate=_fx_rate(Decimal("1.2")),
        ),
    ]

    baseline = calculate_portfolio_timeseries(
        portfolio=_scope(),
        aggregation_date=date(2026, 3, 8),
        epoch=2,
        contributions=contributions,
    )
    reversed_result = calculate_portfolio_timeseries(
        portfolio=_scope(),
        aggregation_date=date(2026, 3, 8),
        epoch=2,
        contributions=list(reversed(contributions)),
    )

    assert reversed_result == baseline


def test_calculator_lineage_changes_with_material_fx_input() -> None:
    position = _position("SEC-EUR")
    baseline = calculate_portfolio_timeseries(
        portfolio=_scope(),
        aggregation_date=date(2026, 3, 8),
        epoch=2,
        contributions=[
            PortfolioPositionContribution(
                position_timeseries=position,
                fx_rate=_fx_rate(Decimal("1.2")),
            )
        ],
    )
    changed = calculate_portfolio_timeseries(
        portfolio=_scope(),
        aggregation_date=date(2026, 3, 8),
        epoch=2,
        contributions=[
            PortfolioPositionContribution(
                position_timeseries=position,
                fx_rate=_fx_rate(Decimal("1.3")),
            )
        ],
    )

    assert baseline.calculation_lineage is not None
    assert changed.calculation_lineage is not None
    assert baseline.calculation_lineage.input_content_hash != (
        changed.calculation_lineage.input_content_hash
    )
    assert baseline.calculation_lineage.output_content_hash != (
        changed.calculation_lineage.output_content_hash
    )


def test_calculator_lineage_binds_equal_rate_to_selected_fx_fact() -> None:
    position = _position("SEC-EUR")
    baseline = calculate_portfolio_timeseries(
        portfolio=_scope(),
        aggregation_date=date(2026, 3, 8),
        epoch=2,
        contributions=[
            PortfolioPositionContribution(
                position_timeseries=position,
                fx_rate=_fx_rate(Decimal("1.2")),
            )
        ],
    )
    changed_fact = calculate_portfolio_timeseries(
        portfolio=_scope(),
        aggregation_date=date(2026, 3, 8),
        epoch=2,
        contributions=[
            PortfolioPositionContribution(
                position_timeseries=position,
                fx_rate=_fx_rate(
                    Decimal("1.2"),
                    rate_date=date(2026, 3, 7),
                    source_record_id=102,
                    source_updated_at=datetime(2026, 3, 8, 8, 0, 1, tzinfo=UTC),
                ),
            )
        ],
    )

    assert changed_fact.bod_market_value == baseline.bod_market_value
    assert changed_fact.bod_cashflow == baseline.bod_cashflow
    assert changed_fact.eod_cashflow == baseline.eod_cashflow
    assert changed_fact.eod_market_value == baseline.eod_market_value
    assert changed_fact.fees == baseline.fees
    assert baseline.calculation_lineage is not None
    assert changed_fact.calculation_lineage is not None
    assert baseline.calculation_lineage.input_content_hash != (
        changed_fact.calculation_lineage.input_content_hash
    )
    assert baseline.calculation_lineage.output_content_hash != (
        changed_fact.calculation_lineage.output_content_hash
    )


def test_calculator_normalizes_fx_amplified_outputs_once_at_portfolio_boundary() -> None:
    result = calculate_portfolio_timeseries(
        portfolio=_scope(),
        aggregation_date=date(2026, 3, 8),
        epoch=2,
        contributions=[
            PortfolioPositionContribution(
                position_timeseries=_position(
                    "SEC-PRECISION",
                    bod_market_value=Decimal("1.0000000001"),
                    bod_cashflow=Decimal("1.0000000001"),
                    eod_cashflow=Decimal("1.0000000001"),
                    eod_market_value=Decimal("1.0000000001"),
                    fees=Decimal("1.0000000001"),
                ),
                fx_rate=_fx_rate(Decimal("1.0000000001")),
            )
        ],
    )

    assert result.bod_market_value == Decimal("1.0000000002")
    assert result.bod_cashflow == Decimal("1.0000000002")
    assert result.eod_cashflow == Decimal("1.0000000002")
    assert result.eod_market_value == Decimal("1.0000000002")
    assert result.fees == Decimal("1.0000000002")


def test_calculator_rejects_portfolio_total_magnitude_overflow() -> None:
    contribution = PortfolioPositionContribution(
        position_timeseries=_position(
            "SEC-OVERFLOW",
            bod_market_value=Decimal("60000000"),
        ),
        fx_rate=_fx_rate(Decimal("2")),
    )

    with pytest.raises(ValueError, match="portfolio-timeseries-ledger-output@1.0.0"):
        calculate_portfolio_timeseries(
            portfolio=_scope(),
            aggregation_date=date(2026, 3, 8),
            epoch=2,
            contributions=[contribution],
        )


def test_calculator_returns_zero_record_for_portfolio_without_positions() -> None:
    result = calculate_portfolio_timeseries(
        portfolio=_scope(),
        aggregation_date=date(2026, 3, 8),
        epoch=2,
        contributions=[],
    )

    assert result.bod_market_value == Decimal("0")
    assert result.bod_cashflow == Decimal("0")
    assert result.eod_cashflow == Decimal("0")
    assert result.eod_market_value == Decimal("0")
    assert result.fees == Decimal("0")


def test_calculator_rejects_cross_portfolio_contribution() -> None:
    contribution = PortfolioPositionContribution(
        position_timeseries=_position("SEC-OTHER", portfolio_id="OTHER-PORT"),
        fx_rate=_fx_rate(Decimal("1")),
    )

    with pytest.raises(PortfolioContributionScopeMismatch):
        calculate_portfolio_timeseries(
            portfolio=_scope(),
            aggregation_date=date(2026, 3, 8),
            epoch=2,
            contributions=[contribution],
        )


def test_calculator_rejects_duplicate_security_contribution() -> None:
    contributions = [
        PortfolioPositionContribution(
            position_timeseries=_position("SEC-DUPLICATE"),
            fx_rate=_fx_rate(Decimal("1")),
        ),
        PortfolioPositionContribution(
            position_timeseries=_position(" SEC-DUPLICATE "),
            fx_rate=_fx_rate(Decimal("1")),
        ),
    ]

    with pytest.raises(DuplicatePortfolioPositionContribution):
        calculate_portfolio_timeseries(
            portfolio=_scope(),
            aggregation_date=date(2026, 3, 8),
            epoch=2,
            contributions=contributions,
        )


def test_calculator_accepts_latest_contribution_within_target_window() -> None:
    result = calculate_portfolio_timeseries(
        portfolio=_scope(),
        aggregation_date=date(2026, 3, 8),
        epoch=2,
        contributions=[
            PortfolioPositionContribution(
                position_timeseries=_position(
                    "SEC-CARRY-FORWARD",
                    business_date=date(2026, 3, 7),
                    epoch=1,
                ),
                fx_rate=_fx_rate(Decimal("1")),
            )
        ],
    )

    assert result.eod_market_value == Decimal("110")


@pytest.mark.parametrize(
    "position",
    [
        _position("SEC-FUTURE-DATE", business_date=date(2026, 3, 9)),
        _position("SEC-FUTURE-EPOCH", epoch=3),
    ],
)
def test_calculator_rejects_future_contribution_outside_target_window(
    position: PositionTimeseriesRecord,
) -> None:
    contribution = PortfolioPositionContribution(
        position_timeseries=position,
        fx_rate=_fx_rate(Decimal("1")),
    )

    with pytest.raises(PortfolioContributionWindowMismatch):
        calculate_portfolio_timeseries(
            portfolio=_scope(),
            aggregation_date=date(2026, 3, 8),
            epoch=2,
            contributions=[contribution],
        )


def test_calculator_rejects_missing_portfolio_identity() -> None:
    with pytest.raises(InvalidPortfolioAggregationScope):
        calculate_portfolio_timeseries(
            portfolio=PortfolioAggregationScope(portfolio_id=" ", base_currency="USD"),
            aggregation_date=date(2026, 3, 8),
            epoch=2,
            contributions=[],
        )


@pytest.mark.parametrize("fx_rate", [Decimal("0"), Decimal("-1")])
def test_contribution_rejects_non_positive_fx_rate(fx_rate: Decimal) -> None:
    with pytest.raises(InvalidPortfolioPositionContribution):
        PortfolioPositionContribution(
            position_timeseries=_position("SEC-INVALID-FX"),
            fx_rate=_fx_rate(fx_rate),
        )
