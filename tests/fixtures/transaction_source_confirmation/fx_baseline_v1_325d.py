"""Apply the governed baseline cost and realized-P&L policy to FX components."""

from __future__ import annotations

from collections.abc import Mapping, Sequence, Set
from dataclasses import asdict, fields, replace
from datetime import UTC, datetime
from decimal import Decimal
from typing import TypedDict

from portfolio_common.domain.calculation_lineage import build_calculation_lineage
from portfolio_common.domain.transaction.numeric_policy import (
    TRANSACTION_COST_LEDGER_OUTPUT_V1,
)
from portfolio_common.domain.transaction_control_codes import (
    normalize_transaction_control_code,
)

from ..booked import BookedTransaction
from .models import FxCanonicalTransaction
from .validation import validate_fx_transaction

FX_BASELINE_REALIZED_PNL_MODES = {"NONE", "UPSTREAM_PROVIDED"}
FX_BASELINE_CALCULATION_ALGORITHM_ID = "foreign-exchange-baseline-processing"
FX_BASELINE_CALCULATION_ALGORITHM_VERSION = 1

_NON_PERSISTED_BOOKED_TRANSACTION_FIELDS = frozenset(
    {
        "brokerage",
        "calculation_lineage",
        "epoch",
        "exchange_fee",
        "gst",
        "other_fees",
        "stamp_duty",
    }
)


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
    processed_transaction = replace(transaction, **update, calculation_lineage=None)
    canonical_input = FxCanonicalTransaction.from_transaction(processed_transaction)
    lineage = build_calculation_lineage(
        algorithm_id=FX_BASELINE_CALCULATION_ALGORITHM_ID,
        algorithm_version=FX_BASELINE_CALCULATION_ALGORITHM_VERSION,
        intermediate_precision=TRANSACTION_COST_LEDGER_OUTPUT_V1.working_precision,
        input_payload=_canonical_fx_lineage_payload(asdict(canonical_input)),
        output_payload=fx_booked_transaction_output_payload(processed_transaction),
        numeric_output_policy=TRANSACTION_COST_LEDGER_OUTPUT_V1.lineage_identity(),
    )
    return replace(processed_transaction, calculation_lineage=lineage)


def fx_booked_transaction_output_payload(
    transaction: BookedTransaction,
) -> dict[str, object]:
    """Return the complete persistence-shaped FX transaction output for lineage."""

    return {
        field.name: _canonical_fx_lineage_value(value, field_path=field.name)
        for field in fields(transaction)
        if field.name not in _NON_PERSISTED_BOOKED_TRANSACTION_FIELDS
        and (value := getattr(transaction, field.name)) is not None
    }


def _canonical_fx_lineage_payload(payload: Mapping[str, object]) -> dict[str, object]:
    return {
        key: _canonical_fx_lineage_value(value, field_path=key) for key, value in payload.items()
    }


def _canonical_fx_lineage_value(value: object, *, field_path: str) -> object:
    """Match the governed numeric representation used by the transaction ledger."""

    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(
                f"FX calculation-lineage timestamp '{field_path}' must be timezone-aware."
            )
        return value.astimezone(UTC)
    if isinstance(value, Decimal):
        normalized = TRANSACTION_COST_LEDGER_OUTPUT_V1.normalize(
            value,
            field_name=field_path,
        )
        quantum = Decimal(1).scaleb(-TRANSACTION_COST_LEDGER_OUTPUT_V1.scale)
        with TRANSACTION_COST_LEDGER_OUTPUT_V1.arithmetic_context():
            return normalized.quantize(
                quantum,
                rounding=TRANSACTION_COST_LEDGER_OUTPUT_V1.rounding,
            )
    if isinstance(value, Mapping):
        return {
            key: _canonical_fx_lineage_value(item, field_path=f"{field_path}.{key}")
            for key, item in value.items()
        }
    if isinstance(value, Set):
        return {_canonical_fx_lineage_value(item, field_path=f"{field_path}[]") for item in value}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [
            _canonical_fx_lineage_value(item, field_path=f"{field_path}[{index}]")
            for index, item in enumerate(value)
        ]
    return value


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
