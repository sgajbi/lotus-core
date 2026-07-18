from __future__ import annotations

from datetime import date
from decimal import Decimal, localcontext
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.services.query_control_plane_service.app.application.core_snapshot.projected_valuation import (  # noqa: E501
    CoreSnapshotProjectedPositionResolver,
)
from src.services.query_control_plane_service.app.domain.core_snapshot import CoreSnapshotInstrument

pytestmark = pytest.mark.asyncio


def _instrument(
    security_id: str = "SEC_AAPL_US",
    currency: str = "USD",
    asset_class: str = "EQUITY",
) -> CoreSnapshotInstrument:
    return CoreSnapshotInstrument(
        security_id=security_id,
        name=f"{security_id}-name",
        isin=f"{security_id}-isin",
        currency=currency,
        asset_class=asset_class,
        sector="TECHNOLOGY",
        country_of_risk="US",
        issuer_id=f"ISSUER_{security_id}",
        issuer_name=f"{security_id} issuer",
        ultimate_parent_issuer_id=f"PARENT_{security_id}",
        ultimate_parent_issuer_name=f"{security_id} parent",
        liquidity_tier="L2",
    )


@pytest.fixture
def resolver_dependencies():
    simulation_repo = AsyncMock()
    instrument_repo = AsyncMock()
    price_repo = AsyncMock()
    fx_repo = AsyncMock()
    simulation_repo.get_changes.return_value = []
    instrument_repo.get_by_security_ids.return_value = [_instrument("SEC_NEW_US")]
    price_repo.get_prices.return_value = [SimpleNamespace(price=Decimal("10"), currency="USD")]
    fx_repo.get_fx_rates.return_value = [SimpleNamespace(rate=Decimal("1"))]
    return simulation_repo, instrument_repo, price_repo, fx_repo


def _resolver(dependencies) -> CoreSnapshotProjectedPositionResolver:
    simulation_repo, instrument_repo, price_repo, fx_repo = dependencies
    source_reader = SimpleNamespace(
        get_instruments=instrument_repo.get_by_security_ids,
        get_prices=price_repo.get_prices,
        get_fx_rates=fx_repo.get_fx_rates,
    )
    return CoreSnapshotProjectedPositionResolver(
        simulation_store=simulation_repo,
        source_reader=source_reader,
    )


async def test_projected_position_resolver_handles_non_positive_quantity_branch(
    resolver_dependencies,
):
    simulation_repo, instrument_repo, _price_repo, _fx_repo = resolver_dependencies
    simulation_repo.get_changes.return_value = [
        SimpleNamespace(
            security_id="SEC_NEG",
            transaction_type="SELL",
            quantity=Decimal("1"),
            amount=None,
        )
    ]
    instrument_repo.get_by_security_ids.return_value = [_instrument("SEC_NEG")]

    projected = await _resolver(resolver_dependencies).resolve_projected_positions(
        session_id="SIM_1",
        as_of_date=date(2026, 2, 27),
        portfolio_base_currency="USD",
        portfolio_to_reporting_fx=Decimal("1"),
        baseline_positions={},
        include_zero=True,
        include_cash=True,
    )

    assert projected["SEC_NEG"]["market_value_base"] == Decimal("0")


async def test_projected_position_resolver_normalizes_change_security_ids(
    resolver_dependencies,
):
    simulation_repo, instrument_repo, _price_repo, _fx_repo = resolver_dependencies
    simulation_repo.get_changes.return_value = [
        SimpleNamespace(
            security_id=" SEC_EXISTING ",
            transaction_type="BUY",
            quantity=Decimal("2"),
            amount=None,
        ),
        SimpleNamespace(
            security_id=" SEC_NEW ",
            transaction_type="BUY",
            quantity=Decimal("1"),
            amount=None,
        ),
    ]
    instrument_repo.get_by_security_ids.return_value = [_instrument(" SEC_NEW ")]

    projected = await _resolver(resolver_dependencies).resolve_projected_positions(
        session_id="SIM_1",
        as_of_date=date(2026, 2, 27),
        portfolio_base_currency="USD",
        portfolio_to_reporting_fx=Decimal("1"),
        baseline_positions={
            "SEC_EXISTING": {
                "security_id": "SEC_EXISTING",
                "quantity": Decimal("3"),
                "market_value_base": Decimal("30"),
                "market_value_local": Decimal("30"),
                "currency": "USD",
                "instrument_name": "Existing",
                "asset_class": "EQUITY",
                "sector": None,
                "country_of_risk": None,
                "isin": None,
                "issuer_id": None,
                "issuer_name": None,
                "ultimate_parent_issuer_id": None,
                "ultimate_parent_issuer_name": None,
                "liquidity_tier": None,
            }
        },
        include_zero=True,
        include_cash=True,
    )

    assert projected["SEC_EXISTING"]["quantity"] == Decimal("5")
    assert projected["SEC_NEW"]["security_id"] == "SEC_NEW"
    instrument_repo.get_by_security_ids.assert_awaited_once_with(["SEC_NEW"])


