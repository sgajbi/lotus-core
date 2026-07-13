"""Build synthetic instrument identity for foreign-exchange contract components."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from portfolio_common.domain.transaction_control_codes import normalize_transaction_control_code

from ..booked import BookedTransaction

FX_CONTRACT_PRODUCT_TYPE = "FX_CONTRACT"
FX_CONTRACT_ASSET_CLASS = "FX"


@dataclass(frozen=True, slots=True)
class FxContractInstrument:
    """Framework-neutral instrument values for one synthetic FX contract."""

    security_id: str
    name: str
    isin: str
    currency: str
    product_type: str
    asset_class: str
    maturity_date: date | None
    portfolio_id: str
    trade_date: date
    pair_base_currency: str | None
    pair_quote_currency: str | None
    buy_currency: str | None
    sell_currency: str | None
    buy_amount: Decimal | None
    sell_amount: Decimal | None
    contract_rate: Decimal | None


def is_fx_contract_component(transaction: BookedTransaction) -> bool:
    component_type = normalize_transaction_control_code(transaction.component_type)
    return component_type in {"FX_CONTRACT_OPEN", "FX_CONTRACT_CLOSE"}


def build_fx_contract_instrument(
    transaction: BookedTransaction,
) -> FxContractInstrument | None:
    """Build synthetic FX contract instrument values for a contract component."""

    if not is_fx_contract_component(transaction):
        return None

    fx_contract_id = _resolve_fx_contract_id(transaction)
    if not fx_contract_id:
        return None

    buy_currency, sell_currency = _resolve_contract_currencies(transaction)
    maturity_date = transaction.settlement_date.date() if transaction.settlement_date else None
    trade_date = transaction.transaction_date.date()
    pair = _resolve_contract_pair_label(transaction)
    name = _build_contract_name(pair, maturity_date.isoformat() if maturity_date else None)
    return _build_contract_instrument(
        transaction=transaction,
        fx_contract_id=fx_contract_id,
        name=name,
        buy_currency=buy_currency,
        sell_currency=sell_currency,
        maturity_date=maturity_date,
        trade_date=trade_date,
    )


def _resolve_fx_contract_id(transaction: BookedTransaction) -> str:
    return (transaction.fx_contract_id or "").strip()


def _resolve_contract_currencies(transaction: BookedTransaction) -> tuple[str, str]:
    return (
        normalize_transaction_control_code(transaction.buy_currency),
        normalize_transaction_control_code(transaction.sell_currency),
    )


def _resolve_contract_pair_label(transaction: BookedTransaction) -> str:
    return "/".join(
        part for part in [transaction.pair_base_currency, transaction.pair_quote_currency] if part
    )


def _build_contract_name(pair: str, maturity_date_label: str | None) -> str:
    name_parts = ["FX CONTRACT"]
    if pair:
        name_parts.append(pair)
    if maturity_date_label:
        name_parts.append(maturity_date_label)
    return " ".join(name_parts)


def _build_contract_instrument(
    *,
    transaction: BookedTransaction,
    fx_contract_id: str,
    name: str,
    buy_currency: str,
    sell_currency: str,
    maturity_date: date | None,
    trade_date: date,
) -> FxContractInstrument:
    return FxContractInstrument(
        security_id=fx_contract_id,
        name=name,
        isin=f"SYN-FX-{fx_contract_id}",
        currency=buy_currency or sell_currency or transaction.currency,
        product_type=FX_CONTRACT_PRODUCT_TYPE,
        asset_class=FX_CONTRACT_ASSET_CLASS,
        maturity_date=maturity_date,
        portfolio_id=transaction.portfolio_id,
        trade_date=trade_date,
        pair_base_currency=transaction.pair_base_currency,
        pair_quote_currency=transaction.pair_quote_currency,
        buy_currency=buy_currency or None,
        sell_currency=sell_currency or None,
        buy_amount=transaction.buy_amount,
        sell_amount=transaction.sell_amount,
        contract_rate=transaction.contract_rate,
    )
