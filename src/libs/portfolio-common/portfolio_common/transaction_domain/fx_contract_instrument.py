from __future__ import annotations

from datetime import date

from portfolio_common.events import InstrumentEvent, TransactionEvent

from .control_code_normalization import normalize_transaction_control_code

FX_CONTRACT_PRODUCT_TYPE = "FX_CONTRACT"
FX_CONTRACT_ASSET_CLASS = "FX"


def is_fx_contract_component_event(event: TransactionEvent) -> bool:
    component_type = normalize_transaction_control_code(event.component_type)
    return component_type in {"FX_CONTRACT_OPEN", "FX_CONTRACT_CLOSE"}


def build_fx_contract_instrument_event(event: TransactionEvent) -> InstrumentEvent | None:
    if not is_fx_contract_component_event(event):
        return None

    fx_contract_id = _resolve_fx_contract_id(event)
    if not fx_contract_id:
        return None

    buy_currency, sell_currency = _resolve_contract_currencies(event)
    maturity_date = event.settlement_date.date() if event.settlement_date else None
    trade_date = event.transaction_date.date()
    pair = _resolve_contract_pair_label(event)
    name = _build_contract_name(pair, maturity_date.isoformat() if maturity_date else None)
    return _build_contract_instrument_event(
        event=event,
        fx_contract_id=fx_contract_id,
        name=name,
        buy_currency=buy_currency,
        sell_currency=sell_currency,
        maturity_date=maturity_date,
        trade_date=trade_date,
    )


def _resolve_fx_contract_id(event: TransactionEvent) -> str:
    return (event.fx_contract_id or "").strip()


def _resolve_contract_currencies(event: TransactionEvent) -> tuple[str, str]:
    return (
        normalize_transaction_control_code(event.buy_currency),
        normalize_transaction_control_code(event.sell_currency),
    )


def _resolve_contract_pair_label(event: TransactionEvent) -> str:
    return "/".join(part for part in [event.pair_base_currency, event.pair_quote_currency] if part)


def _build_contract_name(pair: str, maturity_date_label: str | None) -> str:
    name_parts = ["FX CONTRACT"]
    if pair:
        name_parts.append(pair)
    if maturity_date_label:
        name_parts.append(maturity_date_label)
    return " ".join(name_parts)


def _build_contract_instrument_event(
    *,
    event: TransactionEvent,
    fx_contract_id: str,
    name: str,
    buy_currency: str,
    sell_currency: str,
    maturity_date: date | None,
    trade_date: date,
) -> InstrumentEvent:
    return InstrumentEvent(
        security_id=fx_contract_id,
        name=name,
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
