from datetime import UTC, date, datetime
from decimal import Context, Decimal, localcontext
from unittest.mock import AsyncMock

import pytest
from portfolio_common.domain.tenant import TenantId

from src.services.query_service.app.repositories.cashflow_repository import (
    CashflowFxRateEvidence,
    CashflowSeriesEvidence,
)
from src.services.query_service.app.services.cashflow_evidence_window import (
    read_cashflow_evidence_window,
)

pytestmark = pytest.mark.asyncio


async def test_read_cashflow_evidence_window_reads_booked_and_projected_sequentially() -> None:
    repo = AsyncMock()
    call_order: list[str] = []

    async def booked_evidence(
        *,
        portfolio_id: str,
        start_date: date,
        end_date: date,
        tenant_id: TenantId,
    ) -> CashflowSeriesEvidence:
        call_order.append("booked")
        assert portfolio_id == "P1"
        assert start_date == date(2026, 3, 27)
        assert end_date == date(2026, 4, 5)
        return CashflowSeriesEvidence(
            rows=[(start_date, "USD", Decimal("10"))],
            latest_evidence_timestamp=datetime(2026, 3, 27, 9, tzinfo=UTC),
        )

    async def projected_evidence(
        *,
        portfolio_id: str,
        start_date: date,
        end_date: date,
        tenant_id: TenantId,
    ) -> CashflowSeriesEvidence:
        call_order.append("projected")
        assert portfolio_id == "P1"
        assert start_date == date(2026, 3, 27)
        assert end_date == date(2026, 4, 5)
        return CashflowSeriesEvidence(
            rows=[(end_date, "USD", Decimal("-5"))],
            latest_evidence_timestamp=datetime(2026, 3, 27, 10, tzinfo=UTC),
        )

    repo.get_portfolio_cashflow_series_with_evidence.side_effect = booked_evidence
    repo.get_projected_settlement_cashflow_series_with_evidence.side_effect = projected_evidence

    window = await read_cashflow_evidence_window(
        repo=repo,
        portfolio_id="P1",
        portfolio_currency="USD",
        start_date=date(2026, 3, 27),
        end_date=date(2026, 4, 5),
        include_projected=True,
        tenant_id=TenantId("tenant-test"),
    )

    assert window.booked_rows == [(date(2026, 3, 27), Decimal("10"))]
    assert window.projected_rows == [(date(2026, 4, 5), Decimal("-5"))]
    assert window.latest_evidence_timestamp == datetime(2026, 3, 27, 10, tzinfo=UTC)
    assert call_order == ["booked", "projected"]


async def test_read_cashflow_evidence_window_skips_projected_read_for_booked_only() -> None:
    repo = AsyncMock()
    repo.get_portfolio_cashflow_series_with_evidence.return_value = CashflowSeriesEvidence(
        rows=[(date(2026, 3, 27), "USD", Decimal("10"))],
        latest_evidence_timestamp=datetime(2026, 3, 27, 9, tzinfo=UTC),
    )

    window = await read_cashflow_evidence_window(
        repo=repo,
        portfolio_id="P1",
        portfolio_currency="USD",
        start_date=date(2026, 3, 27),
        end_date=date(2026, 3, 27),
        include_projected=False,
        tenant_id=TenantId("tenant-test"),
    )

    repo.get_projected_settlement_cashflow_series_with_evidence.assert_not_awaited()
    assert window.booked_rows == [(date(2026, 3, 27), Decimal("10"))]
    assert window.projected_rows == []
    assert window.latest_evidence_timestamp == datetime(2026, 3, 27, 9, tzinfo=UTC)


