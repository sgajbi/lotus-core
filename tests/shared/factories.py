from decimal import Decimal
from typing import Iterable

from src.services.query_service.app.advisory_simulation.models import (
    CashBalance,
    FxRate,
    MarketDataSnapshot,
    ModelPortfolio,
    ModelTarget,
    PortfolioSnapshot,
    Position,
    Price,
    ShelfEntry,
)


def cash(currency: str, amount: str) -> CashBalance:
    return CashBalance(currency=currency, amount=Decimal(amount))


def position(instrument_id: str, quantity: str) -> Position:
    return Position(instrument_id=instrument_id, quantity=Decimal(quantity))


def price(instrument_id: str, px: str, currency: str) -> Price:
    return Price(instrument_id=instrument_id, price=Decimal(px), currency=currency)


def fx(pair: str, rate: str) -> FxRate:
    return FxRate(pair=pair, rate=Decimal(rate))


def target(instrument_id: str, weight: str) -> ModelTarget:
    return ModelTarget(instrument_id=instrument_id, weight=Decimal(weight))


def shelf_entry(
    instrument_id: str,
    status: str = "APPROVED",
    asset_class: str = "UNKNOWN",
    settlement_days: int = 2,
    issuer_id: str | None = None,
    liquidity_tier: str | None = None,
) -> ShelfEntry:
    return ShelfEntry(
        instrument_id=instrument_id,
        status=status,
        asset_class=asset_class,
        settlement_days=settlement_days,
        issuer_id=issuer_id,
        liquidity_tier=liquidity_tier,
    )


def portfolio_snapshot(
    *,
    portfolio_id: str = "pf_test",
    base_currency: str = "USD",
    positions: Iterable[Position] | None = None,
    cash_balances: Iterable[CashBalance] | None = None,
) -> PortfolioSnapshot:
    return PortfolioSnapshot(
        portfolio_id=portfolio_id,
        base_currency=base_currency,
        positions=list(positions or []),
        cash_balances=list(cash_balances or []),
    )


def market_data_snapshot(
    *, prices: Iterable[Price] | None = None, fx_rates: Iterable[FxRate] | None = None
) -> MarketDataSnapshot:
    return MarketDataSnapshot(prices=list(prices or []), fx_rates=list(fx_rates or []))


def model_portfolio(*, targets: Iterable[ModelTarget]) -> ModelPortfolio:
    return ModelPortfolio(targets=list(targets))
