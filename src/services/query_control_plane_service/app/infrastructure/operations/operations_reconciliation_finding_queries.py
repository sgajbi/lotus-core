"""SQL projections for reconciliation-finding support evidence."""

from __future__ import annotations

from datetime import datetime

from portfolio_common.database_models import FinancialReconciliationFinding
from portfolio_common.identifiers import normalize_lookup_identifier as normalize_security_id
from sqlalchemy import case, func, select, true

from ...domain.operations import ReconciliationFindingSummary
from .operations_position_scope_queries import security_id_expr


def apply_reconciliation_finding_scope(
    stmt,
    *,
    run_id: str,
    finding_id: str | None = None,
    normalized_security_id: str | None = None,
    transaction_id: str | None = None,
    as_of: datetime | None = None,
):
    stmt = stmt.where(FinancialReconciliationFinding.run_id == run_id)
    if as_of is not None:
        stmt = stmt.where(FinancialReconciliationFinding.created_at <= as_of)
    if finding_id:
        stmt = stmt.where(FinancialReconciliationFinding.finding_id == finding_id)
    if normalized_security_id:
        finding_security_id = security_id_expr(FinancialReconciliationFinding.security_id)
        stmt = stmt.where(finding_security_id == normalized_security_id)
    if transaction_id:
        stmt = stmt.where(FinancialReconciliationFinding.transaction_id == transaction_id)
    return stmt


def reconciliation_finding_severity_rank():
    severity = func.upper(func.trim(FinancialReconciliationFinding.severity))
    return case(
        (severity == "BLOCKER", 0),
        (severity == "CRITICAL", 1),
        (severity == "ERROR", 2),
        (severity == "WARNING", 3),
        (severity == "INFO", 4),
        else_=9,
    )


def reconciliation_finding_summary_base_select():
    return select(
        FinancialReconciliationFinding.severity.label("severity"),
        FinancialReconciliationFinding.resolution_state.label("resolution_state"),
        FinancialReconciliationFinding.created_at.label("created_at"),
        FinancialReconciliationFinding.resolved_at.label("resolved_at"),
        FinancialReconciliationFinding.id.label("id"),
        FinancialReconciliationFinding.finding_id.label("finding_id"),
        FinancialReconciliationFinding.finding_type.label("finding_type"),
        security_id_expr(FinancialReconciliationFinding.security_id).label("security_id"),
        FinancialReconciliationFinding.transaction_id.label("transaction_id"),
        FinancialReconciliationFinding.owner.label("owner"),
        FinancialReconciliationFinding.repair_recommendation.label("repair_recommendation"),
    )


def reconciliation_finding_summary_select(base_stmt):
    base_subq = base_stmt.subquery()
    normalized_severity = func.upper(func.trim(base_subq.c.severity))
    is_open = base_subq.c.resolution_state.in_(("OPEN", "IN_PROGRESS"))
    is_blocking = is_open & normalized_severity.in_(("BLOCKER", "CRITICAL", "ERROR"))
    aggregate_subq = (
        select(
            func.count().label("total_findings"),
            func.count().filter(is_open).label("open_findings"),
            func.count().filter(is_blocking).label("blocking_findings"),
            func.count()
            .filter(is_open & (normalized_severity == "BLOCKER"))
            .label("blocker_findings"),
            func.count()
            .filter(is_open & (normalized_severity == "CRITICAL"))
            .label("critical_findings"),
            func.count().filter(is_open & (normalized_severity == "ERROR")).label("error_findings"),
            func.count()
            .filter(is_open & (normalized_severity == "WARNING"))
            .label("warning_findings"),
            func.count().filter(is_open & (normalized_severity == "INFO")).label("info_findings"),
            func.max(func.coalesce(base_subq.c.resolved_at, base_subq.c.created_at)).label(
                "latest_evidence_at"
            ),
        )
        .select_from(base_subq)
        .subquery()
    )
    top_blocking_subq = (
        select(
            base_subq.c.finding_id,
            base_subq.c.finding_type,
            base_subq.c.security_id,
            base_subq.c.transaction_id,
            base_subq.c.owner,
            base_subq.c.repair_recommendation,
            base_subq.c.created_at,
            case(
                (normalized_severity == "BLOCKER", 0),
                (normalized_severity == "CRITICAL", 1),
                (normalized_severity == "ERROR", 2),
                else_=9,
            ).label("severity_rank"),
        )
        .where(is_blocking)
        .order_by("severity_rank", base_subq.c.created_at.asc(), base_subq.c.id.asc())
        .limit(1)
        .subquery()
    )
    return (
        select(
            aggregate_subq.c.total_findings,
            aggregate_subq.c.open_findings,
            aggregate_subq.c.blocking_findings,
            aggregate_subq.c.blocker_findings,
            aggregate_subq.c.critical_findings,
            aggregate_subq.c.error_findings,
            aggregate_subq.c.warning_findings,
            aggregate_subq.c.info_findings,
            aggregate_subq.c.latest_evidence_at,
            top_blocking_subq.c.finding_id,
            top_blocking_subq.c.finding_type,
            top_blocking_subq.c.security_id,
            top_blocking_subq.c.transaction_id,
            top_blocking_subq.c.owner,
            top_blocking_subq.c.repair_recommendation,
            top_blocking_subq.c.created_at,
        )
        .select_from(aggregate_subq)
        .outerjoin(top_blocking_subq, true())
    )


def reconciliation_finding_summary_from_row(row) -> ReconciliationFindingSummary:
    return ReconciliationFindingSummary(
        total_findings=int(row.total_findings or 0),
        open_findings=int(row.open_findings or 0),
        blocking_findings=int(row.blocking_findings or 0),
        blocker_findings=int(row.blocker_findings or 0),
        critical_findings=int(row.critical_findings or 0),
        error_findings=int(row.error_findings or 0),
        warning_findings=int(row.warning_findings or 0),
        info_findings=int(row.info_findings or 0),
        latest_evidence_at=row.latest_evidence_at,
        top_blocking_finding_id=row.finding_id,
        top_blocking_finding_type=row.finding_type,
        top_blocking_finding_security_id=normalize_security_id(row.security_id),
        top_blocking_finding_transaction_id=row.transaction_id,
        top_blocking_finding_owner=row.owner,
        top_blocking_repair_recommendation=row.repair_recommendation,
        top_blocking_finding_created_at=row.created_at,
    )
