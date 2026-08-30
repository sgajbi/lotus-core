from datetime import date

import pytest
from portfolio_common.domain.tenant import TenantAuthorityMismatchError, TenantContext, TenantId
from portfolio_common.events import PortfolioEvent
from pydantic import BaseModel, ValidationError

from src.services.ingestion_service.app.application.portfolio_tenant_authority import (
    bind_portfolio_tenant_authority,
)
from src.services.ingestion_service.app.DTOs.portfolio_dto import Portfolio
from tests.test_support.tenant import TEST_TENANT_ID


def _portfolio_values(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "portfolio_id": "PORTFOLIO-001",
        "tenant_id": TEST_TENANT_ID,
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
def test_portfolio_contract_requires_source_owned_tenant(
    model: type[BaseModel],
) -> None:
    values = _portfolio_values()
    values.pop("tenant_id")

    with pytest.raises(ValidationError, match="tenant_id"):
        model.model_validate(values)


@pytest.mark.parametrize("model", [Portfolio, PortfolioEvent])
@pytest.mark.parametrize(
    ("tenant_id", "legal_book_id"),
    [(None, "PB-SG-01")],
)
def test_portfolio_contract_rejects_legal_book_without_tenant(
    model: type[BaseModel],
    tenant_id: str | None,
    legal_book_id: str | None,
) -> None:
    with pytest.raises(ValidationError, match="tenant_id"):
        model.model_validate(_portfolio_values(tenant_id=tenant_id, legal_book_id=legal_book_id))


@pytest.mark.parametrize("model", [Portfolio, PortfolioEvent])
def test_portfolio_contract_allows_tenant_without_legal_book(
    model: type[BaseModel],
) -> None:
    portfolio = model.model_validate(_portfolio_values(legal_book_id=None))

    assert portfolio.tenant_id == TEST_TENANT_ID
    assert portfolio.legal_book_id is None


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


def test_portfolio_binding_rejects_cross_tenant_payload_without_mutation() -> None:
    matching_portfolio = Portfolio.model_validate(_portfolio_values(tenant_id="tenant-a"))
    conflicting_portfolio = Portfolio.model_validate(_portfolio_values(tenant_id="tenant-b"))
    context = TenantContext(tenant_id=TenantId("tenant-a"), identity_verified=True)

    with pytest.raises(TenantAuthorityMismatchError, match="does not match"):
        bind_portfolio_tenant_authority(
            [matching_portfolio, conflicting_portfolio],
            context,
        )

    assert matching_portfolio.tenant_id == "tenant-a"
    assert conflicting_portfolio.tenant_id == "tenant-b"


def test_portfolio_binding_stamps_canonical_admitted_authority() -> None:
    portfolio = Portfolio.model_validate(_portfolio_values(tenant_id="tenant-a"))
    context = TenantContext(tenant_id=TenantId(" tenant-a "), identity_verified=True)

    bind_portfolio_tenant_authority([portfolio], context)

    assert portfolio.tenant_id == "tenant-a"
