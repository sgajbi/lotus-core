# services/calculators/position-valuation-calculator/app/logic/valuation_logic.py
import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional, Tuple

from portfolio_common.domain.calculation_lineage import (
    CalculationLineage,
    build_calculation_lineage,
)
from portfolio_common.domain.decimal_amount import required_decimal
from portfolio_common.domain.market_data.fx_rate import coerce_positive_fx_rate_or_none
from portfolio_common.domain.market_data.market_price import (
    coerce_positive_market_price_or_none,
)
from portfolio_common.domain.valuation import (
    BOND_QUOTE_AUTHORITY_REQUIRED_REASON,
    UnsupportedValuationError,
    requires_bond_quote_authority,
)
from portfolio_common.domain.valuation.numeric_policy import (
    POSITION_VALUATION_LEDGER_OUTPUT_V1,
)

logger = logging.getLogger(__name__)

LEGACY_VALUATION_ALGORITHM_ID = "legacy-unscoped-position-valuation"
LEGACY_VALUATION_ALGORITHM_VERSION = 1


@dataclass(frozen=True, slots=True)
class ValuationComponents:
    market_value_base: Decimal
    market_value_local: Decimal
    unrealized_total_base: Decimal
    unrealized_total_local: Decimal
    unrealized_price_base: Decimal
    unrealized_price_local: Decimal
    unrealized_fx_base: Decimal
    calculation_lineage: CalculationLineage

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

        price_alignment_fx_rate: Decimal | None = None
        portfolio_fx_rate = Decimal(1)
        if requires_bond_quote_authority(
            product_type=product_type,
            quantity=quantity,
            cost_basis_reporting=cost_basis_base,
            cost_basis_local=cost_basis_local,
        ):
            raise UnsupportedValuationError(BOND_QUOTE_AUTHORITY_REQUIRED_REASON)

        if quantity.is_zero():
            components = ValuationComponents(
                market_value_base=Decimal(0),
                market_value_local=Decimal(0),
                unrealized_total_base=Decimal(0),
                unrealized_total_local=Decimal(0),
                unrealized_price_base=Decimal(0),
                unrealized_price_local=Decimal(0),
                unrealized_fx_base=Decimal(0),
                calculation_lineage=build_calculation_lineage(
                    algorithm_id=LEGACY_VALUATION_ALGORITHM_ID,
                    algorithm_version=LEGACY_VALUATION_ALGORITHM_VERSION,
                    intermediate_precision=POSITION_VALUATION_LEDGER_OUTPUT_V1.working_precision,
                    input_payload={
                        "cost_basis_base": cost_basis_base,
                        "cost_basis_local": cost_basis_local,
                        "instrument_currency": instrument_currency,
                        "market_price": normalized_market_price,
                        "portfolio_currency": portfolio_currency,
                        "price_currency": price_currency,
                        "product_type": product_type,
                        "quantity": quantity,
                        "zero_position_short_circuit": True,
                    },
                    output_payload=_valuation_output_payload(
                        market_value_base=Decimal(0),
                        market_value_local=Decimal(0),
                        unrealized_total_base=Decimal(0),
                        unrealized_total_local=Decimal(0),
                        unrealized_price_base=Decimal(0),
                        unrealized_price_local=Decimal(0),
                        unrealized_fx_base=Decimal(0),
                    ),
                    numeric_output_policy=POSITION_VALUATION_LEDGER_OUTPUT_V1.lineage_identity(),
                ),
            )
            return components

        with POSITION_VALUATION_LEDGER_OUTPUT_V1.arithmetic_context():
            # 1. Determine the price in the instrument's currency.
            valuation_price_local = normalized_market_price
            if price_currency != instrument_currency:
                normalized_price_fx_rate = ValuationLogic._positive_fx_rate_or_none(
                    price_to_instrument_fx_rate,
                    from_currency=price_currency,
                    to_currency=instrument_currency,
                )
                if normalized_price_fx_rate is None:
                    return None
                price_alignment_fx_rate = normalized_price_fx_rate
                valuation_price_local = normalized_market_price * normalized_price_fx_rate

            # 2. Calculate raw local/base values at governed working precision.
            raw_market_value_local = quantity * valuation_price_local
            current_instrument_to_portfolio_rate = Decimal(1)
            raw_market_value_base = raw_market_value_local
            if instrument_currency != portfolio_currency:
                normalized_portfolio_fx_rate = ValuationLogic._positive_fx_rate_or_none(
                    instrument_to_portfolio_fx_rate,
                    from_currency=instrument_currency,
                    to_currency=portfolio_currency,
                )
                if normalized_portfolio_fx_rate is None:
                    return None
                portfolio_fx_rate = normalized_portfolio_fx_rate
                current_instrument_to_portfolio_rate = normalized_portfolio_fx_rate
                raw_market_value_base = raw_market_value_local * normalized_portfolio_fx_rate

            raw_unrealized_fx_base = (
                cost_basis_local * current_instrument_to_portfolio_rate - cost_basis_base
            )

        policy = POSITION_VALUATION_LEDGER_OUTPUT_V1
        market_value_local = policy.normalize(
            raw_market_value_local,
            field_name="market_value_local",
        )
        market_value_base = policy.normalize(
            raw_market_value_base,
            field_name="market_value",
        )
        unrealized_pnl_local = policy.subtract(
            market_value_local,
            cost_basis_local,
            field_name="unrealized_gain_loss_local",
        )
        unrealized_pnl_base = policy.subtract(
            market_value_base,
            cost_basis_base,
            field_name="unrealized_gain_loss",
        )
        unrealized_fx_pnl_base = policy.normalize(
            raw_unrealized_fx_base,
            field_name="unrealized_fx_gain_loss",
        )
        # Allocate the rounding residual to price P&L so the persisted
        # price-plus-FX decomposition remains exactly equal to total P&L.
        unrealized_price_pnl_base = policy.subtract(
            unrealized_pnl_base,
            unrealized_fx_pnl_base,
            field_name="unrealized_price_gain_loss",
        )
        calculation_lineage = build_calculation_lineage(
            algorithm_id=LEGACY_VALUATION_ALGORITHM_ID,
            algorithm_version=LEGACY_VALUATION_ALGORITHM_VERSION,
            intermediate_precision=policy.working_precision,
            input_payload={
                "cost_basis_base": cost_basis_base,
                "cost_basis_local": cost_basis_local,
                "instrument_currency": instrument_currency,
                "instrument_to_portfolio_fx_rate": portfolio_fx_rate,
                "market_price": normalized_market_price,
                "portfolio_currency": portfolio_currency,
                "price_currency": price_currency,
                "price_to_instrument_fx_rate": price_alignment_fx_rate,
                "product_type": product_type,
                "quantity": quantity,
                "resolved_valuation_unit_price": valuation_price_local,
                "zero_position_short_circuit": False,
            },
            output_payload=_valuation_output_payload(
                market_value_base=market_value_base,
                market_value_local=market_value_local,
                unrealized_total_base=unrealized_pnl_base,
                unrealized_total_local=unrealized_pnl_local,
                unrealized_price_base=unrealized_price_pnl_base,
                unrealized_price_local=unrealized_pnl_local,
                unrealized_fx_base=unrealized_fx_pnl_base,
            ),
            numeric_output_policy=policy.lineage_identity(),
        )
        return ValuationComponents(
            market_value_base=market_value_base,
            market_value_local=market_value_local,
            unrealized_total_base=unrealized_pnl_base,
            unrealized_total_local=unrealized_pnl_local,
            unrealized_price_base=unrealized_price_pnl_base,
            unrealized_price_local=unrealized_pnl_local,
            unrealized_fx_base=unrealized_fx_pnl_base,
            calculation_lineage=calculation_lineage,
        )


def _valuation_output_payload(
    *,
    market_value_base: Decimal,
    market_value_local: Decimal,
    unrealized_total_base: Decimal,
    unrealized_total_local: Decimal,
    unrealized_price_base: Decimal,
    unrealized_price_local: Decimal,
    unrealized_fx_base: Decimal,
) -> dict[str, Decimal]:
    return {
        "market_value_base": market_value_base,
        "market_value_local": market_value_local,
        "unrealized_fx_base": unrealized_fx_base,
        "unrealized_price_base": unrealized_price_base,
        "unrealized_price_local": unrealized_price_local,
        "unrealized_total_base": unrealized_total_base,
        "unrealized_total_local": unrealized_total_local,
    }
