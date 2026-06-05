from __future__ import annotations

from decimal import Decimal

from portfolio_common.events import TransactionEvent
from portfolio_common.transaction_domain.control_code_normalization import (
    normalize_transaction_control_code,
)
from portfolio_common.transaction_domain.fx_models import FxCanonicalTransaction
from portfolio_common.transaction_domain.fx_validation import validate_fx_transaction


def build_fx_processed_event(event: TransactionEvent) -> TransactionEvent:
    """
    Establishes explicit baseline processing semantics for FX rows until
    richer realized-P&L and valuation treatment is implemented.
    """
    realized_mode = normalize_transaction_control_code(event.fx_realized_pnl_mode or "NONE")
    update = _build_base_fx_processing_update(event, realized_mode)
    update.update(_build_realized_pnl_update(event, realized_mode))
    return event.model_copy(update=update)


def _decimal_or_zero(value: Decimal | None) -> Decimal:
    return value if value is not None else Decimal(0)


def _build_base_fx_processing_update(
    event: TransactionEvent,
    realized_mode: str,
) -> dict[str, object]:
    return {
        "fx_realized_pnl_mode": realized_mode,
        "gross_cost": _decimal_or_zero(event.gross_cost),
        "net_cost": _decimal_or_zero(event.net_cost),
        "realized_gain_loss": _decimal_or_zero(event.realized_gain_loss),
        "net_cost_local": _decimal_or_zero(event.net_cost_local),
        "realized_gain_loss_local": _decimal_or_zero(event.realized_gain_loss_local),
    }


def _build_realized_pnl_update(
    event: TransactionEvent,
    realized_mode: str,
) -> dict[str, object]:
    if realized_mode == "NONE":
        return _build_zero_realized_pnl_update()
    return _build_upstream_realized_pnl_update(event)


def _build_zero_realized_pnl_update() -> dict[str, object]:
    return {
        "realized_capital_pnl_local": Decimal(0),
        "realized_fx_pnl_local": Decimal(0),
        "realized_total_pnl_local": Decimal(0),
        "realized_capital_pnl_base": Decimal(0),
        "realized_fx_pnl_base": Decimal(0),
        "realized_total_pnl_base": Decimal(0),
    }


def _build_upstream_realized_pnl_update(event: TransactionEvent) -> dict[str, object]:
    capital_local = _decimal_or_zero(event.realized_capital_pnl_local)
    capital_base = _decimal_or_zero(event.realized_capital_pnl_base)
    fx_local = _decimal_or_zero(event.realized_fx_pnl_local)
    fx_base = _decimal_or_zero(event.realized_fx_pnl_base)
    return {
        "realized_capital_pnl_local": capital_local,
        "realized_capital_pnl_base": capital_base,
        "realized_fx_pnl_local": fx_local,
        "realized_fx_pnl_base": fx_base,
        "realized_total_pnl_local": _resolve_total_pnl(
            event.realized_total_pnl_local, capital_local, fx_local
        ),
        "realized_total_pnl_base": _resolve_total_pnl(
            event.realized_total_pnl_base, capital_base, fx_base
        ),
    }


def _resolve_total_pnl(
    total_pnl: Decimal | None,
    capital_pnl: Decimal,
    fx_pnl: Decimal,
) -> Decimal:
    return total_pnl if total_pnl is not None else capital_pnl + fx_pnl


def assert_fx_processed_event_valid(
    event: TransactionEvent, *, strict_metadata: bool = True
) -> None:
    canonical = FxCanonicalTransaction.model_validate(event.model_dump(mode="python"))
    issues = validate_fx_transaction(canonical, strict_metadata=strict_metadata)
    if issues:
        message = "; ".join(f"{issue.code}:{issue.field}" for issue in issues)
        raise ValueError(f"FX validation failed: {message}")
