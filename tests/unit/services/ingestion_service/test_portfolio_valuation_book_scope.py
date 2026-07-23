from datetime import date

import pytest
from portfolio_common.events import PortfolioEvent
from pydantic import BaseModel, ValidationError

from src.services.ingestion_service.app.DTOs.portfolio_dto import Portfolio


def _portfolio_values(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "portfolio_id": "PORTFOLIO-001",
        "base_currency": "USD",
        "open_date": date(2026, 1, 1),
        "risk_exposure": "balanced",
        "investment_time_horizon": "long_term",
        "portfolio_type": "discretionary",
        "booking_center_code": "SG_BOOKING",
        "client_id": "CLIENT-001",
        "status": "active",
    }
    values.update(overrides)
    return values


@pytest.mark.parametrize("model", [Portfolio, PortfolioEvent])
def test_portfolio_contract_normalizes_complete_valuation_book_scope(
    model: type[BaseModel],
) -> None:
    portfolio = model.model_validate(
        _portfolio_values(tenant_id=" TENANT-SG ", legal_book_id=" PB-SG-01 ")
    )

    assert portfolio.tenant_id == "TENANT-SG"
    assert portfolio.legal_book_id == "PB-SG-01"


@pytest.mark.parametrize("model", [Portfolio, PortfolioEvent])
def test_portfolio_contract_preserves_legacy_unscoped_payload(
    model: type[BaseModel],
) -> None:
    portfolio = model.model_validate(_portfolio_values())

    assert portfolio.tenant_id is None
    assert portfolio.legal_book_id is None


@pytest.mark.parametrize("model", [Portfolio, PortfolioEvent])
@pytest.mark.parametrize(
    ("tenant_id", "legal_book_id"),
    [("TENANT-SG", None), (None, "PB-SG-01")],
)
def test_portfolio_contract_rejects_partial_valuation_book_scope(
    model: type[BaseModel],
    tenant_id: str | None,
    legal_book_id: str | None,
) -> None:
    with pytest.raises(ValidationError, match="must be supplied together"):
        model.model_validate(_portfolio_values(tenant_id=tenant_id, legal_book_id=legal_book_id))


@pytest.mark.parametrize("model", [Portfolio, PortfolioEvent])
@pytest.mark.parametrize(
    ("tenant_id", "legal_book_id"),
    [("", "PB-SG-01"), ("TENANT-SG", " "), (42, "PB-SG-01")],
)
def test_portfolio_contract_rejects_malformed_valuation_book_scope(
    model: type[BaseModel],
    tenant_id: object,
    legal_book_id: object,
) -> None:
    with pytest.raises(ValidationError):
        model.model_validate(_portfolio_values(tenant_id=tenant_id, legal_book_id=legal_book_id))
