import asyncio
from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace

from src.services.query_service.app.dtos.reference_integration_dto import (
    PortfolioTaxLotWindowRequest,
)
from src.services.query_service.app.services.portfolio_tax_lot_window import (
    build_portfolio_tax_lot_window_response,
    portfolio_tax_lot_after_sort_key,
    portfolio_tax_lot_next_page_token_payload,
    portfolio_tax_lot_page_token,
    portfolio_tax_lot_window_request_scope,
    resolve_portfolio_tax_lot_window_response,
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


def test_portfolio_tax_lot_window_request_scope_binds_filters_and_cursor() -> None:
    request = PortfolioTaxLotWindowRequest(
        as_of_date=date(2026, 4, 10),
        security_ids=["EQ_US_AAPL", "EQ_US_MSFT"],
        include_closed_lots=True,
        lot_status_filter="OPEN",
        tenant_id="TENANT_SG",
    )

    scope = portfolio_tax_lot_window_request_scope(
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        request=request,
        cursor={
            "last_acquisition_date": "2026-03-25",
            "last_lot_id": "LOT-AAPL-001",
        },
    )

    assert scope.request_fingerprint
    assert scope.after_sort_key == (date(2026, 3, 25), "LOT-AAPL-001")


def test_portfolio_tax_lot_window_request_scope_rejects_token_scope_mismatch() -> None:
    request = PortfolioTaxLotWindowRequest(as_of_date=date(2026, 4, 10))

    try:
        portfolio_tax_lot_window_request_scope(
            portfolio_id="PB_SG_GLOBAL_BAL_001",
            request=request,
            cursor={"scope_fingerprint": "wrong-scope"},
        )
    except ValueError as exc:
        assert "tax-lot page token does not match request scope" in str(exc)
    else:
        raise AssertionError("Expected portfolio tax-lot page token scope mismatch")


def test_portfolio_tax_lot_next_page_token_payload_uses_last_page_lot() -> None:
    request = PortfolioTaxLotWindowRequest(as_of_date=date(2026, 4, 10))
    scope = portfolio_tax_lot_window_request_scope(
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        request=request,
        cursor={},
    )

    assert portfolio_tax_lot_next_page_token_payload(
        request_scope=scope,
        has_more=True,
        page_rows=[(_tax_lot_row(lot_id="LOT-A"), "USD"), (_tax_lot_row(lot_id="LOT-B"), "USD")],
    ) == {
        "scope_fingerprint": scope.request_fingerprint,
        "last_acquisition_date": "2026-03-25",
        "last_lot_id": "LOT-B",
    }
    assert (
        portfolio_tax_lot_next_page_token_payload(
            request_scope=scope,
            has_more=False,
            page_rows=[(_tax_lot_row(), "USD")],
        )
        is None
    )


def test_portfolio_tax_lot_page_token_encodes_payload() -> None:
    request = PortfolioTaxLotWindowRequest(as_of_date=date(2026, 4, 10))
    scope = portfolio_tax_lot_window_request_scope(
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        request=request,
        cursor={},
    )
    encoded_payloads: list[dict[str, str]] = []

    def encode(payload: dict[str, str]) -> str:
        encoded_payloads.append(payload)
        return "encoded-token"

    assert (
        portfolio_tax_lot_page_token(
            request_scope=scope,
            has_more=True,
            page_rows=[
                (_tax_lot_row(lot_id="LOT-A"), "USD"),
                (_tax_lot_row(lot_id="LOT-B"), "USD"),
            ],
            encode_page_token=encode,
        )
        == "encoded-token"
    )
    assert encoded_payloads == [
        {
            "scope_fingerprint": scope.request_fingerprint,
            "last_acquisition_date": "2026-03-25",
            "last_lot_id": "LOT-B",
        }
    ]


def test_portfolio_tax_lot_page_token_suppresses_terminal_page() -> None:
    request = PortfolioTaxLotWindowRequest(as_of_date=date(2026, 4, 10))
    scope = portfolio_tax_lot_window_request_scope(
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        request=request,
        cursor={},
    )

    def encode(_: dict[str, str]) -> str:
        raise AssertionError("Unexpected token encoding for terminal tax-lot page")

    assert (
        portfolio_tax_lot_page_token(
            request_scope=scope,
            has_more=False,
            page_rows=[(_tax_lot_row(), "USD")],
            encode_page_token=encode,
        )
        is None
    )


def test_resolve_portfolio_tax_lot_window_response_orchestrates_repository_reads() -> None:
    async def run_case() -> tuple[
        object, list[tuple[str, dict[str, object]]], list[dict[str, str]]
    ]:
        calls: list[tuple[str, dict[str, object]]] = []
        encoded_payloads: list[dict[str, str]] = []

        class Repository:
            async def portfolio_exists(self, portfolio_id: str) -> bool:
                calls.append(("portfolio_exists", {"portfolio_id": portfolio_id}))
                return True

            async def list_portfolio_tax_lots(
                self, **kwargs: object
            ) -> list[tuple[SimpleNamespace, str]]:
                calls.append(("tax_lots", kwargs))
                return [
                    (_tax_lot_row(lot_id="LOT-A"), "USD"),
                    (_tax_lot_row(lot_id="LOT-B"), "USD"),
                ]

        def encode(payload: dict[str, str]) -> str:
            encoded_payloads.append(payload)
            return "encoded-token"

        response = await resolve_portfolio_tax_lot_window_response(
            repository=Repository(),
            portfolio_id="PB_SG_GLOBAL_BAL_001",
            request=PortfolioTaxLotWindowRequest(
                as_of_date=date(2026, 4, 10),
                security_ids=["EQ_US_AAPL"],
                include_closed_lots=True,
                lot_status_filter="OPEN",
                page={"page_size": 1},
            ),
            decode_page_token=lambda _: {},
            encode_page_token=encode,
        )
        return response, calls, encoded_payloads

    response, calls, encoded_payloads = asyncio.run(run_case())

    assert response.portfolio_id == "PB_SG_GLOBAL_BAL_001"
    assert response.page.next_page_token == "encoded-token"
    assert response.page.returned_component_count == 1
    assert response.lots[0].lot_id == "LOT-A"
    assert [call[0] for call in calls] == ["portfolio_exists", "tax_lots"]
    assert calls[1] == (
        "tax_lots",
        {
            "portfolio_id": "PB_SG_GLOBAL_BAL_001",
            "as_of_date": date(2026, 4, 10),
            "security_ids": ["EQ_US_AAPL"],
            "include_closed_lots": True,
            "lot_status_filter": "OPEN",
            "after_sort_key": None,
            "limit": 2,
        },
    )
    assert encoded_payloads == [
        {
            "scope_fingerprint": response.page.request_scope_fingerprint,
            "last_acquisition_date": "2026-03-25",
            "last_lot_id": "LOT-A",
        }
    ]


def test_resolve_portfolio_tax_lot_window_response_requires_existing_portfolio() -> None:
    async def run_case() -> None:
        class Repository:
            async def portfolio_exists(self, portfolio_id: str) -> bool:
                return False

            async def list_portfolio_tax_lots(self, **_: object) -> list[object]:
                raise AssertionError("Unexpected tax-lot read for missing portfolio")

        await resolve_portfolio_tax_lot_window_response(
            repository=Repository(),
            portfolio_id="PB_UNKNOWN",
            request=PortfolioTaxLotWindowRequest(as_of_date=date(2026, 4, 10)),
            decode_page_token=lambda _: {},
            encode_page_token=lambda _: "token",
        )

    try:
        asyncio.run(run_case())
    except LookupError as exc:
        assert "Portfolio with id PB_UNKNOWN not found" in str(exc)
    else:
        raise AssertionError("Expected missing portfolio lookup failure")


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


def test_build_portfolio_tax_lot_window_response_marks_complete_ready_page() -> None:
    response = build_portfolio_tax_lot_window_response(
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        request=PortfolioTaxLotWindowRequest(
            as_of_date=date(2026, 4, 10),
            security_ids=["EQ_US_AAPL"],
            page={"page_size": 25},
        ),
        request_scope_fingerprint="scope-123",
        page_rows=[(_tax_lot_row(), "USD")],
        has_more=False,
        next_page_token=None,
    )

    assert response.supportability.state == "READY"
    assert response.supportability.reason == "TAX_LOTS_READY"
    assert response.supportability.requested_security_count == 1
    assert response.supportability.returned_lot_count == 1
    assert response.supportability.missing_security_ids == []
    assert response.data_quality_status == "COMPLETE"
    assert response.page.returned_component_count == 1
    assert response.page.next_page_token is None


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
