from datetime import UTC, date, datetime
from decimal import Decimal

from portfolio_common.reconciliation_quality import COMPLETE, PARTIAL, STALE, UNKNOWN

from src.services.query_service.app.dtos.position_dto import PortfolioPositionsResponse, Position
from src.services.query_service.app.dtos.source_data_product_identity import (
    source_data_product_runtime_metadata,
)
from src.services.query_service.app.services.position_maturity_summary import (
    portfolio_maturity_summary_response,
)


def _position(
    security_id: str,
    *,
    maturity_date: date | None,
    asset_class: str | None = "Bond",
    product_type: str | None = "Bond",
    instrument_name: str = "Issuer Bond",
    quantity: Decimal = Decimal("100"),
) -> Position:
    return Position(
        security_id=security_id,
        quantity=quantity,
        instrument_name=instrument_name,
        position_date=date(2026, 3, 10),
        asset_class=asset_class,
        product_type=product_type,
        maturity_date=maturity_date,
        cost_basis=Decimal("1000"),
        cost_basis_local=Decimal("1000"),
        valuation=None,
        reprocessing_status="CURRENT",
    )


def _holdings_response(
    *,
    positions: list[Position],
    data_quality_status: str = COMPLETE,
) -> PortfolioPositionsResponse:
    return PortfolioPositionsResponse(
        portfolio_id="P1",
        positions=positions,
        **source_data_product_runtime_metadata(
            as_of_date=date(2026, 3, 10),
            generated_at=datetime(2026, 3, 10, 1, 2, tzinfo=UTC),
            data_quality_status=data_quality_status,
            latest_evidence_timestamp=datetime(2026, 3, 10, 1, 1, tzinfo=UTC),
            snapshot_id="holdings-snapshot-1",
            policy_version="policy-v1",
        ),
    )


def test_maturity_summary_counts_maturing_holdings_and_next_date() -> None:
    holdings = _holdings_response(
        positions=[
            _position("BOND-1", maturity_date=date(2026, 4, 1)),
            _position("BOND-2", maturity_date=date(2026, 5, 5)),
            _position("BOND-3", maturity_date=date(2027, 1, 1)),
            _position("EQ-1", maturity_date=None, asset_class="Equity", product_type="Equity"),
        ]
    )

    summary = portfolio_maturity_summary_response(
        portfolio_id="P1",
        holdings=holdings,
        horizon_days=90,
        include_projected=False,
    )

    assert summary.product_name == "PortfolioMaturitySummary"
    assert summary.source_product_name == "HoldingsAsOf"
    assert summary.window_start_date == date(2026, 3, 10)
    assert summary.window_end_date == date(2026, 6, 8)
    assert summary.next_maturity_date == date(2026, 4, 1)
    assert summary.maturing_holding_count == 2
    assert summary.maturity_bearing_holding_count == 3
    assert summary.missing_maturity_date_count == 0
    assert summary.supportability_status == "SUPPORTED"
    assert summary.supportability_reasons == []
    assert summary.data_quality_status == COMPLETE
    assert summary.freshness_status == "CURRENT"
    assert summary.request_fingerprint.startswith("maturity_summary:")
    assert summary.source_batch_fingerprint is None


def test_maturity_summary_degrades_when_bond_maturity_fact_is_missing() -> None:
    holdings = _holdings_response(
        positions=[
            _position("BOND-1", maturity_date=None),
            _position("BOND-2", maturity_date=date(2026, 4, 1)),
        ]
    )

    summary = portfolio_maturity_summary_response(
        portfolio_id="P1",
        holdings=holdings,
        horizon_days=90,
        include_projected=False,
    )

    assert summary.next_maturity_date == date(2026, 4, 1)
    assert summary.maturing_holding_count == 1
    assert summary.missing_maturity_date_count == 1
    assert summary.supportability_status == "PARTIAL"
    assert summary.data_quality_status == PARTIAL
    assert summary.supportability_reasons == ["MISSING_INSTRUMENT_MATURITY_DATE"]


def test_maturity_summary_preserves_stale_holdings_posture() -> None:
    holdings = _holdings_response(
        positions=[_position("BOND-1", maturity_date=date(2026, 4, 1))],
        data_quality_status=STALE,
    )

    summary = portfolio_maturity_summary_response(
        portfolio_id="P1",
        holdings=holdings,
        horizon_days=90,
        include_projected=False,
    )

    assert summary.supportability_status == "STALE"
    assert summary.freshness_status == "STALE"
    assert summary.data_quality_status == STALE
    assert summary.supportability_reasons == ["HOLDINGS_STALE"]


def test_maturity_summary_marks_unknown_holdings_unavailable() -> None:
    holdings = _holdings_response(
        positions=[],
        data_quality_status=UNKNOWN,
    )

    summary = portfolio_maturity_summary_response(
        portfolio_id="P1",
        holdings=holdings,
        horizon_days=90,
        include_projected=True,
    )

    assert summary.include_projected is True
    assert summary.next_maturity_date is None
    assert summary.maturing_holding_count == 0
    assert summary.supportability_status == "UNAVAILABLE"
    assert summary.freshness_status == "UNKNOWN"
    assert summary.supportability_reasons == ["HOLDINGS_UNKNOWN"]


def test_maturity_summary_flags_unsupported_maturity_features() -> None:
    holdings = _holdings_response(
        positions=[
            _position(
                "STRUCTURED-1",
                maturity_date=date(2026, 4, 1),
                product_type="Structured Callable Note",
                instrument_name="Callable Structured Note",
            )
        ]
    )

    summary = portfolio_maturity_summary_response(
        portfolio_id="P1",
        holdings=holdings,
        horizon_days=90,
        include_projected=False,
    )

    assert summary.unsupported_maturity_feature_count == 1
    assert summary.supportability_status == "PARTIAL"
    assert summary.supportability_reasons == ["UNSUPPORTED_PRODUCT_MATURITY_FEATURE"]
