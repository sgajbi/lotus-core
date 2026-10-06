"""Pure FX evidence-only confirmation, never economic correction authority.

The owning command must first verify retained source, receipt, tenant, grant and
CAS authority. This policy only decides whether confirmation changes presence
without changing either retained currency-basis output.
"""

from collections.abc import Mapping
from dataclasses import dataclass, replace
from decimal import Decimal, InvalidOperation
from typing import Literal, cast

from portfolio_common.domain.calculation_lineage import (
    build_calculation_lineage,
    calculation_lineage_binds_output,
    calculation_lineage_from_payload,
    canonical_content_hash,
)

from .fx_source_admission import FX_SOURCE_ADMISSION_TYPES
from .fx_source_presence import fx_original_pnl_values, fx_source_presence_input_payload
from .numeric_policy import TRANSACTION_COST_LEDGER_OUTPUT_V1
from .payload_identity import (
    transaction_payload_fingerprint,
    transaction_payload_pre_upstream_fingerprint,
)

FxCurrencyBasis = Literal["local", "base"]


def source_confirmation_material(
    *,
    raw_id: str,
    raw_sha256: str,
    original_receipt: object,
    request_sha256: str,
    original_output: Mapping[str, object],
    confirmed_source: Mapping[str, object],
    original_presence: Mapping[str, bool],
) -> tuple[str, dict[str, object], dict[str, object]]:
    """Normalize and bind identical material for append and independent verification."""
    policy = TRANSACTION_COST_LEDGER_OUTPUT_V1
    original_output_sha256 = canonical_content_hash(retained_fx_output_payload(original_output))
    confirmed_values = retained_fx_output_payload(confirmed_source)
    lineage = build_calculation_lineage(
        algorithm_id="fx-source-evidence-confirmation",
        algorithm_version=1,
        intermediate_precision=policy.working_precision,
        numeric_output_policy=policy.lineage_identity(),
        input_payload={
            "raw_id": raw_id,
            "raw_sha256": raw_sha256,
            "original_presence": original_presence,
            "original_receipt": original_receipt,
            "request_sha256": request_sha256,
        },
        output_payload={
            "original_output_sha256": original_output_sha256,
            "confirmed_source": confirmed_values,
        },
    )
    return (
        cast(str, original_output_sha256),
        confirmed_values,
        cast(dict[str, object], lineage.lineage_payload()),
    )


class SourceEvidenceConfirmationRejected(ValueError):
    """Bounded reason without input values or financial identifiers."""


def verify_confirmed_fx_revision(
    *,
    revision: Mapping[str, object],
    authenticated_claims: Mapping[str, object],
    reason: str,
    portfolio_id: str,
    raw_id: int,
    raw_source: Mapping[str, object],
    ledger_output: Mapping[str, object],
    stored_fingerprint: str,
    original_receipt: object,
    supplied_bases: tuple[FxCurrencyBasis, ...],
    local: Decimal | None,
    base: Decimal | None,
) -> None:
    """Shared pure committed-fact qualification for retries and status projection.

    Claims must already have known-key cryptographic authentication. A row hash
    alone is not authority: independently bind original source/output/receipt,
    the signed initial head, and the new confirmation receipt and source values.
    """
    claims = authenticated_claims
    raw_hash = canonical_content_hash(raw_source)
    links = {
        "authorization_claims": dict(claims),
        "tenant_id": claims["tenant_id"],
        "command_id": claims["command_id"],
        "operation_id": claims["operation_id"],
        "transaction_id": claims["target_transaction_id"],
        "portfolio_id": portfolio_id,
        "reason": reason,
        "correlation_id": claims["correlation_id"],
        "trace_id": claims["trace_id"],
        "canonical_request_sha256": claims["canonical_request_sha256"],
        "root_raw_event_id": raw_id,
        "root_raw_sha256": raw_hash,
        "expected_head_id": str(raw_id),
        "expected_head_sha256": raw_hash,
        "predecessor_revision_id": None,
    }
    if (
        canonical_content_hash(
            {key: value for key, value in revision.items() if key != "revision_sha256"}
        )
        != revision.get("revision_sha256")
        or any(revision.get(key) != value for key, value in links.items())
        or claims["root_raw_id"] != str(raw_id)
        or claims["root_raw_sha256"] != raw_hash
        or claims["expected_head_id"] != str(raw_id)
        or claims["expected_head_sha256"] != raw_hash
        or ledger_output.get("transaction_id") != claims["target_transaction_id"]
        or ledger_output.get("portfolio_id") != portfolio_id
    ):
        raise SourceEvidenceConfirmationRejected("SOURCE_REVISION_FACT_UNVERIFIED")
    original = verify_retained_fx_source(
        raw_source=raw_source,
        ledger_output=ledger_output,
        stored_fingerprint=stored_fingerprint,
        receipt_payload=original_receipt,
        tenant_id=cast(str, claims["tenant_id"]),
    )
    confirmed = confirm_missing_fx_source(
        original,
        local=local if "local" in supplied_bases else original.local.source,
        base=base if "base" in supplied_bases else original.base.source,
    )
    presence = {
        "local": original.local.source is not None,
        "base": original.base.source is not None,
    }
    original_hash, values, receipt = source_confirmation_material(
        raw_id=str(raw_id),
        raw_sha256=raw_hash,
        original_receipt=original_receipt,
        request_sha256=cast(str, claims["canonical_request_sha256"]),
        original_output=ledger_output,
        original_presence=presence,
        confirmed_source={"local": confirmed.local.source, "base": confirmed.base.source},
    )
    if (
        revision.get("original_output_sha256") != original_hash
        or revision.get("qualification_receipt") != receipt
        or revision.get("original_local_present") != presence["local"]
        or revision.get("original_base_present") != presence["base"]
        or revision.get("source_local") != values["local"]
        or revision.get("source_base") != values["base"]
    ):
        raise SourceEvidenceConfirmationRejected("SOURCE_REVISION_FACT_UNVERIFIED")


