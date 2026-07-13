"""Unit contracts for persistence-independent QCP analytics records."""

from dataclasses import FrozenInstanceError
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from src.services.query_control_plane_service.app.domain.analytics import (
    AnalyticsCashflowEvidence,
    AnalyticsExportJobRecord,
    AnalyticsFxRateObservation,
    PositionValuationObservation,
    PriorPositionValuation,
)


def test_analytics_source_records_preserve_domain_fields() -> None:
    position = PositionValuationObservation(
        security_id="SEC_A",
        valuation_date=date(2026, 4, 10),
        bod_market_value=Decimal("100"),
        eod_market_value=Decimal("110"),
        bod_cashflow_position=Decimal("5"),
        eod_cashflow_position=Decimal("0"),
        bod_cashflow_portfolio=Decimal("0"),
        eod_cashflow_portfolio=Decimal("0"),
        fees=Decimal("1"),
        quantity=Decimal("10"),
        epoch=2,
        position_currency="USD",
        asset_class="Equity",
        sector="Technology",
        country="US",
    )
    prior = PriorPositionValuation(
        security_id="SEC_A",
        valuation_date=date(2026, 4, 9),
        eod_market_value=Decimal("100"),
        epoch=1,
    )
    cashflow = AnalyticsCashflowEvidence(
        transaction_id="TXN_1",
        security_id="SEC_A",
        valuation_date=date(2026, 4, 10),
        amount=Decimal("5"),
        currency="USD",
        classification="BUY",
        timing="BOD",
        is_position_flow=True,
        is_portfolio_flow=False,
        epoch=2,
    )
    fx_rate = AnalyticsFxRateObservation(
        rate_date=date(2026, 4, 10),
        rate=Decimal("1.35"),
    )

    assert position.eod_market_value == Decimal("110")
    assert prior.valuation_date == date(2026, 4, 9)
    assert cashflow.is_position_flow is True
    assert fx_rate.rate == Decimal("1.35")


def test_analytics_records_are_immutable() -> None:
    observation = AnalyticsFxRateObservation(
        rate_date=date(2026, 4, 10),
        rate=Decimal("1.35"),
    )

    with pytest.raises(FrozenInstanceError):
        observation.rate = Decimal("1.36")  # type: ignore[misc]


def test_export_job_payloads_remain_json_shaped_without_orm_identity() -> None:
    now = datetime(2026, 4, 10, tzinfo=UTC)
    record = AnalyticsExportJobRecord(
        job_id="aexp_1",
        dataset_type="position_timeseries",
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        status="completed",
        request_fingerprint="sha256:request",
        request_payload={"page_size": 100},
        result_payload={"row_count": 1},
        result_row_count=1,
        result_format="json",
        compression="none",
        error_message=None,
        created_at=now,
        started_at=now,
        completed_at=now,
        updated_at=now,
    )

    assert record.request_payload == {"page_size": 100}
    assert record.result_payload == {"row_count": 1}