async def test_projected_position_resolver_prices_new_security_with_fx(
    resolver_dependencies,
):
    simulation_repo, instrument_repo, price_repo, fx_repo = resolver_dependencies
    simulation_repo.get_changes.return_value = [
        SimpleNamespace(
            security_id="SEC_NEW_EUR",
            transaction_type="BUY",
            quantity=Decimal("2"),
            amount=None,
        )
    ]
    instrument_repo.get_by_security_ids.return_value = [_instrument("SEC_NEW_EUR", "EUR", "EQUITY")]
    price_repo.get_prices.return_value = [SimpleNamespace(price=Decimal("10"), currency="EUR")]
    fx_repo.get_fx_rates.return_value = [SimpleNamespace(rate=Decimal("1.2"))]

    projected = await _resolver(resolver_dependencies).resolve_projected_positions(
        session_id="SIM_1",
        as_of_date=date(2026, 2, 27),
        portfolio_base_currency="USD",
        portfolio_to_reporting_fx=Decimal("1.5"),
        baseline_positions={},
        include_zero=True,
        include_cash=True,
    )

    assert projected["SEC_NEW_EUR"]["market_value_local"] == Decimal("20")
    assert projected["SEC_NEW_EUR"]["market_value_base"] == Decimal("36")
    fx_repo.get_fx_rates.assert_awaited_once_with(
        from_currency="EUR",
        to_currency="USD",
        start_date=date.min,
        end_date=date(2026, 2, 27),
    )


async def test_projected_market_value_ignores_ambient_decimal_precision(
    resolver_dependencies,
):
    simulation_repo, instrument_repo, price_repo, fx_repo = resolver_dependencies
    simulation_repo.get_changes.return_value = [
        SimpleNamespace(
            security_id="SEC_NEW_EUR",
            transaction_type="BUY",
            quantity=Decimal("3.141592653589793238462643383"),
            amount=None,
        )
    ]
    instrument_repo.get_by_security_ids.return_value = [_instrument("SEC_NEW_EUR", "EUR")]
    price_repo.get_prices.return_value = [
        SimpleNamespace(price=Decimal("1.234567890123456789"), currency="EUR")
    ]
    fx_repo.get_fx_rates.return_value = [SimpleNamespace(rate=Decimal("1.111111111111111111"))]
    resolver = _resolver(resolver_dependencies)

    async def calculate(ambient_precision: int) -> Decimal:
        with localcontext() as context:
            context.prec = ambient_precision
            projected = await resolver.resolve_projected_positions(
                session_id="SIM_1",
                as_of_date=date(2026, 2, 27),
                portfolio_base_currency="USD",
                portfolio_to_reporting_fx=Decimal("0.9876543210987654321"),
                baseline_positions={},
                include_zero=True,
                include_cash=True,
            )
        return projected["SEC_NEW_EUR"]["market_value_base"]

    assert await calculate(6) == await calculate(50)


async def test_projected_position_resolver_reuses_market_fx_per_currency(
    resolver_dependencies,
):
    simulation_repo, instrument_repo, price_repo, fx_repo = resolver_dependencies
    simulation_repo.get_changes.return_value = [
        SimpleNamespace(
            security_id="SEC_NEW_EUR_A",
            transaction_type="BUY",
            quantity=Decimal("2"),
            amount=None,
        ),
        SimpleNamespace(
            security_id="SEC_NEW_EUR_B",
            transaction_type="BUY",
            quantity=Decimal("3"),
            amount=None,
        ),
    ]
    instrument_repo.get_by_security_ids.return_value = [
        _instrument("SEC_NEW_EUR_A", "EUR", "EQUITY"),
        _instrument("SEC_NEW_EUR_B", "EUR", "EQUITY"),
    ]
    price_repo.get_prices.return_value = [SimpleNamespace(price=Decimal("10"), currency=" eur ")]
    fx_repo.get_fx_rates.return_value = [SimpleNamespace(rate=Decimal("1.2"))]

    projected = await _resolver(resolver_dependencies).resolve_projected_positions(
        session_id="SIM_1",
        as_of_date=date(2026, 2, 27),
        portfolio_base_currency="USD",
        portfolio_to_reporting_fx=Decimal("1.5"),
        baseline_positions={},
        include_zero=True,
        include_cash=True,
    )

    assert projected["SEC_NEW_EUR_A"]["market_value_base"] == Decimal("36.0")
    assert projected["SEC_NEW_EUR_B"]["market_value_base"] == Decimal("54.0")
    fx_repo.get_fx_rates.assert_awaited_once_with(
        from_currency="EUR",
        to_currency="USD",
        start_date=date.min,
        end_date=date(2026, 2, 27),
    )


