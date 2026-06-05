from __future__ import annotations

from datetime import datetime

from portfolio_common.database_models import FinancialReconciliationFinding
from sqlalchemy import case, func, select, true

from .identifier_normalization import normalize_security_id
from .operations_models import ReconciliationFindingSummary
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
    severity = FinancialReconciliationFinding.severity
    return case(
        (severity == "ERROR", 0),
        (severity == "WARNING", 1),
        (severity == "INFO", 2),
        else_=9,
    )


def reconciliation_finding_summary_base_select():
    return select(
        FinancialReconciliationFinding.severity.label("severity"),
        FinancialReconciliationFinding.created_at.label("created_at"),
        FinancialReconciliationFinding.id.label("id"),
        FinancialReconciliationFinding.finding_id.label("finding_id"),
        FinancialReconciliationFinding.finding_type.label("finding_type"),
        security_id_expr(FinancialReconciliationFinding.security_id).label("security_id"),
        FinancialReconciliationFinding.transaction_id.label("transaction_id"),
    )


def reconciliation_finding_summary_select(base_stmt):
    base_subq = base_stmt.subquery()
    aggregate_subq = (
        select(
            func.count().label("total_findings"),
            func.count().filter(base_subq.c.severity == "ERROR").label("blocking_findings"),
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
        )
        .where(base_subq.c.severity == "ERROR")
        .order_by(base_subq.c.created_at.desc(), base_subq.c.id.desc())
        .limit(1)
        .subquery()
    )
    return (
        select(
            aggregate_subq.c.total_findings,
            aggregate_subq.c.blocking_findings,
            top_blocking_subq.c.finding_id,
            top_blocking_subq.c.finding_type,
            top_blocking_subq.c.security_id,
            top_blocking_subq.c.transaction_id,
        )
        .select_from(aggregate_subq)
        .outerjoin(top_blocking_subq, true())
    )


def reconciliation_finding_summary_from_row(row) -> ReconciliationFindingSummary:
    return ReconciliationFindingSummary(
        total_findings=int(row.total_findings or 0),
        blocking_findings=int(row.blocking_findings or 0),
        top_blocking_finding_id=row.finding_id,
        top_blocking_finding_type=row.finding_type,
        top_blocking_finding_security_id=normalize_security_id(row.security_id),
        top_blocking_finding_transaction_id=row.transaction_id,
    )
