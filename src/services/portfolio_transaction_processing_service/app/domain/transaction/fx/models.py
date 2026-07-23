"""Canonical foreign-exchange transaction values and controlled vocabularies."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Mapping, cast

from portfolio_common.domain.currency import normalize_currency_code
from portfolio_common.domain.decimal_amount import decimal_or_none
from portfolio_common.domain.transaction.fee_components import (
    TRANSACTION_FEE_COMPONENT_FIELDS,
    resolve_transaction_trade_fee,
)
from portfolio_common.domain.transaction.type_registry import (
    production_transaction_types_for_lifecycle_families,
)
from portfolio_common.domain.transaction_control_codes import (
    normalize_optional_transaction_control_code,
    normalize_transaction_control_code,
)

from .transaction_source import FxTransactionSource

FX_BUSINESS_TRANSACTION_TYPES = production_transaction_types_for_lifecycle_families("fx")
FX_COMPONENT_TYPES = {
    "FX_CONTRACT_OPEN",
    "FX_CONTRACT_CLOSE",
    "FX_CASH_SETTLEMENT_BUY",
    "FX_CASH_SETTLEMENT_SELL",
}
FX_CASH_LEG_ROLES = {"BUY", "SELL"}
FX_RATE_QUOTE_CONVENTIONS = {"QUOTE_PER_BASE", "BASE_PER_QUOTE"}
FX_SPOT_EXPOSURE_MODELS = {"NONE", "FX_CONTRACT"}
FX_REALIZED_PNL_MODES = {"NONE", "UPSTREAM_PROVIDED", "CASH_LOT_COST_METHOD"}


def _optional_source_value(source: object, field_name: str) -> Any:
    """Read an optional extension value from a structurally compatible source."""

    return getattr(source, field_name, None)


def _fee_component_values(source: object) -> dict[str, object]:
    fees = _optional_source_value(source, "fees")
    if fees is not None:
        return {
            field_name: (
                fees.get(field_name)
                if isinstance(fees, Mapping)
                else getattr(fees, field_name, None)
            )
            for field_name in TRANSACTION_FEE_COMPONENT_FIELDS
        }
    return {
        field_name: _optional_source_value(source, field_name)
        for field_name in TRANSACTION_FEE_COMPONENT_FIELDS
    }


def _resolved_source_trade_fee(source: object) -> Decimal:
    trade_fee = _optional_source_value(source, "trade_fee")
    resolved_aggregate = resolve_transaction_trade_fee(trade_fee, {}) or Decimal(0)
    resolved_components = resolve_transaction_trade_fee(
        None, _fee_component_values(source)
    ) or Decimal(0)
    return resolved_components if resolved_components != Decimal(0) else resolved_aggregate


def _optional_source_decimal(source: object, field_name: str) -> Decimal:
    raw_value = _optional_source_value(source, field_name)
    if raw_value is None:
        return Decimal(0)
    value = cast(Decimal | None, decimal_or_none(raw_value))
    if value is None:
        raise ValueError(f"{field_name} must be numeric.")
    return value


@dataclass(frozen=True, slots=True, kw_only=True)
class FxCanonicalTransaction:
    """Immutable canonical economics for one persisted FX component."""

    transaction_id: str
    transaction_type: str
    component_type: str
    component_id: str
    portfolio_id: str
    instrument_id: str
    security_id: str
    transaction_date: datetime
    quantity: Decimal
    price: Decimal
    gross_transaction_amount: Decimal
    trade_currency: str
    currency: str
    pair_base_currency: str
    pair_quote_currency: str
    fx_rate_quote_convention: str
    buy_currency: str
    sell_currency: str
    buy_amount: Decimal
    sell_amount: Decimal
    contract_rate: Decimal
    trade_fee: Decimal = Decimal(0)
    withholding_tax_amount: Decimal = Decimal(0)
    linked_component_ids: tuple[str, ...] | None = None
    settlement_date: datetime | None = None
    economic_event_id: str | None = None
    linked_transaction_group_id: str | None = None
    calculation_policy_id: str | None = None
    calculation_policy_version: str | None = None
    fx_cash_leg_role: str | None = None
    linked_fx_cash_leg_id: str | None = None
    settlement_status: str | None = None
    fx_contract_id: str | None = None
    fx_contract_open_transaction_id: str | None = None
    fx_contract_close_transaction_id: str | None = None
    settlement_of_fx_contract_id: str | None = None
    swap_event_id: str | None = None
    near_leg_group_id: str | None = None
    far_leg_group_id: str | None = None
    spot_exposure_model: str | None = None
    fx_realized_pnl_mode: str | None = None
    realized_capital_pnl_local: Decimal | None = None
    realized_fx_pnl_local: Decimal | None = None
    realized_total_pnl_local: Decimal | None = None
    realized_capital_pnl_base: Decimal | None = None
    realized_fx_pnl_base: Decimal | None = None
    realized_total_pnl_base: Decimal | None = None

    def __post_init__(self) -> None:
        for field_name in (
            "trade_currency",
            "currency",
            "pair_base_currency",
            "pair_quote_currency",
            "buy_currency",
            "sell_currency",
        ):
            object.__setattr__(
                self,
                field_name,
                normalize_currency_code(getattr(self, field_name)),
            )
        for field_name in (
            "transaction_type",
            "component_type",
            "fx_rate_quote_convention",
        ):
            object.__setattr__(
                self,
                field_name,
                normalize_transaction_control_code(getattr(self, field_name)),
            )
        for field_name in (
            "fx_cash_leg_role",
            "settlement_status",
            "spot_exposure_model",
            "fx_realized_pnl_mode",
        ):
            object.__setattr__(
                self,
                field_name,
                normalize_optional_transaction_control_code(getattr(self, field_name)),
            )
        if self.linked_component_ids is not None:
            object.__setattr__(self, "linked_component_ids", tuple(self.linked_component_ids))

    @classmethod
    def from_transaction(cls, source: FxTransactionSource) -> FxCanonicalTransaction:
        """Copy FX-relevant values from a booked transaction or event adapter."""

        return cls(
            transaction_id=source.transaction_id,
            transaction_type=source.transaction_type,
            component_type=source.component_type or "",
            component_id=source.component_id or "",
            linked_component_ids=tuple(source.linked_component_ids)
            if source.linked_component_ids is not None
            else None,
            portfolio_id=source.portfolio_id,
            instrument_id=source.instrument_id,
            security_id=source.security_id,
            transaction_date=source.transaction_date,
            settlement_date=source.settlement_date,
            quantity=source.quantity,
            price=source.price,
            gross_transaction_amount=source.gross_transaction_amount,
            trade_currency=source.trade_currency,
            currency=source.currency,
            pair_base_currency=source.pair_base_currency or "",
            pair_quote_currency=source.pair_quote_currency or "",
            fx_rate_quote_convention=source.fx_rate_quote_convention or "",
            buy_currency=source.buy_currency or "",
            sell_currency=source.sell_currency or "",
            buy_amount=source.buy_amount or Decimal(0),
            sell_amount=source.sell_amount or Decimal(0),
            contract_rate=source.contract_rate or Decimal(0),
            trade_fee=_resolved_source_trade_fee(source),
            withholding_tax_amount=_optional_source_decimal(source, "withholding_tax_amount"),
            economic_event_id=_optional_source_value(source, "economic_event_id"),
            linked_transaction_group_id=_optional_source_value(
                source, "linked_transaction_group_id"
            ),
            calculation_policy_id=_optional_source_value(source, "calculation_policy_id"),
            calculation_policy_version=_optional_source_value(source, "calculation_policy_version"),
            fx_cash_leg_role=_optional_source_value(source, "fx_cash_leg_role"),
            linked_fx_cash_leg_id=_optional_source_value(source, "linked_fx_cash_leg_id"),
            settlement_status=_optional_source_value(source, "settlement_status"),
            fx_contract_id=_optional_source_value(source, "fx_contract_id"),
            fx_contract_open_transaction_id=_optional_source_value(
                source, "fx_contract_open_transaction_id"
            ),
            fx_contract_close_transaction_id=_optional_source_value(
                source, "fx_contract_close_transaction_id"
            ),
            settlement_of_fx_contract_id=_optional_source_value(
                source, "settlement_of_fx_contract_id"
            ),
            swap_event_id=_optional_source_value(source, "swap_event_id"),
            near_leg_group_id=_optional_source_value(source, "near_leg_group_id"),
            far_leg_group_id=_optional_source_value(source, "far_leg_group_id"),
            spot_exposure_model=_optional_source_value(source, "spot_exposure_model"),
            fx_realized_pnl_mode=_optional_source_value(source, "fx_realized_pnl_mode"),
            realized_capital_pnl_local=_optional_source_value(source, "realized_capital_pnl_local"),
            realized_fx_pnl_local=_optional_source_value(source, "realized_fx_pnl_local"),
            realized_total_pnl_local=_optional_source_value(source, "realized_total_pnl_local"),
            realized_capital_pnl_base=_optional_source_value(source, "realized_capital_pnl_base"),
            realized_fx_pnl_base=_optional_source_value(source, "realized_fx_pnl_base"),
            realized_total_pnl_base=_optional_source_value(source, "realized_total_pnl_base"),
        )
