from __future__ import annotations

from decimal import Decimal

from portfolio_common.events import TransactionEvent
from portfolio_common.transaction_domain.fx_models import FxCanonicalTransaction
from portfolio_common.transaction_domain.fx_validation import validate_fx_transaction


def build_fx_processed_event(event: TransactionEvent) -> TransactionEvent:
    """
    Establishes explicit baseline processing semantics for FX rows until
    richer realized-P&L and valuation treatment is implemented.
    """
    realized_mode = (event.fx_realized_pnl_mode or "NONE").upper()
    update: dict[str, object] = {
        "gross_cost": event.gross_cost if event.gross_cost is not None else Decimal(0),
        "net_cost": event.net_cost if event.net_cost is not None else Decimal(0),
        "realized_gain_loss": (
            event.realized_gain_loss if event.realized_gain_loss is not None else Decimal(0)
        ),
        "net_cost_local": event.net_cost_local if event.net_cost_local is not None else Decimal(0),
        "realized_gain_loss_local": (
            event.realized_gain_loss_local
            if event.realized_gain_loss_local is not None
            else Decimal(0)
        ),
    }
    if realized_mode == "NONE":
        update.update(
            {
                "realized_capital_pnl_local": Decimal(0),
                "realized_fx_pnl_local": Decimal(0),
                "realized_total_pnl_local": Decimal(0),
                "realized_capital_pnl_base": Decimal(0),
                "realized_fx_pnl_base": Decimal(0),
                "realized_total_pnl_base": Decimal(0),
            }
        )
    else:
        capital_local = (
            event.realized_capital_pnl_local
            if event.realized_capital_pnl_local is not None
            else Decimal(0)
        )
        capital_base = (
            event.realized_capital_pnl_base
            if event.realized_capital_pnl_base is not None
            else Decimal(0)
        )
        fx_local = (
            event.realized_fx_pnl_local if event.realized_fx_pnl_local is not None else Decimal(0)
        )
        fx_base = (
            event.realized_fx_pnl_base if event.realized_fx_pnl_base is not None else Decimal(0)
        )
        update.update(
            {
                "realized_capital_pnl_local": capital_local,
                "realized_capital_pnl_base": capital_base,
                "realized_fx_pnl_local": fx_local,
                "realized_fx_pnl_base": fx_base,
                "realized_total_pnl_local": (
                    event.realized_total_pnl_local
                    if event.realized_total_pnl_local is not None
                    else capital_local + fx_local
                ),
                "realized_total_pnl_base": (
                    event.realized_total_pnl_base
                    if event.realized_total_pnl_base is not None
                    else capital_base + fx_base
                ),
            }
        )
    return event.model_copy(update=update)


def assert_fx_processed_event_valid(
    event: TransactionEvent, *, strict_metadata: bool = True
) -> None:
    canonical = FxCanonicalTransaction.model_validate(event.model_dump(mode="python"))
    issues = validate_fx_transaction(canonical, strict_metadata=strict_metadata)
    if issues:
        message = "; ".join(f"{issue.code}:{issue.field}" for issue in issues)
        raise ValueError(f"FX validation failed: {message}")