@dataclass(frozen=True, slots=True)
class FxPnlBasisEvidence:
    source: Decimal | None
    capital: Decimal
    fx: Decimal
    total: Decimal

    def __post_init__(self) -> None:
        for field_name in ("source", "capital", "fx", "total"):
            value = getattr(self, field_name)
            if value is None and field_name == "source":
                continue
            if not isinstance(value, Decimal):
                raise TypeError("FX evidence values must be Decimal")
            if not value.is_finite():
                raise ValueError("FX evidence values must be finite")


@dataclass(frozen=True, slots=True)
class FxSourceEvidenceConfirmation:
    local: FxPnlBasisEvidence
    base: FxPnlBasisEvidence
    confirmed_bases: tuple[FxCurrencyBasis, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.local, FxPnlBasisEvidence) or not isinstance(
            self.base, FxPnlBasisEvidence
        ):
            raise TypeError("FX confirmation requires typed currency-basis evidence")


def retained_fx_output_payload(ledger_output: Mapping[str, object]) -> dict[str, object]:
    """Complete persisted FX output projection; never manufacture an old receipt."""
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


def verify_retained_fx_source(
    *,
    raw_source: Mapping[str, object],
    ledger_output: Mapping[str, object],
    stored_fingerprint: str,
    receipt_payload: object,
    tenant_id: str,
) -> FxSourceEvidenceConfirmation:
    """Refuse unbound raw/source/output before missing-evidence interpretation."""
    identities = (
        "transaction_id",
        "portfolio_id",
        "security_id",
        "transaction_type",
        "component_type",
    )
    if (
        raw_source.get("tenant_id") not in (None, tenant_id)
        or ledger_output.get("tenant_id") != tenant_id
        or any(raw_source.get(name) != ledger_output.get(name) for name in identities)
        or ledger_output.get("transaction_type") not in FX_SOURCE_ADMISSION_TYPES
        or raw_source.get("fx_realized_pnl_mode") != "UPSTREAM_PROVIDED"
        or ledger_output.get("fx_realized_pnl_mode") != "UPSTREAM_PROVIDED"
        or stored_fingerprint
        not in (
            transaction_payload_fingerprint(raw_source),
            transaction_payload_pre_upstream_fingerprint(raw_source),
        )
    ):
        raise SourceEvidenceConfirmationRejected("FX_SOURCE_AUTHORITY_UNAVAILABLE")
    receipt = calculation_lineage_from_payload(receipt_payload)
    if receipt is not None and receipt.algorithm_version == 2:
        return _verify_v2_fx_source(
            raw_source=raw_source, ledger_output=ledger_output, receipt_payload=receipt_payload
        )
    return _verify_v1_fx_source(
        raw_source=raw_source, ledger_output=ledger_output, receipt_payload=receipt_payload
    )


def _verify_v1_fx_source(
    *,
    raw_source: Mapping[str, object],
    ledger_output: Mapping[str, object],
    receipt_payload: object,
) -> FxSourceEvidenceConfirmation:
    receipt = calculation_lineage_from_payload(receipt_payload)
    policy = TRANSACTION_COST_LEDGER_OUTPUT_V1
    if (
        receipt is None
        or receipt.algorithm_id != "foreign-exchange-baseline-processing"
        or receipt.algorithm_version != 1
        or receipt.intermediate_precision != policy.working_precision
        or receipt.numeric_output_policy != policy.lineage_identity()
        or not calculation_lineage_binds_output(
            receipt, output_payload=retained_fx_output_payload(ledger_output)
        )
    ):
        raise SourceEvidenceConfirmationRejected("FX_SOURCE_RECEIPT_UNAVAILABLE")
    return FxSourceEvidenceConfirmation(
        local=_retained_basis(raw_source, ledger_output, "local"),
        base=_retained_basis(raw_source, ledger_output, "base"),
    )


