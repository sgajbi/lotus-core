"""Map foreign-exchange domain values to governed integration events."""

from portfolio_common.events import InstrumentEvent

from ..domain.transaction.fx import FxContractInstrument


def to_fx_contract_instrument_event(
    instrument: FxContractInstrument,
) -> InstrumentEvent:
    """Create the integration event for a synthetic FX contract instrument."""

    return InstrumentEvent(
        security_id=instrument.security_id,
        name=instrument.name,
        isin=instrument.isin,
        currency=instrument.currency,
        product_type=instrument.product_type,
        asset_class=instrument.asset_class,
        maturity_date=instrument.maturity_date,
        portfolio_id=instrument.portfolio_id,
        trade_date=instrument.trade_date,
        pair_base_currency=instrument.pair_base_currency,
        pair_quote_currency=instrument.pair_quote_currency,
        buy_currency=instrument.buy_currency,
        sell_currency=instrument.sell_currency,
        buy_amount=instrument.buy_amount,
        sell_amount=instrument.sell_amount,
        contract_rate=instrument.contract_rate,
    )
