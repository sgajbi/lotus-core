"""PostgreSQL proof for tenant-scoped selector and exact-date FX evidence."""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from portfolio_common.database_models import (
    FxRate,
    Instrument,
    Portfolio,
    PositionHistory,
    Transaction,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from src.services.query_service.app.repositories.reporting_currency_support_repository import (
    ReportingCurrencySupportRepository,
)

pytestmark = pytest.mark.asyncio


def _portfolio(*, portfolio_id: str, tenant_id: str, base_currency: str) -> Portfolio:
    return Portfolio(
        portfolio_id=portfolio_id,
        tenant_id=tenant_id,
        legal_book_id=f"{tenant_id}-BOOK",
        base_currency=base_currency,
        open_date=date(2026, 1, 1),
        risk_exposure="MODERATE",
        investment_time_horizon="MEDIUM_TERM",
        portfolio_type="DISCRETIONARY",
        objective="CAPITAL_GROWTH",
        booking_center_code="SG",
        client_id=f"{tenant_id}-CLIENT",
        status="ACTIVE",
    )


@pytest.fixture
def reporting_currency_scope_records(clean_db, db_engine) -> None:  # noqa: ARG001
    with Session(db_engine) as session:
        session.add_all(
            [
                _portfolio(
                    portfolio_id="PF-SCOPE-A",
                    tenant_id="TENANT_A",
                    base_currency="USD",
                ),
                _portfolio(
                    portfolio_id="PF-SCOPE-B",
                    tenant_id="TENANT_B",
                    base_currency="CHF",
                ),
                Instrument(
                    security_id="SEC-SCOPE-EUR",
                    name="Tenant B Euro Instrument",
                    isin="XS0000010610",
                    currency="EUR",
                    product_type="Bond",
                ),
                FxRate(
                    from_currency="EUR",
                    to_currency="USD",
                    rate_date=date(2026, 8, 27),
                    rate=Decimal("1.10"),
                ),
                FxRate(
                    from_currency="EUR",
                    to_currency="USD",
                    rate_date=date(2026, 8, 28),
                    rate=Decimal("1.11"),
                ),
            ]
        )
        session.flush()
        session.add(
            Transaction(
                transaction_id="TX-SCOPE-B-EUR",
                portfolio_id="PF-SCOPE-B",
                instrument_id="SEC-SCOPE-EUR",
                security_id="SEC-SCOPE-EUR",
                transaction_type="BUY",
                quantity=Decimal("1"),
                price=Decimal("100"),
                gross_transaction_amount=Decimal("100"),
                trade_currency="EUR",
                currency="EUR",
                transaction_date=datetime(2026, 8, 1, tzinfo=UTC),
            )
        )
        session.flush()
        session.add(
            PositionHistory(
                portfolio_id="PF-SCOPE-B",
                security_id="SEC-SCOPE-EUR",
                transaction_id="TX-SCOPE-B-EUR",
                position_date=date(2026, 8, 1),
                epoch=0,
                quantity=Decimal("1"),
                cost_basis=Decimal("100"),
            )
        )
        session.commit()


async def test_selector_observation_cannot_cross_tenant_boundary(
    reporting_currency_scope_records: None,
    async_db_session: AsyncSession,
) -> None:
    repository = ReportingCurrencySupportRepository(async_db_session)

    assert await repository.is_selector_currency_observed(currency="EUR", tenant_id="TENANT_B")
    assert not await repository.is_selector_currency_observed(currency="EUR", tenant_id="TENANT_A")
    assert await repository.is_selector_currency_observed(currency="CHF", tenant_id="TENANT_B")
    assert not await repository.is_selector_currency_observed(currency="CHF", tenant_id="TENANT_A")


async def test_fx_evidence_requires_the_exact_requested_date(
    reporting_currency_scope_records: None,
    async_db_session: AsyncSession,
) -> None:
    repository = ReportingCurrencySupportRepository(async_db_session)

    assert await repository.get_exact_fx_rate_dates(
        from_currencies=("EUR",),
        to_currency="USD",
        as_of_date=date(2026, 8, 28),
    ) == {"EUR": date(2026, 8, 28)}
    assert (
        await repository.get_exact_fx_rate_dates(
            from_currencies=("EUR",),
            to_currency="USD",
            as_of_date=date(2026, 8, 29),
        )
        == {}
    )
