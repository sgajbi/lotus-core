# services/calculators/position-valuation-calculator/app/logic/valuation_logic.py
import logging
from decimal import Decimal
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


class ValuationLogic:
    """
    A stateless calculator for determining the market value and unrealized
    gain/loss of a position, with full dual-currency support.
    """

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
        # Defensive type conversion to prevent errors from non-Decimal inputs
        quantity = Decimal(str(quantity))

        if quantity.is_zero():
            return Decimal(0), Decimal(0), Decimal(0), Decimal(0)

        # 1. Determine the price in the instrument's currency
        valuation_price_local = market_price
        if price_currency != instrument_currency:
            if price_to_instrument_fx_rate is None:
                logger.warning(
                    "Missing FX rate from "
                    f"{price_currency} to {instrument_currency} "
                    "to align price. Cannot value."
                )
                return None
            valuation_price_local = market_price * price_to_instrument_fx_rate

        normalized_product_type = (product_type or "").strip().upper()
        if normalized_product_type == "BOND":
            average_cost_local = (
                abs(cost_basis_local / quantity)
                if not quantity.is_zero() and cost_basis_local is not None
                else Decimal("0")
            )
            absolute_price_local = abs(valuation_price_local)
            if (
                absolute_price_local > Decimal("0")
                and absolute_price_local < Decimal("200")
                and average_cost_local >= Decimal("500")
            ):
                price_ratio = average_cost_local / absolute_price_local
                if price_ratio >= Decimal("50"):
                    valuation_price_local *= Decimal("100")
                elif price_ratio >= Decimal("5"):
                    valuation_price_local *= Decimal("10")

        # 2. Calculate Market Value in local currency
        market_value_local = quantity * valuation_price_local

        # 3. Calculate Unrealized PnL in local currency
        unrealized_pnl_local = market_value_local - cost_basis_local

        # 4. Convert Market Value to portfolio's base currency
        market_value_base = market_value_local
        if instrument_currency != portfolio_currency:
            if instrument_to_portfolio_fx_rate is None:
                logger.warning(
                    "Missing FX rate from "
                    f"{instrument_currency} to {portfolio_currency} "
                    "for reporting. Cannot value."
                )
                return None
            market_value_base = market_value_local * instrument_to_portfolio_fx_rate

        # 5. Calculate Unrealized PnL in portfolio's base currency
        unrealized_pnl_base = market_value_base - cost_basis_base

        return market_value_base, market_value_local, unrealized_pnl_base, unrealized_pnl_local
