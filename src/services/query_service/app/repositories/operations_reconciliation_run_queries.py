from __future__ import annotations

from datetime import date, datetime

from portfolio_common.database_models import FinancialReconciliationRun
from sqlalchemy import case


def reconciliation_status_filter(status_column, status: str):
    return status_column == status.strip().upper()


def reconciliation_run_priority(status_column):
    governed_status = status_column
    return case(
        (governed_status.in_(("FAILED", "REQUIRES_REPLAY")), 0),
        (governed_status == "RUNNING", 1),
        else_=9,
    )


def apply_reconciliation_run_time_scope(
    stmt,
    *,
    as_of: datetime | None,
    include_started_as_of: bool,
):
    if as_of is None:
        return stmt
    stmt = stmt.where(FinancialReconciliationRun.updated_at <= as_of)
    if include_started_as_of:
        stmt = stmt.where(FinancialReconciliationRun.started_at <= as_of)
    return stmt


def apply_reconciliation_run_identity_scope(
    stmt,
    *,
    run_id: str | None,
    correlation_id: str | None,
    requested_by: str | None,
    dedupe_key: str | None,
):
    if run_id:
        stmt = stmt.where(FinancialReconciliationRun.run_id == run_id)
    if correlation_id:
        stmt = stmt.where(FinancialReconciliationRun.correlation_id == correlation_id)
    if requested_by:
        stmt = stmt.where(FinancialReconciliationRun.requested_by == requested_by)
    if dedupe_key:
        stmt = stmt.where(FinancialReconciliationRun.dedupe_key == dedupe_key)
    return stmt


def apply_reconciliation_run_attribute_scope(
    stmt,
    *,
    reconciliation_type: str | None,
    business_date: date | None,
    epoch: int | None,
):
    if reconciliation_type:
        stmt = stmt.where(FinancialReconciliationRun.reconciliation_type == reconciliation_type)
    if business_date is not None:
        stmt = stmt.where(FinancialReconciliationRun.business_date == business_date)
    if epoch is not None:
        stmt = stmt.where(FinancialReconciliationRun.epoch == epoch)
    return stmt


def apply_reconciliation_run_scope(
    stmt,
    *,
    portfolio_id: str,
    run_id: str | None = None,
    correlation_id: str | None = None,
    requested_by: str | None = None,
    dedupe_key: str | None = None,
    reconciliation_type: str | None = None,
    business_date: date | None = None,
    epoch: int | None = None,
    status: str | None = None,
    as_of: datetime | None = None,
    include_started_as_of: bool = False,
):
    stmt = stmt.where(FinancialReconciliationRun.portfolio_id == portfolio_id)
    stmt = apply_reconciliation_run_time_scope(
        stmt,
        as_of=as_of,
        include_started_as_of=include_started_as_of,
    )
    stmt = apply_reconciliation_run_identity_scope(
        stmt,
        run_id=run_id,
        correlation_id=correlation_id,
        requested_by=requested_by,
        dedupe_key=dedupe_key,
    )
    stmt = apply_reconciliation_run_attribute_scope(
        stmt,
        reconciliation_type=reconciliation_type,
        business_date=business_date,
        epoch=epoch,
    )
    if status:
        stmt = stmt.where(reconciliation_status_filter(FinancialReconciliationRun.status, status))
    return stmt
