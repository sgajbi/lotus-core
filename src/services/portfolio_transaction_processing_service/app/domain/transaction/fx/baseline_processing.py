"""Apply the governed baseline cost and realized-P&L policy to FX components."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from typing import TypedDict

from portfolio_common.domain.transaction_control_codes import (
    normalize_transaction_control_code,
)

from ..booked import BookedTransaction
from .models import FxCanonicalTransaction
from .validation import validate_fx_transaction

FX_BASELINE_REALIZED_PNL_MODES = {"NONE", "UPSTREAM_PROVIDED"}


class UnsupportedFxRealizedPnlModeError(ValueError):
    """Raised when baseline FX processing is asked to simulate advanced P&L modes."""


class FxBaselineProcessingUpdate(TypedDict):
    """Calculated cost and realized-P&L fields for one FX component."""

    fx_realized_pnl_mode: str
    gross_cost: Decimal
    net_cost: Decimal
    realized_gain_loss: Decimal
    net_cost_local: Decimal
    realized_gain_loss_local: Decimal
    realized_capital_pnl_local: Decimal
    realized_fx_pnl_local: Decimal
    realized_total_pnl_local: Decimal
    realized_capital_pnl_base: Decimal
    realized_fx_pnl_base: Decimal
    realized_total_pnl_base: Decimal


def build_fx_processed_transaction(transaction: BookedTransaction) -> BookedTransaction:
    """Apply explicit baseline cost and realized-P&L semantics to an FX component."""

    update = build_fx_baseline_processing_update(transaction)
    return replace(transaction, **update)


def build_fx_baseline_processing_update(source: object) -> FxBaselineProcessingUpdate:
    realized_mode = normalize_transaction_control_code(
        getattr(source, "fx_realized_pnl_mode", None) or "NONE"
    )
    _assert_supported_baseline_realized_mode(realized_mode)
    (
        capital_local,
        fx_local,
        total_local,
        capital_base,
        fx_base,
        total_base,
    ) = _resolve_realized_pnl_values(source, realized_mode)
    return {
        "fx_realized_pnl_mode": realized_mode,
        "gross_cost": _decimal_or_zero(getattr(source, "gross_cost", None)),
        "net_cost": _decimal_or_zero(getattr(source, "net_cost", None)),
        "realized_gain_loss": _decimal_or_zero(getattr(source, "realized_gain_loss", None)),
        "net_cost_local": _decimal_or_zero(getattr(source, "net_cost_local", None)),
        "realized_gain_loss_local": _decimal_or_zero(
            getattr(source, "realized_gain_loss_local", None)
        ),
        "realized_capital_pnl_local": capital_local,
        "realized_fx_pnl_local": fx_local,
        "realized_total_pnl_local": total_local,
        "realized_capital_pnl_base": capital_base,
        "realized_fx_pnl_base": fx_base,
        "realized_total_pnl_base": total_base,
    }


def _assert_supported_baseline_realized_mode(realized_mode: str) -> None:
    if realized_mode in FX_BASELINE_REALIZED_PNL_MODES:
        return
    raise UnsupportedFxRealizedPnlModeError(
        "FX realized P&L mode "
        f"'{realized_mode}' is not supported by baseline FX cost processing; "
        "supported modes are NONE and UPSTREAM_PROVIDED."
    )


def _decimal_or_zero(value: Decimal | None) -> Decimal:
    return value if value is not None else Decimal(0)


def _resolve_realized_pnl_values(
    source: object,
    realized_mode: str,
) -> tuple[Decimal, Decimal, Decimal, Decimal, Decimal, Decimal]:
    if realized_mode == "NONE":
        zero = Decimal(0)
        return zero, zero, zero, zero, zero, zero
    capital_local = _decimal_or_zero(getattr(source, "realized_capital_pnl_local", None))
    capital_base = _decimal_or_zero(getattr(source, "realized_capital_pnl_base", None))
    fx_local = _decimal_or_zero(getattr(source, "realized_fx_pnl_local", None))
    fx_base = _decimal_or_zero(getattr(source, "realized_fx_pnl_base", None))
    return (
        capital_local,
        fx_local,
        _resolve_total_pnl(
            getattr(source, "realized_total_pnl_local", None), capital_local, fx_local
        ),
        capital_base,
        fx_base,
        _resolve_total_pnl(getattr(source, "realized_total_pnl_base", None), capital_base, fx_base),
    )


def _resolve_total_pnl(
    total_pnl: Decimal | None,
    capital_pnl: Decimal,
    fx_pnl: Decimal,
) -> Decimal:
    return total_pnl if total_pnl is not None else capital_pnl + fx_pnl


def assert_fx_processed_transaction_valid(
    transaction: BookedTransaction, *, strict_metadata: bool = True
) -> None:
    canonical = FxCanonicalTransaction.from_transaction(transaction)
    issues = validate_fx_transaction(canonical, strict_metadata=strict_metadata)
    if issues:
        message = "; ".join(f"{issue.code}:{issue.field}" for issue in issues)
        raise ValueError(f"FX validation failed: {message}")