async def test_read_cashflow_evidence_window_converts_each_native_currency_before_aggregation() -> (
    None
):
    repo = AsyncMock()
    repo.get_portfolio_cashflow_series_with_evidence.return_value = CashflowSeriesEvidence(
        rows=[
            (date(2026, 3, 27), "USD", Decimal("100")),
            (date(2026, 3, 27), "EUR", Decimal("100")),
        ],
        latest_evidence_timestamp=datetime(2026, 3, 27, 9, tzinfo=UTC),
    )
    repo.get_projected_settlement_cashflow_series_with_evidence.return_value = (
        CashflowSeriesEvidence(
            rows=[(date(2026, 3, 28), "EUR", Decimal("-25"))],
            latest_evidence_timestamp=datetime(2026, 3, 27, 10, tzinfo=UTC),
        )
    )
    repo.get_cashflow_fx_rate_evidence.return_value = {
        ("EUR", "USD", date(2026, 3, 27)): CashflowFxRateEvidence(
            rate=Decimal("2"),
            rate_date=date(2026, 3, 27),
            source_id=11,
            from_currency="EUR",
            to_currency="USD",
            source_updated_at=datetime(2026, 3, 27, 8, tzinfo=UTC),
        ),
        ("EUR", "USD", date(2026, 3, 28)): CashflowFxRateEvidence(
            rate=Decimal("4"),
            rate_date=date(2026, 3, 28),
            source_id=12,
            from_currency="EUR",
            to_currency="USD",
            source_updated_at=datetime(2026, 3, 28, 8, tzinfo=UTC),
        ),
    }

    window = await read_cashflow_evidence_window(
        repo=repo,
        portfolio_id="P1",
        portfolio_currency="USD",
        start_date=date(2026, 3, 27),
        end_date=date(2026, 3, 28),
        include_projected=True,
        tenant_id=TenantId("tenant-test"),
    )

    assert window.booked_rows == [(date(2026, 3, 27), Decimal("300"))]
    assert window.projected_rows == [(date(2026, 3, 28), Decimal("-100"))]
    assert window.booked_source_total == Decimal("300")
    assert window.projected_source_total == Decimal("-100")
    assert len(window.fx_conversion_evidence) == 2


@pytest.mark.parametrize("available_rate", [None, Decimal("0"), Decimal("-1")])
async def test_read_cashflow_evidence_window_refuses_missing_or_invalid_direct_fx(
    available_rate: Decimal | None,
) -> None:
    repo = AsyncMock()
    repo.get_portfolio_cashflow_series_with_evidence.return_value = CashflowSeriesEvidence(
        rows=[(date(2026, 3, 27), "EUR", Decimal("100"))],
        latest_evidence_timestamp=datetime(2026, 3, 27, 9, tzinfo=UTC),
    )
    repo.get_projected_settlement_cashflow_series_with_evidence.return_value = (
        CashflowSeriesEvidence(rows=[], latest_evidence_timestamp=None)
    )
    repo.get_cashflow_fx_rate_evidence.return_value = (
        {}
        if available_rate is None
        else {
            ("EUR", "USD", date(2026, 3, 27)): CashflowFxRateEvidence(
                source_id=11,
                from_currency="EUR",
                to_currency="USD",
                rate_date=date(2026, 3, 27),
                rate=available_rate,
                source_updated_at=datetime(2026, 3, 27, 8, tzinfo=UTC),
            )
        }
    )

    with pytest.raises(ValueError, match="FX|rate"):
        await read_cashflow_evidence_window(
            repo=repo,
            portfolio_id="P1",
            portfolio_currency="USD",
            start_date=date(2026, 3, 27),
            end_date=date(2026, 3, 27),
            include_projected=False,
            tenant_id=TenantId("tenant-test"),
        )


