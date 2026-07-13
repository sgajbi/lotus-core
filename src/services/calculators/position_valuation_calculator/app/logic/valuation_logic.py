# services/calculators/position-valuation-calculator/app/logic/valuation_logic.py
import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional, Tuple

from portfolio_common.domain.decimal_amount import required_decimal
from portfolio_common.domain.market_data.fx_rate import coerce_positive_fx_rate_or_none
from portfolio_common.domain.market_data.market_price import (
    coerce_positive_market_price_or_none,
)
from portfolio_common.domain.market_data.valuation_unit_price import (
    resolve_valuation_unit_price,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ValuationComponents:
    market_value_base: Decimal
    market_value_local: Decimal
    unrealized_total_base: Decimal
    unrealized_total_local: Decimal
    unrealized_price_base: Decimal
    unrealized_price_local: Decimal
    unrealized_fx_base: Decimal

    def as_legacy_tuple(self) -> Tuple[Decimal, Decimal, Decimal, Decimal]:
        return (
            self.market_value_base,
            self.market_value_local,
            self.unrealized_total_base,
            self.unrealized_total_local,
        )


class ValuationLogic:
    """
    A stateless calculator for determining the market value and unrealized
    gain/loss of a position, with full dual-currency support.
    """

    @staticmethod
    def _normalize_currency_code(currency_code: str) -> str:
        return currency_code.strip().upper()

    @classmethod
    def _positive_fx_rate_or_none(
        cls,
        fx_rate: Decimal | None,
        *,
        from_currency: str,
        to_currency: str,
    ) -> Decimal | None:
        if fx_rate is None:
            logger.warning(
                "Missing FX rate from %s to %s. Cannot value.",
                from_currency,
                to_currency,
            )
            return None
        normalized_fx_rate = coerce_positive_fx_rate_or_none(fx_rate)
        if normalized_fx_rate is None:
            logger.warning(
                "Non-positive FX rate from %s to %s. Cannot value.",
                from_currency,
                to_currency,
            )
            return None
        return normalized_fx_rate

    @staticmethod
    def calculate_valuation(
        quantity: Decimal,
        market_price: Decimal,
        cost_basis_base: Decimal,
        cost_basis_local: Decimal,
        price_currency: str,
        instrument_currency: str,
        portfolio_currency: str,
        product_type: str | None = None,
        price_to_instrument_fx_rate: Optional[Decimal] = None,
        instrument_to_portfolio_fx_rate: Optional[Decimal] = None,
    ) -> Optional[Tuple[Decimal, Decimal, Decimal, Decimal]]:
        """
        Calculates market value and unrealized PnL in both local and base currencies.
        Returns:
            A tuple of (market_value_base, market_value_local, pnl_base, pnl_local),
            or None if a required FX rate is missing.
        """
        components = ValuationLogic.calculate_valuation_components(
            quantity=quantity,
            market_price=market_price,
            cost_basis_base=cost_basis_base,
            cost_basis_local=cost_basis_local,
            price_currency=price_currency,
            instrument_currency=instrument_currency,
            portfolio_currency=portfolio_currency,
            product_type=product_type,
            price_to_instrument_fx_rate=price_to_instrument_fx_rate,
            instrument_to_portfolio_fx_rate=instrument_to_portfolio_fx_rate,
        )
        return components.as_legacy_tuple() if components is not None else None

    @staticmethod
    def calculate_valuation_components(
        quantity: Decimal,
        market_price: Decimal,
        cost_basis_base: Decimal,
        cost_basis_local: Decimal,
        price_currency: str,
        instrument_currency: str,
        portfolio_currency: str,
        product_type: str | None = None,
        price_to_instrument_fx_rate: Optional[Decimal] = None,
        instrument_to_portfolio_fx_rate: Optional[Decimal] = None,
    ) -> ValuationComponents | None:
        quantity = required_decimal(quantity, field_name="quantity")
        normalized_market_price = coerce_positive_market_price_or_none(market_price)
        if normalized_market_price is None:
            logger.warning(
                "Non-positive market price for %s/%s. Cannot value.",
                price_currency,
                instrument_currency,
            )
            return None
        cost_basis_base = required_decimal(cost_basis_base, field_name="cost_basis_base")
        cost_basis_local = required_decimal(cost_basis_local, field_name="cost_basis_local")
        price_currency = ValuationLogic._normalize_currency_code(price_currency)
        instrument_currency = ValuationLogic._normalize_currency_code(instrument_currency)
        portfolio_currency = ValuationLogic._normalize_currency_code(portfolio_currency)

        if quantity.is_zero():
            return ValuationComponents(
                market_value_base=Decimal(0),
                market_value_local=Decimal(0),
                unrealized_total_base=Decimal(0),
                unrealized_total_local=Decimal(0),
                unrealized_price_base=Decimal(0),
                unrealized_price_local=Decimal(0),
                unrealized_fx_base=Decimal(0),
            )

        # 1. Determine the price in the instrument's currency
        valuation_price_local = normalized_market_price
        if price_currency != instrument_currency:
            normalized_price_fx_rate = ValuationLogic._positive_fx_rate_or_none(
                price_to_instrument_fx_rate,
                from_currency=price_currency,
                to_currency=instrument_currency,
            )
            if normalized_price_fx_rate is None:
                return None
            valuation_price_local = normalized_market_price * normalized_price_fx_rate

        valuation_price_local = resolve_valuation_unit_price(
            market_price=valuation_price_local,
            quantity=quantity,
            cost_basis_local=cost_basis_local,
            product_type=product_type,
        )

        # 2. Calculate Market Value in local currency
        market_value_local = quantity * valuation_price_local

        # 3. Calculate Unrealized PnL in local currency
        unrealized_pnl_local = market_value_local - cost_basis_local

        # 4. Convert Market Value to portfolio's base currency
        current_instrument_to_portfolio_rate = Decimal(1)
        market_value_base = market_value_local
        if instrument_currency != portfolio_currency:
            normalized_portfolio_fx_rate = ValuationLogic._positive_fx_rate_or_none(
                instrument_to_portfolio_fx_rate,
                from_currency=instrument_currency,
                to_currency=portfolio_currency,
            )
            if normalized_portfolio_fx_rate is None:
                return None
            current_instrument_to_portfolio_rate = normalized_portfolio_fx_rate
            market_value_base = market_value_local * normalized_portfolio_fx_rate

        # 5. Calculate Unrealized PnL in portfolio's base currency
        unrealized_pnl_base = market_value_base - cost_basis_base
        unrealized_price_pnl_base = unrealized_pnl_local * current_instrument_to_portfolio_rate
        unrealized_fx_pnl_base = (
            cost_basis_local * current_instrument_to_portfolio_rate - cost_basis_base
        )

        return ValuationComponents(
            market_value_base=market_value_base,
            market_value_local=market_value_local,
            unrealized_total_base=unrealized_pnl_base,
            unrealized_total_local=unrealized_pnl_local,
            unrealized_price_base=unrealized_price_pnl_base,
            unrealized_price_local=unrealized_pnl_local,
            unrealized_fx_base=unrealized_fx_pnl_base,
        )
