from __future__ import annotations

from portfolio_common.events import InstrumentEvent, TransactionEvent

FX_CONTRACT_PRODUCT_TYPE = "FX_CONTRACT"
FX_CONTRACT_ASSET_CLASS = "FX"


def is_fx_contract_component_event(event: TransactionEvent) -> bool:
    component_type = (event.component_type or "").upper()
    return component_type in {"FX_CONTRACT_OPEN", "FX_CONTRACT_CLOSE"}


def build_fx_contract_instrument_event(event: TransactionEvent) -> InstrumentEvent | None:
    if not is_fx_contract_component_event(event):
        return None

    fx_contract_id = (event.fx_contract_id or "").strip()
    if not fx_contract_id:
        return None

    buy_currency = (event.buy_currency or "").upper()
    sell_currency = (event.sell_currency or "").upper()
    maturity_date = event.settlement_date.date() if event.settlement_date else None
    trade_date = event.transaction_date.date()
    pair = "/".join(part for part in [event.pair_base_currency, event.pair_quote_currency] if part)
    name_parts = ["FX CONTRACT"]
    if pair:
        name_parts.append(pair)
    if maturity_date:
        name_parts.append(maturity_date.isoformat())

    return InstrumentEvent(
        security_id=fx_contract_id,
        name=" ".join(name_parts),
        isin=f"SYN-FX-{fx_contract_id}",
        currency=buy_currency or sell_currency or event.currency,
        product_type=FX_CONTRACT_PRODUCT_TYPE,
        asset_class=FX_CONTRACT_ASSET_CLASS,
        maturity_date=maturity_date,
        portfolio_id=event.portfolio_id,
        trade_date=trade_date,
        pair_base_currency=event.pair_base_currency,
        pair_quote_currency=event.pair_quote_currency,
        buy_currency=buy_currency or None,
        sell_currency=sell_currency or None,
        buy_amount=event.buy_amount,
        sell_amount=event.sell_amount,
        contract_rate=event.contract_rate,
    )