async def test_read_cashflow_evidence_window_does_not_infer_inverse_pair() -> None:
    repo = AsyncMock()
    repo.get_portfolio_cashflow_series_with_evidence.return_value = CashflowSeriesEvidence(
        rows=[(date(2026, 3, 27), "EUR", Decimal("100"))],
        latest_evidence_timestamp=None,
    )
    repo.get_cashflow_fx_rate_evidence.return_value = {
        ("USD", "EUR", date(2026, 3, 27)): CashflowFxRateEvidence(
            source_id=12,
            from_currency="USD",
            to_currency="EUR",
            rate_date=date(2026, 3, 27),
            rate=Decimal("0.5"),
            source_updated_at=datetime(2026, 3, 27, 8, tzinfo=UTC),
        )
    }

    with pytest.raises(ValueError, match="exact-date direct FX"):
        await read_cashflow_evidence_window(
            repo=repo,
            portfolio_id="P1",
            portfolio_currency="USD",
            start_date=date(2026, 3, 27),
            end_date=date(2026, 3, 27),
            include_projected=False,
            tenant_id=TenantId("tenant-test"),
        )


async def test_read_cashflow_evidence_window_preserves_same_currency_zero_without_fx() -> None:
    repo = AsyncMock()
    repo.get_portfolio_cashflow_series_with_evidence.return_value = CashflowSeriesEvidence(
        rows=[(date(2026, 3, 27), "USD", Decimal("0"))],
        latest_evidence_timestamp=datetime(2026, 3, 27, 9, tzinfo=UTC),
        source_row_count=1,
    )

    window = await read_cashflow_evidence_window(
        repo=repo,
        portfolio_id="P1",
        portfolio_currency="USD",
        start_date=date(2026, 3, 27),
        end_date=date(2026, 3, 27),
        include_projected=False,
        tenant_id=TenantId("tenant-test"),
    )

    assert window.booked_rows == [(date(2026, 3, 27), Decimal("0"))]
    assert window.booked_source_total == Decimal("0")
    repo.get_cashflow_fx_rate_evidence.assert_not_awaited()


@pytest.mark.parametrize("ambient_precision", [6, 28, 50])
async def test_read_cashflow_evidence_window_owns_conversion_and_aggregation_precision(
    ambient_precision: int,
) -> None:
    flow_date = date(2026, 3, 27)
    projected_date = date(2026, 3, 28)
    repo = AsyncMock()
    repo.get_portfolio_cashflow_series_with_evidence.return_value = CashflowSeriesEvidence(
        rows=[
            (flow_date, "EUR", Decimal("12345678.1234567890")),
            (flow_date, "USD", Decimal("12345.6789")),
        ],
        latest_evidence_timestamp=datetime(2026, 3, 27, 9, tzinfo=UTC),
        source_row_count=2,
    )
    repo.get_projected_settlement_cashflow_series_with_evidence.return_value = (
        CashflowSeriesEvidence(
            rows=[(projected_date, "EUR", Decimal("12345.6789"))],
            latest_evidence_timestamp=datetime(2026, 3, 27, 10, tzinfo=UTC),
            source_row_count=1,
        )
    )
    repo.get_cashflow_fx_rate_evidence.return_value = {
        ("EUR", "USD", flow_date): CashflowFxRateEvidence(
            source_id=11,
            from_currency="EUR",
            to_currency="USD",
            rate_date=flow_date,
            rate=Decimal("12345678.1234567890"),
            source_updated_at=datetime(2026, 3, 27, 8, tzinfo=UTC),
        ),
        ("EUR", "USD", projected_date): CashflowFxRateEvidence(
            source_id=12,
            from_currency="EUR",
            to_currency="USD",
            rate_date=projected_date,
            rate=Decimal("1.23456789"),
            source_updated_at=datetime(2026, 3, 28, 8, tzinfo=UTC),
        ),
    }

    with localcontext(Context(prec=ambient_precision)):
        window = await read_cashflow_evidence_window(
            repo=repo,
            portfolio_id="P1",
            portfolio_currency="USD",
            start_date=flow_date,
            end_date=projected_date,
            include_projected=True,
            tenant_id=TenantId("tenant-test"),
        )

    assert window.booked_rows == [(flow_date, Decimal("152415768340345.22195746275019052100"))]
    assert window.projected_rows == [(projected_date, Decimal("15241.578750190521"))]
    assert window.booked_source_total == Decimal("152415768340345.22195746275019052100")
    assert window.projected_source_total == Decimal("15241.578750190521")
