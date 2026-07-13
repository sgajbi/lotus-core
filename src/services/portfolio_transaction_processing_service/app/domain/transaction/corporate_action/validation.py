"""Validate Corporate Action Bundle A booked transactions."""

from dataclasses import dataclass
from typing import Iterable

from portfolio_common.ca_bundle_a_constants import (
    CA_BUNDLE_A_CASH_CONSIDERATION_TYPE,
    CA_BUNDLE_A_SOURCE_OUT_TYPES,
    CA_BUNDLE_A_TARGET_IN_TYPES,
    CA_BUNDLE_A_TRANSACTION_TYPES,
    normalize_ca_bundle_a_transaction_type,
)

from ..booked import BookedTransaction
from .reason_codes import CorporateActionValidationReasonCode


@dataclass(frozen=True, slots=True)
class CorporateActionValidationFinding:
    """Describe one deterministic corporate-action booking defect."""

    code: CorporateActionValidationReasonCode
    field: str
    message: str


class CorporateActionValidationError(ValueError):
    """Report all corporate-action validation findings for one booking."""

    def __init__(self, findings: Iterable[CorporateActionValidationFinding]) -> None:
        self.findings = tuple(findings)
        message = "; ".join(f"{finding.code}: {finding.field}" for finding in self.findings)
        super().__init__(message or "Corporate Action Bundle A validation failed")


def is_bundle_a_corporate_action(transaction_type: str | None) -> bool:
    """Return whether a source control code belongs to Corporate Action Bundle A."""

    return normalize_ca_bundle_a_transaction_type(transaction_type) in CA_BUNDLE_A_TRANSACTION_TYPES


def validate_bundle_a_corporate_action(
    transaction: BookedTransaction,
) -> tuple[CorporateActionValidationFinding, ...]:
    """Return every validation finding in stable field-policy order."""

    findings: list[CorporateActionValidationFinding] = []
    transaction_type = normalize_ca_bundle_a_transaction_type(transaction.transaction_type)
    if transaction_type not in CA_BUNDLE_A_TRANSACTION_TYPES:
        findings.append(
            _finding(
                CorporateActionValidationReasonCode.INVALID_TRANSACTION_TYPE,
                "transaction_type",
                "transaction_type must be one of SPIN_OFF, SPIN_IN, DEMERGER_OUT, "
                "DEMERGER_IN, CASH_CONSIDERATION.",
            )
        )
        return tuple(findings)

    if not _present(transaction.parent_event_reference):
        findings.append(
            _finding(
                CorporateActionValidationReasonCode.MISSING_PARENT_EVENT_REFERENCE,
                "parent_event_reference",
                "parent_event_reference is required for Bundle A CA transaction types.",
            )
        )
    if not _present(transaction.economic_event_id) or not _present(
        transaction.linked_transaction_group_id
    ):
        findings.append(
            _finding(
                CorporateActionValidationReasonCode.MISSING_LINKAGE_IDENTIFIER,
                "economic_event_id",
                "economic_event_id and linked_transaction_group_id are required for "
                "Bundle A CA transaction types.",
            )
        )
    if transaction_type in CA_BUNDLE_A_SOURCE_OUT_TYPES and not _present(
        transaction.source_instrument_id
    ):
        findings.append(
            _finding(
                CorporateActionValidationReasonCode.MISSING_SOURCE_INSTRUMENT_ID,
                "source_instrument_id",
                "source_instrument_id is required for Bundle A source-out transaction types.",
            )
        )
    if transaction_type in CA_BUNDLE_A_TARGET_IN_TYPES and not _present(
        transaction.target_instrument_id
    ):
        findings.append(
            _finding(
                CorporateActionValidationReasonCode.MISSING_TARGET_INSTRUMENT_ID,
                "target_instrument_id",
                "target_instrument_id is required for Bundle A target-in transaction types.",
            )
        )
    if transaction_type == CA_BUNDLE_A_CASH_CONSIDERATION_TYPE:
        _validate_cash_leg_references(findings, transaction)
    return tuple(findings)


def assert_bundle_a_corporate_action_valid(transaction: BookedTransaction) -> None:
    """Raise one bounded error when a Bundle A booking is invalid."""

    findings = validate_bundle_a_corporate_action(transaction)
    if findings:
        raise CorporateActionValidationError(findings)


def _validate_cash_leg_references(
    findings: list[CorporateActionValidationFinding],
    transaction: BookedTransaction,
) -> None:
    linked_cash_transaction_id = _normalized(transaction.linked_cash_transaction_id)
    external_cash_transaction_id = _normalized(transaction.external_cash_transaction_id)
    if not linked_cash_transaction_id and not external_cash_transaction_id:
        findings.append(
            _finding(
                CorporateActionValidationReasonCode.MISSING_CASH_CONSIDERATION_LINK,
                "linked_cash_transaction_id",
                "CASH_CONSIDERATION requires linked cash-leg reference via "
                "linked_cash_transaction_id or external_cash_transaction_id.",
            )
        )
    if (
        linked_cash_transaction_id
        and external_cash_transaction_id
        and linked_cash_transaction_id != external_cash_transaction_id
    ):
        findings.append(
            _finding(
                CorporateActionValidationReasonCode.INCONSISTENT_CASH_CONSIDERATION_LINK,
                "linked_cash_transaction_id",
                "linked_cash_transaction_id and external_cash_transaction_id must match "
                "when both are provided on CASH_CONSIDERATION.",
            )
        )


def _finding(
    code: CorporateActionValidationReasonCode,
    field: str,
    message: str,
) -> CorporateActionValidationFinding:
    return CorporateActionValidationFinding(code=code, field=field, message=message)


def _present(value: str | None) -> bool:
    return bool(_normalized(value))


def _normalized(value: str | None) -> str:
    return (value or "").strip()