def _verify_v2_fx_source(
    *,
    raw_source: Mapping[str, object],
    ledger_output: Mapping[str, object],
    receipt_payload: object,
) -> FxSourceEvidenceConfirmation:
    receipt = calculation_lineage_from_payload(receipt_payload)
    policy = TRANSACTION_COST_LEDGER_OUTPUT_V1
    if (
        receipt is None
        or receipt.algorithm_id != "foreign-exchange-baseline-processing"
        or receipt.algorithm_version != 2
        or receipt.intermediate_precision != policy.working_precision
        or receipt.numeric_output_policy != policy.lineage_identity()
        or not calculation_lineage_binds_output(
            receipt, output_payload=retained_fx_output_payload(ledger_output)
        )
    ):
        raise SourceEvidenceConfirmationRejected("FX_SOURCE_RECEIPT_UNAVAILABLE")
    if receipt.input_content_hash != canonical_content_hash(
        fx_source_presence_input_payload(
            source_values=fx_original_pnl_values(raw_source),
            booked_output=retained_fx_output_payload(ledger_output),
        )
    ):
        raise SourceEvidenceConfirmationRejected("FX_SOURCE_INPUT_UNAVAILABLE")
    return FxSourceEvidenceConfirmation(
        local=_retained_basis(raw_source, ledger_output, "local"),
        base=_retained_basis(raw_source, ledger_output, "base"),
    )


def _retained_basis(
    raw: Mapping[str, object], output: Mapping[str, object], basis: str
) -> FxPnlBasisEvidence:
    source = raw.get(f"realized_fx_pnl_{basis}")
    if source is not None:
        if not isinstance(source, (str, Decimal)):
            raise SourceEvidenceConfirmationRejected("FX_SOURCE_AMOUNT_INVALID")
        try:
            source = TRANSACTION_COST_LEDGER_OUTPUT_V1.normalize(
                Decimal(source), field_name="fx_source"
            )
        except (InvalidOperation, ValueError, ArithmeticError):
            raise SourceEvidenceConfirmationRejected("FX_SOURCE_AMOUNT_INVALID") from None
        if source != output.get(f"realized_fx_pnl_{basis}"):
            raise SourceEvidenceConfirmationRejected("FX_SOURCE_OUTPUT_MISMATCH")
    try:
        return FxPnlBasisEvidence(
            source=cast(Decimal | None, source),
            capital=cast(Decimal, output[f"realized_capital_pnl_{basis}"]),
            fx=cast(Decimal, output[f"realized_fx_pnl_{basis}"]),
            total=cast(Decimal, output[f"realized_total_pnl_{basis}"]),
        )
    except (KeyError, TypeError, ValueError):
        raise SourceEvidenceConfirmationRejected("FX_SOURCE_OUTPUT_UNAVAILABLE") from None


def confirm_missing_fx_source(
    original: FxSourceEvidenceConfirmation,
    *,
    local: Decimal | None,
    base: Decimal | None,
) -> FxSourceEvidenceConfirmation:
    """Return new presence evidence while preserving all financial outputs.

    A supplied signed companion basis is retained exactly. Only a missing basis
    can become supplied zero; complete source cannot mint another revision.
    """
    bases: tuple[tuple[FxCurrencyBasis, FxPnlBasisEvidence], ...] = (
        ("local", original.local),
        ("base", original.base),
    )
    confirmed_bases = tuple(basis for basis, evidence in bases if evidence.source is None)
    if not confirmed_bases:
        raise SourceEvidenceConfirmationRejected("FX_SOURCE_NO_MISSING_EVIDENCE")
    return FxSourceEvidenceConfirmation(
        local=_confirm_basis(original.local, local),
        base=_confirm_basis(original.base, base),
        confirmed_bases=confirmed_bases,
    )


def _confirm_basis(original: FxPnlBasisEvidence, supplied: Decimal | None) -> FxPnlBasisEvidence:
    if supplied is None:
        raise SourceEvidenceConfirmationRejected("FX_SOURCE_CONFIRMATION_REQUIRED")
    if not isinstance(supplied, Decimal) or not supplied.is_finite():
        raise SourceEvidenceConfirmationRejected("FX_SOURCE_CONFIRMATION_INVALID")
    if original.source is None and supplied != Decimal("0"):
        raise SourceEvidenceConfirmationRejected("FX_SOURCE_CONFIRMATION_NON_ZERO")
    if original.source is not None and supplied != original.source:
        raise SourceEvidenceConfirmationRejected("FX_SOURCE_SUPPLIED_SOURCE_CHANGED")
    if original.capital != Decimal("0") or original.total != original.fx or supplied != original.fx:
        raise SourceEvidenceConfirmationRejected("FX_SOURCE_ECONOMICS_CHANGED")
    return replace(original, source=supplied)
