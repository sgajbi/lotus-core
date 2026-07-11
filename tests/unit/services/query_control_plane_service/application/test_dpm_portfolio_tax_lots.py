"""Application policy tests for DPM portfolio tax-lot evidence."""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from src.services.query_control_plane_service.app.application.dpm_source_readiness import (
    portfolio_tax_lots,
)
from src.services.query_control_plane_service.app.contracts.portfolio_tax_lots import (
    PortfolioTaxLotWindowRequest,
)
from src.services.query_control_plane_service.app.domain.dpm_source_readiness import (
    PortfolioTaxLotEvidence,
)

GENERATED_AT = datetime(2026, 4, 10, 12, tzinfo=UTC)
EVIDENCE_AT = datetime(2026, 4, 10, 10, tzinfo=UTC)


def _lot(
    *,
    security_id: str = "EQ_US_AAPL",
    lot_id: str = "LOT_1",
    open_quantity: str = "100.0000000000",
) -> PortfolioTaxLotEvidence:
    return PortfolioTaxLotEvidence(
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        security_id=security_id,
        instrument_id=security_id,
        lot_id=lot_id,
        open_quantity=Decimal(open_quantity),
        original_quantity=Decimal("100.0000000000"),
        acquisition_date=date(2026, 3, 25),
        lot_cost_base=Decimal("15000.0000000000"),
        lot_cost_local=Decimal("15000.0000000000"),
        source_transaction_id=f"TX_{lot_id}",
        source_system="position_lot_state",
        calculation_policy_id="average_cost",
        calculation_policy_version="v1",
        local_currency="USD",
        updated_at=EVIDENCE_AT,
    )


def _request(*security_ids: str, page_size: int = 25) -> PortfolioTaxLotWindowRequest:
    return PortfolioTaxLotWindowRequest(
        as_of_date=date(2026, 4, 10),
        security_ids=list(security_ids) or None,
        page={"page_size": page_size},
        tenant_id="tenant-1",
    )


def _build(
    *,
    request: PortfolioTaxLotWindowRequest,
    evidence: list[PortfolioTaxLotEvidence],
    has_more: bool = False,
    known_security_ids: set[str] | None = None,
):
    return portfolio_tax_lots.build_portfolio_tax_lot_response(
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        request=request,
        scope=portfolio_tax_lots.PortfolioTaxLotRequestScope(
            fingerprint="scope-1",
            after_sort_key=None,
        ),
        evidence=evidence,
        has_more=has_more,
        next_page_token="next" if has_more else None,
        known_security_ids=known_security_ids or {row.security_id for row in evidence},
        generated_at=GENERATED_AT,
    )


def test_complete_tax_lot_page_is_ready_current_and_hashed() -> None:
    response = _build(request=_request("EQ_US_AAPL"), evidence=[_lot()])

    assert response.supportability.state == "READY"
    assert response.data_quality_status == "COMPLETE"
    assert response.source_evidence_current is True
    assert response.freshness_status == "CURRENT"
    assert response.source_batch_fingerprint == response.content_hash == response.source_digest
    assert response.lots[0].tax_lot_status == "OPEN"
    assert response.lots[0].source_lineage["calculation_policy_id"] == "average_cost"


def test_partial_page_does_not_report_unseen_requested_security_as_missing() -> None:
    response = _build(
        request=_request("EQ_US_AAPL", "EQ_US_MSFT", page_size=1),
        evidence=[_lot()],
        has_more=True,
    )

    assert response.supportability.state == "DEGRADED"
    assert response.supportability.reason == "TAX_LOTS_PAGE_PARTIAL"
    assert response.supportability.missing_security_ids == []
    assert response.page.next_page_token == "next"


def test_terminal_page_reports_missing_requested_security() -> None:
    response = _build(
        request=_request("EQ_US_AAPL", "UNKNOWN"),
        evidence=[_lot()],
    )

    assert response.supportability.state == "INCOMPLETE"
    assert response.supportability.missing_security_ids == ["UNKNOWN"]
    assert response.data_quality_status == "PARTIAL"


def test_orphan_lot_instrument_reference_degrades_source_support() -> None:
    response = _build(
        request=_request("ORPHAN"),
        evidence=[_lot(security_id="ORPHAN")],
        known_security_ids={"OTHER"},
    )

    assert response.supportability.reason == "TAX_LOTS_INSTRUMENT_REFERENCE_MISSING"
    assert response.supportability.missing_instrument_security_ids == ["ORPHAN"]


def test_page_token_is_bound_to_request_scope() -> None:
    request = _request("EQ_US_AAPL")
    scope = portfolio_tax_lots.portfolio_tax_lot_request_scope(
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        request=request,
        cursor={},
    )

    with pytest.raises(ValueError, match="does not match request scope"):
        portfolio_tax_lots.portfolio_tax_lot_request_scope(
            portfolio_id="PB_SG_GLOBAL_BAL_001",
            request=request,
            cursor={"scope_fingerprint": f"wrong-{scope.fingerprint}"},
        )


@pytest.mark.asyncio
async def test_service_fetches_page_size_plus_one_and_encodes_last_returned_lot() -> None:
    class Reader:
        async def portfolio_exists(self, portfolio_id: str) -> bool:
            return True

        async def list_portfolio_tax_lots(self, **kwargs: object):
            self.read = kwargs
            return [_lot(lot_id="LOT_1"), _lot(lot_id="LOT_2")]

        async def list_known_instrument_security_ids(self, security_ids: list[str]) -> set[str]:
            return set(security_ids)

    class Tokens:
        def decode(self, token: str | None) -> dict[str, object]:
            return {}

        def encode(self, payload: dict[str, object]) -> str:
            self.payload = payload
            return "encoded"

    reader = Reader()
    tokens = Tokens()
    response = await portfolio_tax_lots.PortfolioTaxLotService(
        reader=reader,  # type: ignore[arg-type]
        page_tokens=tokens,
        clock=lambda: GENERATED_AT,
    ).resolve(
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        request=_request("EQ_US_AAPL", page_size=1),
    )

    assert reader.read["limit"] == 2
    assert response.page.next_page_token == "encoded"
    assert tokens.payload["last_lot_id"] == "LOT_1"
