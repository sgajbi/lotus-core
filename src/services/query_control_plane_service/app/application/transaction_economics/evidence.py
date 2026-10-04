"""Source qualification and timestamp policies for transaction-economics products."""

from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal

from portfolio_common.domain.calculation_lineage import (
    calculation_lineage_binds_output,
    calculation_lineage_from_payload,
)
from portfolio_common.domain.transaction.numeric_policy import TRANSACTION_COST_LEDGER_OUTPUT_V1
from portfolio_common.domain.transaction.payload_identity import (
    transaction_payload_fingerprint,
    transaction_payload_pre_upstream_fingerprint,
)
from portfolio_common.events import TransactionEvent

from ...domain.transaction_economics import BookedTransactionEconomics, FxPnlSourceEvidence


def qualify_fx_pnl_source_evidence(
    *,
    raw_source: object,
    ledger_output: Mapping[str, object],
    stored_fingerprint: str,
    receipt_payload: object,
    tenant_id: str,
    source_portfolio_tenant_id: str | None,
) -> FxPnlSourceEvidence:
    """Verify independent raw presence and the producer's complete persisted output.

    A v1 calculation receipt hashes already-defaulted FX values. It is output integrity,
    not original presence. Retained immutable raw source is required independently.
    Legacy fingerprint compatibility never reconstructs an absent original amount.
    """
    unavailable = FxPnlSourceEvidence(None, None, "FX_SOURCE_AUTHORITY_UNAVAILABLE")
    if not isinstance(raw_source, Mapping):
        return unavailable
    try:
        source = TransactionEvent.model_validate(raw_source)
        if (
            source_portfolio_tenant_id != tenant_id
            or source.tenant_id not in (None, tenant_id)
            or source.transaction_id != ledger_output.get("transaction_id")
            or source.portfolio_id != ledger_output.get("portfolio_id")
            or source.security_id != ledger_output.get("security_id")
            or source.transaction_type != ledger_output.get("transaction_type")
            or source.component_type != ledger_output.get("component_type")
            or source.fx_realized_pnl_mode != "UPSTREAM_PROVIDED"
            or ledger_output.get("fx_realized_pnl_mode") != "UPSTREAM_PROVIDED"
        ):
            return unavailable
        if stored_fingerprint not in (
            transaction_payload_fingerprint(raw_source),
            transaction_payload_pre_upstream_fingerprint(raw_source),
        ):
            return unavailable
        return _qualify_retained_fx_source(
            source=source, ledger_output=ledger_output, receipt_payload=receipt_payload
        )
    except (TypeError, ValueError, ArithmeticError):
        return unavailable


def _qualify_retained_fx_source(
    *, source: TransactionEvent, ledger_output: Mapping[str, object], receipt_payload: object
) -> FxPnlSourceEvidence:
    """Reject invalid retained authority before interpreting either source amount."""
    receipt = calculation_lineage_from_payload(receipt_payload)
    policy = TRANSACTION_COST_LEDGER_OUTPUT_V1
    if (
        receipt is None
        or receipt.algorithm_id != "foreign-exchange-baseline-processing"
        or receipt.algorithm_version != 1
        or receipt.intermediate_precision != policy.working_precision
        or receipt.numeric_output_policy != policy.lineage_identity()
        or not calculation_lineage_binds_output(
            receipt, output_payload=fx_receipt_output_payload(ledger_output)
        )
    ):
        raise ValueError("Retained FX output authority is unavailable")
    local = _qualified_source_amount(source.realized_fx_pnl_local, ledger_output, "local")
    base = _qualified_source_amount(source.realized_fx_pnl_base, ledger_output, "base")
    return FxPnlSourceEvidence(
        local,
        base,
        "FX_SOURCE_QUALIFIED" if local is not None and base is not None else "FX_SOURCE_INCOMPLETE",
    )


def _qualified_source_amount(
    source: Decimal | None, ledger_output: Mapping[str, object], basis: str
) -> Decimal | None:
    if source is None:
        return None
    amount = TRANSACTION_COST_LEDGER_OUTPUT_V1.normalize(source, field_name=f"fx_pnl_{basis}")
    return amount if amount == ledger_output.get(f"realized_fx_pnl_{basis}") else None


def fx_receipt_output_payload(ledger_output: Mapping[str, object]) -> dict[str, object]:
    """Project the existing complete FX receipt at its governed ledger numeric scale.

    The adapter supplies persistence-shaped business fields and admitted tenant authority;
    technical row/fingerprint/update fields are not producer receipt outputs.
    """
    policy = TRANSACTION_COST_LEDGER_OUTPUT_V1
    quantum = Decimal(1).scaleb(-policy.scale)
    output: dict[str, object] = {}
    for name, value in ledger_output.items():
        if value is None:
            continue
        if isinstance(value, Decimal):
            with policy.arithmetic_context():
                value = policy.normalize(value, field_name=name).quantize(
                    quantum, rounding=policy.rounding
                )
        output[name] = value
    return output


def latest_evidence_timestamp(rows: list[BookedTransactionEconomics]) -> datetime | None:
    """Return the latest transaction, cost, or cashflow evidence timestamp."""

    timestamps: list[datetime] = []
    for row in rows:
        if row.updated_at is not None:
            timestamps.append(row.updated_at)
        if row.cashflow is not None and row.cashflow.updated_at is not None:
            timestamps.append(row.cashflow.updated_at)
        timestamps.extend(cost.updated_at for cost in row.costs if cost.updated_at is not None)
    return max(timestamps, default=None)
