"""Logging and Prometheus adaptation for corporate-action reconciliation outcomes."""

import logging
from dataclasses import dataclass

from portfolio_common.monitoring import observe_financial_reconciliation_run

from ...application import CORPORATE_ACTION_RECONCILIATION_TYPE
from ...ports import CorporateActionReconciliationObservation

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class _FindingSeverity:
    severity: str


class PrometheusCorporateActionReconciliationObserver:
    """Translate application observations into stable support logs and metrics."""

    def observe(self, observation: CorporateActionReconciliationObservation) -> None:
        """Record one successfully persisted reconciliation outcome."""

        try:
            self._record(observation)
        except Exception:
            logger.exception(
                "Corporate-action reconciliation observation failed.",
                extra={
                    "portfolio_id": observation.processed_transaction.portfolio_id,
                    "transaction_id": observation.processed_transaction.transaction_id,
                    "reconciliation_status": observation.reconciliation_status,
                },
            )

    def _record(self, observation: CorporateActionReconciliationObservation) -> None:
        findings = tuple(
            _FindingSeverity(severity=severity) for severity in observation.finding_severities
        )
        observe_financial_reconciliation_run(
            CORPORATE_ACTION_RECONCILIATION_TYPE,
            "COMPLETED",
            0.0,
            findings,
        )
        self._log_state(observation)

    @staticmethod
    def _log_state(observation: CorporateActionReconciliationObservation) -> None:
        key = observation.key
        transaction = observation.processed_transaction
        logger.info(
            "bundle_a_reconciliation_state",
            extra={
                "portfolio_id": transaction.portfolio_id,
                "transaction_id": transaction.transaction_id,
                "linked_transaction_group_id": key.linked_transaction_group_id,
                "parent_event_reference": key.parent_event_reference,
                "reconciliation_status": observation.reconciliation_status,
                "source_leg_count": observation.source_leg_count,
                "target_leg_count": observation.target_leg_count,
                "cash_consideration_count": observation.cash_consideration_count,
                "source_basis_out_local": str(observation.source_basis_out_local),
                "target_basis_in_local": str(observation.target_basis_in_local),
                "cash_basis_local": str(observation.cash_basis_local),
                "missing_cash_basis_count": observation.missing_cash_basis_count,
                "net_basis_delta_local": str(observation.net_basis_delta_local),
                "basis_tolerance": str(observation.basis_tolerance),
                "missing_dependency_reference_ids": list(
                    observation.missing_dependency_reference_ids
                ),
            },
        )
        if observation.reconciliation_status == "basis_mismatch":
            logger.warning(
                "bundle_a_basis_mismatch_detected",
                extra={
                    "portfolio_id": transaction.portfolio_id,
                    "linked_transaction_group_id": key.linked_transaction_group_id,
                    "parent_event_reference": key.parent_event_reference,
                    "net_basis_delta_local": str(observation.net_basis_delta_local),
                    "basis_tolerance": str(observation.basis_tolerance),
                },
            )
        if observation.reconciliation_status == "insufficient_cash_basis":
            logger.warning(
                "bundle_a_cash_basis_evidence_missing",
                extra={
                    "portfolio_id": transaction.portfolio_id,
                    "linked_transaction_group_id": key.linked_transaction_group_id,
                    "parent_event_reference": key.parent_event_reference,
                    "cash_consideration_count": observation.cash_consideration_count,
                    "missing_cash_basis_count": observation.missing_cash_basis_count,
                },
            )
        if observation.missing_dependency_reference_ids:
            logger.warning(
                "bundle_a_dependency_gap_detected",
                extra={
                    "portfolio_id": transaction.portfolio_id,
                    "transaction_id": transaction.transaction_id,
                    "linked_transaction_group_id": key.linked_transaction_group_id,
                    "parent_event_reference": key.parent_event_reference,
                    "missing_dependency_reference_ids": list(
                        observation.missing_dependency_reference_ids
                    ),
                },
            )


PROMETHEUS_CORPORATE_ACTION_RECONCILIATION_OBSERVER = (
    PrometheusCorporateActionReconciliationObserver()
)
