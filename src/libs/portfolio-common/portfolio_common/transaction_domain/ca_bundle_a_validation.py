from dataclasses import dataclass
from typing import Iterable

from portfolio_common.events import TransactionEvent

from .ca_bundle_a_reason_codes import CaBundleAValidationReasonCode

CA_BUNDLE_A_TRANSACTION_TYPES = {
    "SPIN_OFF",
    "SPIN_IN",
    "DEMERGER_OUT",
    "DEMERGER_IN",
    "CASH_CONSIDERATION",
}
CA_BUNDLE_A_OUT_TYPES = {"SPIN_OFF", "DEMERGER_OUT"}
CA_BUNDLE_A_IN_TYPES = {"SPIN_IN", "DEMERGER_IN"}
CASH_CONSIDERATION_TRANSACTION_TYPE = "CASH_CONSIDERATION"


@dataclass(frozen=True)
class CaBundleAValidationIssue:
    code: CaBundleAValidationReasonCode
    field: str
    message: str


class CaBundleAValidationError(ValueError):
    def __init__(self, issues: Iterable[CaBundleAValidationIssue]) -> None:
        self.issues = list(issues)
        message = "; ".join(f"{i.code}: {i.field}" for i in self.issues)
        super().__init__(message or "CA Bundle A validation failed")


def is_ca_bundle_a_transaction_type(transaction_type: str | None) -> bool:
    return (transaction_type or "").upper() in CA_BUNDLE_A_TRANSACTION_TYPES


def validate_ca_bundle_a_transaction(event: TransactionEvent) -> list[CaBundleAValidationIssue]:
    issues: list[CaBundleAValidationIssue] = []
    transaction_type = event.transaction_type.upper()

    if transaction_type not in CA_BUNDLE_A_TRANSACTION_TYPES:
        issues.append(
            CaBundleAValidationIssue(
                code=CaBundleAValidationReasonCode.INVALID_TRANSACTION_TYPE,
                field="transaction_type",
                message=(
                    "transaction_type must be one of "
                    "SPIN_OFF, SPIN_IN, DEMERGER_OUT, DEMERGER_IN, CASH_CONSIDERATION."
                ),
            )
        )
        return issues

    if not (event.parent_event_reference or "").strip():
        issues.append(
            CaBundleAValidationIssue(
                code=CaBundleAValidationReasonCode.MISSING_PARENT_EVENT_REFERENCE,
                field="parent_event_reference",
                message="parent_event_reference is required for Bundle A CA transaction types.",
            )
        )

    if not (event.economic_event_id or "").strip() or not (
        event.linked_transaction_group_id or ""
    ).strip():
        issues.append(
            CaBundleAValidationIssue(
                code=CaBundleAValidationReasonCode.MISSING_LINKAGE_IDENTIFIER,
                field="economic_event_id",
                message=(
                    "economic_event_id and linked_transaction_group_id are required for "
                    "Bundle A CA transaction types."
                ),
            )
        )

    if transaction_type in CA_BUNDLE_A_OUT_TYPES and not (event.source_instrument_id or "").strip():
        issues.append(
            CaBundleAValidationIssue(
                code=CaBundleAValidationReasonCode.MISSING_SOURCE_INSTRUMENT_ID,
                field="source_instrument_id",
                message=(
                    "source_instrument_id is required for Bundle A source-out "
                    "transaction types."
                ),
            )
        )

    if transaction_type in CA_BUNDLE_A_IN_TYPES and not (event.target_instrument_id or "").strip():
        issues.append(
            CaBundleAValidationIssue(
                code=CaBundleAValidationReasonCode.MISSING_TARGET_INSTRUMENT_ID,
                field="target_instrument_id",
                message=(
                    "target_instrument_id is required for Bundle A target-in "
                    "transaction types."
                ),
            )
        )

    if transaction_type == CASH_CONSIDERATION_TRANSACTION_TYPE:
        linked_cash_transaction_id = (event.linked_cash_transaction_id or "").strip()
        external_cash_transaction_id = (event.external_cash_transaction_id or "").strip()
        if not linked_cash_transaction_id and not external_cash_transaction_id:
            issues.append(
                CaBundleAValidationIssue(
                    code=CaBundleAValidationReasonCode.MISSING_CASH_CONSIDERATION_LINK,
                    field="linked_cash_transaction_id",
                    message=(
                        "CASH_CONSIDERATION requires linked cash-leg reference via "
                        "linked_cash_transaction_id or external_cash_transaction_id."
                    ),
                )
            )
        if (
            linked_cash_transaction_id
            and external_cash_transaction_id
            and linked_cash_transaction_id != external_cash_transaction_id
        ):
            issues.append(
                CaBundleAValidationIssue(
                    code=CaBundleAValidationReasonCode.INCONSISTENT_CASH_CONSIDERATION_LINK,
                    field="linked_cash_transaction_id",
                    message=(
                        "linked_cash_transaction_id and external_cash_transaction_id must match "
                        "when both are provided on CASH_CONSIDERATION."
                    ),
                )
            )

    return issues


def assert_ca_bundle_a_transaction_valid(event: TransactionEvent) -> None:
    issues = validate_ca_bundle_a_transaction(event)
    if issues:
        raise CaBundleAValidationError(issues)
