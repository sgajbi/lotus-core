"""Define framework-neutral transaction validation findings."""

from dataclasses import dataclass

from .reason_codes import TransactionValidationReasonCode


@dataclass(frozen=True, slots=True)
class TransactionValidationIssue:
    """Describe one deterministic transaction validation finding."""

    code: TransactionValidationReasonCode
    field: str
    message: str
