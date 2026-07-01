from __future__ import annotations

from decimal import Decimal

from portfolio_common.events import TransactionEvent
from portfolio_common.transaction_domain.control_code_normalization import (
    normalize_transaction_control_code,
)
from portfolio_common.transaction_domain.fx_models import FxCanonicalTransaction
from portfolio_common.transaction_domain.fx_validation import validate_fx_transaction

FX_BASELINE_REALIZED_PNL_MODES = {"NONE", "UPSTREAM_PROVIDED"}


class UnsupportedFxRealizedPnlModeError(ValueError):
    """Raised when baseline FX processing is asked to simulate advanced P&L modes."""


def build_fx_processed_event(event: TransactionEvent) -> TransactionEvent:
    """
    Establishes explicit baseline processing semantics for FX rows until
    richer realized-P&L and valuation treatment is implemented.
    """
    update = build_fx_baseline_processing_update(event)
    return event.model_copy(update=update)


def build_fx_baseline_processing_update(source: object) -> dict[str, object]:
    realized_mode = normalize_transaction_control_code(
        getattr(source, "fx_realized_pnl_mode", None) or "NONE"
    )
    _assert_supported_baseline_realized_mode(realized_mode)
    update = _build_base_fx_processing_update(source, realized_mode)
    update.update(_build_realized_pnl_update(source, realized_mode))
    return update


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


def _build_base_fx_processing_update(
    source: object,
    realized_mode: str,
) -> dict[str, object]:
    return {
        "fx_realized_pnl_mode": realized_mode,
        "gross_cost": _decimal_or_zero(getattr(source, "gross_cost", None)),
        "net_cost": _decimal_or_zero(getattr(source, "net_cost", None)),
        "realized_gain_loss": _decimal_or_zero(getattr(source, "realized_gain_loss", None)),
        "net_cost_local": _decimal_or_zero(getattr(source, "net_cost_local", None)),
        "realized_gain_loss_local": _decimal_or_zero(
            getattr(source, "realized_gain_loss_local", None)
        ),
    }


def _build_realized_pnl_update(
    source: object,
    realized_mode: str,
) -> dict[str, object]:
    if realized_mode == "NONE":
        return _build_zero_realized_pnl_update()
    return _build_upstream_realized_pnl_update(source)


def _build_zero_realized_pnl_update() -> dict[str, object]:
    return {
        "realized_capital_pnl_local": Decimal(0),
        "realized_fx_pnl_local": Decimal(0),
        "realized_total_pnl_local": Decimal(0),
        "realized_capital_pnl_base": Decimal(0),
        "realized_fx_pnl_base": Decimal(0),
        "realized_total_pnl_base": Decimal(0),
    }


def _build_upstream_realized_pnl_update(source: object) -> dict[str, object]:
    capital_local = _decimal_or_zero(getattr(source, "realized_capital_pnl_local", None))
    capital_base = _decimal_or_zero(getattr(source, "realized_capital_pnl_base", None))
    fx_local = _decimal_or_zero(getattr(source, "realized_fx_pnl_local", None))
    fx_base = _decimal_or_zero(getattr(source, "realized_fx_pnl_base", None))
    return {
        "realized_capital_pnl_local": capital_local,
        "realized_capital_pnl_base": capital_base,
        "realized_fx_pnl_local": fx_local,
        "realized_fx_pnl_base": fx_base,
        "realized_total_pnl_local": _resolve_total_pnl(
            getattr(source, "realized_total_pnl_local", None), capital_local, fx_local
        ),
        "realized_total_pnl_base": _resolve_total_pnl(
            getattr(source, "realized_total_pnl_base", None), capital_base, fx_base
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