async def test_projected_position_resolver_reads_new_security_prices_sequentially(
    resolver_dependencies,
):
    simulation_repo, instrument_repo, price_repo, fx_repo = resolver_dependencies
    simulation_repo.get_changes.return_value = [
        SimpleNamespace(
            security_id="SEC_NEW_US_A",
            transaction_type="BUY",
            quantity=Decimal("2"),
            amount=None,
        ),
        SimpleNamespace(
            security_id="SEC_NEW_US_B",
            transaction_type="BUY",
            quantity=Decimal("3"),
            amount=None,
        ),
    ]
    instrument_repo.get_by_security_ids.return_value = [
        _instrument("SEC_NEW_US_A", "USD", "EQUITY"),
        _instrument("SEC_NEW_US_B", "USD", "EQUITY"),
    ]
    call_order: list[str] = []

    async def get_prices(*, security_id: str, end_date: date):
        assert end_date == date(2026, 2, 27)
        if security_id == "SEC_NEW_US_A":
            call_order.append("SEC_NEW_US_A")
            return [SimpleNamespace(price=Decimal("10"), currency="USD")]
        if security_id == "SEC_NEW_US_B":
            call_order.append("SEC_NEW_US_B")
            return [SimpleNamespace(price=Decimal("20"), currency="USD")]
        raise AssertionError(f"unexpected security {security_id}")

    price_repo.get_prices.side_effect = get_prices
    fx_repo.get_fx_rates.return_value = [SimpleNamespace(rate=Decimal("1"))]

    projected = await _resolver(resolver_dependencies).resolve_projected_positions(
        session_id="SIM_1",
        as_of_date=date(2026, 2, 27),
        portfolio_base_currency="USD",
        portfolio_to_reporting_fx=Decimal("1"),
        baseline_positions={},
        include_zero=True,
        include_cash=True,
    )

    assert projected["SEC_NEW_US_A"]["market_value_base"] == Decimal("20")
    assert projected["SEC_NEW_US_B"]["market_value_base"] == Decimal("60")
    assert sorted(call_order) == ["SEC_NEW_US_A", "SEC_NEW_US_B"]
    assert price_repo.get_prices.await_count == 2


async def test_projected_position_resolver_filters_cash_and_zero_quantity(
    resolver_dependencies,
):
    simulation_repo, _instrument_repo, _price_repo, _fx_repo = resolver_dependencies
    simulation_repo.get_changes.return_value = []

    projected = await _resolver(resolver_dependencies).resolve_projected_positions(
        session_id="SIM_1",
        as_of_date=date(2026, 2, 27),
        portfolio_base_currency="USD",
        portfolio_to_reporting_fx=Decimal("1"),
        baseline_positions={
            "SEC_CASH": {
                "security_id": "SEC_CASH",
                "quantity": Decimal("1"),
                "baseline_quantity": Decimal("1"),
                "market_value_base": Decimal("1"),
                "market_value_local": Decimal("1"),
                "currency": "USD",
                "instrument_name": "Cash",
                "asset_class": " cash ",
                "sector": None,
                "country_of_risk": None,
                "isin": None,
                "issuer_id": None,
                "issuer_name": None,
                "ultimate_parent_issuer_id": None,
                "ultimate_parent_issuer_name": None,
                "liquidity_tier": None,
            },
            "SEC_ZERO": {
                "security_id": "SEC_ZERO",
                "quantity": Decimal("0"),
                "baseline_quantity": Decimal("0"),
                "market_value_base": Decimal("0"),
                "market_value_local": Decimal("0"),
                "currency": "USD",
                "instrument_name": "Zero",
                "asset_class": "EQUITY",
                "sector": None,
                "country_of_risk": None,
                "isin": None,
                "issuer_id": None,
                "issuer_name": None,
                "ultimate_parent_issuer_id": None,
                "ultimate_parent_issuer_name": None,
                "liquidity_tier": None,
            },
        },
        include_zero=False,
        include_cash=False,
    )

    assert projected == {}
