from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace

from src.services.query_service.app.dtos.reference_integration_dto import (
    PortfolioTaxLotWindowRequest,
)
from src.services.query_service.app.services.portfolio_tax_lot_window import (
    build_portfolio_tax_lot_window_response,
    portfolio_tax_lot_after_sort_key,
)


def _tax_lot_row(
    *,
    security_id: str = " EQ_US_AAPL ",
    lot_id: str = "LOT-AAPL-001",
    acquisition_date: date = date(2026, 3, 25),
    updated_at: datetime = datetime(2026, 4, 10, 9, tzinfo=UTC),
) -> SimpleNamespace:
    return SimpleNamespace(
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        security_id=security_id,
        instrument_id=security_id,
        lot_id=lot_id,
        open_quantity=Decimal("100.0000000000"),
        original_quantity=Decimal("100.0000000000"),
        acquisition_date=acquisition_date,
        lot_cost_base=Decimal("15005.5000000000"),
        lot_cost_local=Decimal("15005.5000000000"),
        source_transaction_id="TXN-BUY-AAPL-001",
        source_system="front_office_portfolio_seed",
        calculation_policy_id="BUY_DEFAULT_POLICY",
        calculation_policy_version="1.0.0",
        updated_at=updated_at,
    )


def test_portfolio_tax_lot_after_sort_key_requires_complete_cursor() -> None:
    assert portfolio_tax_lot_after_sort_key({}) is None
    assert portfolio_tax_lot_after_sort_key({"last_lot_id": "LOT-A"}) is None
    assert portfolio_tax_lot_after_sort_key(
        {"last_acquisition_date": "2026-03-25", "last_lot_id": "LOT-A"}
    ) == (date(2026, 3, 25), "LOT-A")


def test_build_portfolio_tax_lot_window_response_marks_partial_page_degraded() -> None:
    response = build_portfolio_tax_lot_window_response(
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        request=PortfolioTaxLotWindowRequest(
            as_of_date=date(2026, 4, 10),
            security_ids=["EQ_US_AAPL"],
            page={"page_size": 1},
        ),
        request_scope_fingerprint="scope-123",
        page_rows=[(_tax_lot_row(), "USD")],
        has_more=True,
        next_page_token="token-2",
    )

    assert response.product_name == "PortfolioTaxLotWindow"
    assert response.lots[0].security_id == "EQ_US_AAPL"
    assert response.page.next_page_token == "token-2"
    assert response.supportability.state == "DEGRADED"
    assert response.supportability.reason == "TAX_LOTS_PAGE_PARTIAL"
    assert response.supportability.missing_security_ids == []
    assert response.data_quality_status == "PARTIAL"
    assert response.latest_evidence_timestamp == datetime(2026, 4, 10, 9, tzinfo=UTC)
    assert response.lineage == {
        "source_system": "position_lot_state",
        "contract_version": "rfc_087_v1",
    }


def test_build_portfolio_tax_lot_window_response_reports_missing_requested_security() -> None:
    response = build_portfolio_tax_lot_window_response(
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        request=PortfolioTaxLotWindowRequest(
            as_of_date=date(2026, 4, 10),
            security_ids=["EQ_US_AAPL", "UNKNOWN_SEC"],
        ),
        request_scope_fingerprint="scope-123",
        page_rows=[(_tax_lot_row(), "USD")],
        has_more=False,
        next_page_token=None,
    )

    assert response.supportability.state == "INCOMPLETE"
    assert response.supportability.reason == "TAX_LOTS_MISSING_FOR_REQUESTED_SECURITIES"
    assert response.supportability.missing_security_ids == ["UNKNOWN_SEC"]
    assert response.data_quality_status == "PARTIAL"


def test_build_portfolio_tax_lot_window_response_marks_empty_portfolio_unavailable() -> None:
    response = build_portfolio_tax_lot_window_response(
        portfolio_id="PB_EMPTY",
        request=PortfolioTaxLotWindowRequest(as_of_date=date(2026, 4, 10)),
        request_scope_fingerprint="scope-123",
        page_rows=[],
        has_more=False,
        next_page_token=None,
    )

    assert response.supportability.state == "UNAVAILABLE"
    assert response.supportability.reason == "TAX_LOTS_EMPTY"
    assert response.supportability.requested_security_count is None
    assert response.data_quality_status == "MISSING"
