"""Govern closed parent-event cohorts for corporate-action execution readiness."""

from __future__ import annotations

from dataclasses import dataclass

CORPORATE_ACTION_OVERLAY_TRANSACTION_TYPES = frozenset(
    {"CASH_CONSIDERATION", "CASH_IN_LIEU", "ADJUSTMENT", "FEE", "TAX"}
)


@dataclass(frozen=True, slots=True)
class CorporateActionCohortPolicy:
    """Define one supported one-source, one-or-more-target event family."""

    corporate_action_type: str
    source_transaction_type: str
    source_role: str
    target_transaction_type: str

    @property
    def allowed_transaction_types(self) -> frozenset[str]:
        """Return the closed child vocabulary for this event family."""

        return frozenset(
            {
                self.source_transaction_type,
                self.target_transaction_type,
                *CORPORATE_ACTION_OVERLAY_TRANSACTION_TYPES,
            }
        )


_POLICIES = (
    CorporateActionCohortPolicy("SPIN_OFF", "SPIN_OFF", "SOURCE_POSITION_REDUCE", "SPIN_IN"),
    CorporateActionCohortPolicy(
        "DEMERGER", "DEMERGER_OUT", "SOURCE_POSITION_REDUCE", "DEMERGER_IN"
    ),
    CorporateActionCohortPolicy("MERGER", "MERGER_OUT", "SOURCE_POSITION_CLOSE", "MERGER_IN"),
    CorporateActionCohortPolicy(
        "MANDATORY_EXCHANGE",
        "EXCHANGE_OUT",
        "SOURCE_POSITION_CLOSE",
        "EXCHANGE_IN",
    ),
    CorporateActionCohortPolicy(
        "SECURITY_REPLACEMENT",
        "REPLACEMENT_OUT",
        "SOURCE_POSITION_CLOSE",
        "REPLACEMENT_IN",
    ),
)
_POLICY_BY_EVENT_TYPE = {policy.corporate_action_type: policy for policy in _POLICIES}


def corporate_action_cohort_policy(
    corporate_action_type: str,
) -> CorporateActionCohortPolicy | None:
    """Return an explicit policy; unknown or ambiguous event labels remain unsupported."""

    return _POLICY_BY_EVENT_TYPE.get(corporate_action_type.strip().upper())
