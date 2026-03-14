from datetime import date, datetime, timezone
from unittest.mock import patch

import pytest
from portfolio_common.database_models import (
    BusinessDate,
    FinancialReconciliationFinding,
    FinancialReconciliationRun,
    PipelineStageState,
    Portfolio,
    PortfolioAggregationJob,
    PortfolioValuationJob,
    PositionState,
)
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.pipeline_orchestrator_service.app.repositories.pipeline_stage_repository import (
    PipelineStageRepository,
)
from src.services.query_service.app.services import operations_service as operations_service_module
from src.services.query_service.app.services.operations_service import OperationsService

pytestmark = pytest.mark.asyncio

FIXED_GENERATED_AT = datetime(2025, 8, 30, 12, 0, tzinfo=timezone.utc)


class _FixedDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        if tz is None:
            return FIXED_GENERATED_AT.replace(tzinfo=None)
        return FIXED_GENERATED_AT.astimezone(tz)


async def test_support_overview_returns_coherent_snapshot_under_control_churn(
    clean_db, async_db_session: AsyncSession
):
    control_transaction_id = PipelineStageRepository.build_portfolio_stage_key(
        stage_name="FINANCIAL_RECONCILIATION",
        portfolio_id="P1",
        business_date=date(2025, 8, 30),
    )
    late_control_transaction_id = PipelineStageRepository.build_portfolio_stage_key(
        stage_name="FINANCIAL_RECONCILIATION",
        portfolio_id="P1",
        business_date=date(2025, 8, 31),
    )

    older_control = PipelineStageState(
        stage_name="FINANCIAL_RECONCILIATION",
        transaction_id=control_transaction_id,
        portfolio_id="P1",
        security_id=None,
        business_date=date(2025, 8, 30),
        epoch=2,
        status="COMPLETED",
        cost_event_seen=False,
        cashflow_event_seen=False,
        ready_emitted_at=datetime(2025, 8, 30, 10, 5, tzinfo=timezone.utc),
        last_source_event_type="financial_reconciliation_completed",
        created_at=datetime(2025, 8, 30, 10, 0, tzinfo=timezone.utc),
        updated_at=datetime(2025, 8, 30, 11, 0, tzinfo=timezone.utc),
    )
    late_control = PipelineStageState(
        stage_name="FINANCIAL_RECONCILIATION",
        transaction_id=late_control_transaction_id,
        portfolio_id="P1",
        security_id=None,
        business_date=date(2025, 8, 31),
        epoch=3,
        status="FAILED",
        cost_event_seen=False,
        cashflow_event_seen=False,
        ready_emitted_at=None,
        last_source_event_type="financial_reconciliation_completed",
        created_at=datetime(2025, 8, 30, 12, 30, tzinfo=timezone.utc),
        updated_at=datetime(2025, 8, 30, 12, 30, tzinfo=timezone.utc),
    )

    async_db_session.add_all(
        [
            Portfolio(
                portfolio_id="P1",
                base_currency="USD",
                open_date=date(2025, 1, 1),
                risk_exposure="MODERATE",
                investment_time_horizon="MEDIUM_TERM",
                portfolio_type="DISCRETIONARY",
                booking_center_code="SG",
                client_id="CLIENT-P1",
                is_leverage_allowed=False,
                status="ACTIVE",
            ),
            BusinessDate(
                date=date(2025, 8, 30),
                created_at=datetime(2025, 8, 30, 9, 0, tzinfo=timezone.utc),
            ),
            BusinessDate(
                date=date(2025, 8, 31),
                created_at=datetime(2025, 8, 30, 12, 30, tzinfo=timezone.utc),
            ),
            PositionState(
                portfolio_id="P1",
                security_id="SEC-OLD",
                epoch=2,
                watermark_date=date(2025, 8, 29),
                status="CURRENT",
                created_at=datetime(2025, 8, 30, 9, 0, tzinfo=timezone.utc),
                updated_at=datetime(2025, 8, 30, 9, 0, tzinfo=timezone.utc),
            ),
            PositionState(
                portfolio_id="P1",
                security_id="SEC-LATE",
                epoch=5,
                watermark_date=date(2025, 8, 31),
                status="CURRENT",
                created_at=datetime(2025, 8, 30, 12, 30, tzinfo=timezone.utc),
                updated_at=datetime(2025, 8, 30, 12, 30, tzinfo=timezone.utc),
            ),
            older_control,
            late_control,
            FinancialReconciliationRun(
                run_id="recon-old",
                reconciliation_type="transaction_cashflow",
                portfolio_id="P1",
                business_date=date(2025, 8, 30),
                epoch=2,
                status="COMPLETED",
                requested_by="pipeline_orchestrator_service",
                dedupe_key="recon:transaction_cashflow:P1:2025-08-30:2:old",
                correlation_id="corr-recon-old",
                started_at=datetime(2025, 8, 30, 10, 30, tzinfo=timezone.utc),
                completed_at=datetime(2025, 8, 30, 10, 40, tzinfo=timezone.utc),
                created_at=datetime(2025, 8, 30, 10, 30, tzinfo=timezone.utc),
                updated_at=datetime(2025, 8, 30, 10, 45, tzinfo=timezone.utc),
            ),
            FinancialReconciliationRun(
                run_id="recon-late",
                reconciliation_type="transaction_cashflow",
                portfolio_id="P1",
                business_date=date(2025, 8, 30),
                epoch=2,
                status="FAILED",
                requested_by="pipeline_orchestrator_service",
                dedupe_key="recon:transaction_cashflow:P1:2025-08-30:2:late",
                correlation_id="corr-recon-late",
                failure_reason="late failure",
                started_at=datetime(2025, 8, 30, 11, 30, tzinfo=timezone.utc),
                created_at=datetime(2025, 8, 30, 11, 30, tzinfo=timezone.utc),
                updated_at=datetime(2025, 8, 30, 11, 30, tzinfo=timezone.utc),
            ),
        ]
    )
    await async_db_session.commit()
    async_db_session.add_all(
        [
            FinancialReconciliationFinding(
                finding_id="finding-old",
                run_id="recon-old",
                reconciliation_type="transaction_cashflow",
                finding_type="missing_cashflow",
                severity="ERROR",
                portfolio_id="P1",
                security_id="SEC-OLD",
                transaction_id="TXN-OLD",
                business_date=date(2025, 8, 30),
                epoch=2,
                detail={"message": "older finding"},
                created_at=datetime(2025, 8, 30, 10, 50, tzinfo=timezone.utc),
            ),
            FinancialReconciliationFinding(
                finding_id="finding-late",
                run_id="recon-old",
                reconciliation_type="transaction_cashflow",
                finding_type="late_breakage",
                severity="ERROR",
                portfolio_id="P1",
                security_id="SEC-LATE",
                transaction_id="TXN-LATE",
                business_date=date(2025, 8, 30),
                epoch=2,
                detail={"message": "late finding"},
                created_at=datetime(2025, 8, 30, 11, 40, tzinfo=timezone.utc),
            ),
        ]
    )
    await async_db_session.commit()
    await async_db_session.refresh(older_control)

    service = OperationsService(async_db_session)

    with patch.object(operations_service_module, "datetime", _FixedDateTime):
        response = await service.get_support_overview("P1")

    assert response.generated_at_utc == FIXED_GENERATED_AT
    assert response.business_date == date(2025, 8, 30)
    assert response.current_epoch == 2
    assert response.controls_stage_id == older_control.id
    assert response.controls_business_date == date(2025, 8, 30)
    assert response.controls_epoch == 2
    assert response.controls_status == "COMPLETED"
    assert response.controls_failure_reason is None
    assert response.controls_latest_reconciliation_run_id == "recon-old"
    assert response.controls_latest_reconciliation_status == "COMPLETED"
    assert response.controls_latest_reconciliation_correlation_id == "corr-recon-old"
    assert (
        response.controls_latest_reconciliation_dedupe_key
        == "recon:transaction_cashflow:P1:2025-08-30:2:old"
    )
    assert response.controls_latest_reconciliation_failure_reason is None
    assert response.controls_latest_reconciliation_total_findings == 1
    assert response.controls_latest_reconciliation_blocking_findings == 1
    assert response.controls_latest_blocking_finding_id == "finding-old"
    assert response.controls_latest_blocking_finding_type == "missing_cashflow"
    assert response.controls_latest_blocking_finding_security_id == "SEC-OLD"
    assert response.controls_latest_blocking_finding_transaction_id == "TXN-OLD"


async def test_calculator_slos_returns_coherent_snapshot_under_queue_churn(
    clean_db, async_db_session: AsyncSession
):
    async_db_session.add_all(
        [
            Portfolio(
                portfolio_id="P2",
                base_currency="USD",
                open_date=date(2025, 1, 1),
                risk_exposure="MODERATE",
                investment_time_horizon="MEDIUM_TERM",
                portfolio_type="DISCRETIONARY",
                booking_center_code="SG",
                client_id="CLIENT-P2",
                is_leverage_allowed=False,
                status="ACTIVE",
            ),
            BusinessDate(
                date=date(2025, 8, 30),
                created_at=datetime(2025, 8, 30, 9, 0, tzinfo=timezone.utc),
            ),
            BusinessDate(
                date=date(2025, 8, 31),
                created_at=datetime(2025, 8, 30, 12, 30, tzinfo=timezone.utc),
            ),
            PositionState(
                portfolio_id="P2",
                security_id="SEC-VAL-OLD",
                epoch=2,
                watermark_date=date(2025, 8, 18),
                status="REPROCESSING",
                created_at=datetime(2025, 8, 30, 9, 0, tzinfo=timezone.utc),
                updated_at=datetime(2025, 8, 30, 10, 0, tzinfo=timezone.utc),
            ),
            PositionState(
                portfolio_id="P2",
                security_id="SEC-VAL-LATE",
                epoch=5,
                watermark_date=date(2025, 8, 31),
                status="REPROCESSING",
                created_at=datetime(2025, 8, 30, 12, 30, tzinfo=timezone.utc),
                updated_at=datetime(2025, 8, 30, 12, 30, tzinfo=timezone.utc),
            ),
            PortfolioValuationJob(
                portfolio_id="P2",
                security_id="SEC-VAL-OLD",
                valuation_date=date(2025, 8, 20),
                epoch=2,
                status="PENDING",
                correlation_id="corr-val-old",
                created_at=datetime(2025, 8, 30, 9, 30, tzinfo=timezone.utc),
                updated_at=datetime(2025, 8, 30, 10, 0, tzinfo=timezone.utc),
            ),
            PortfolioValuationJob(
                portfolio_id="P2",
                security_id="SEC-VAL-LATE",
                valuation_date=date(2025, 8, 31),
                epoch=5,
                status="FAILED",
                correlation_id="corr-val-late",
                failure_reason="late valuation failure",
                created_at=datetime(2025, 8, 30, 12, 30, tzinfo=timezone.utc),
                updated_at=datetime(2025, 8, 30, 12, 30, tzinfo=timezone.utc),
            ),
            PortfolioAggregationJob(
                portfolio_id="P2",
                aggregation_date=date(2025, 8, 21),
                status="PROCESSING",
                correlation_id="corr-agg-old",
                created_at=datetime(2025, 8, 30, 9, 45, tzinfo=timezone.utc),
                updated_at=datetime(2025, 8, 30, 10, 0, tzinfo=timezone.utc),
            ),
            PortfolioAggregationJob(
                portfolio_id="P2",
                aggregation_date=date(2025, 8, 31),
                status="FAILED",
                correlation_id="corr-agg-late",
                failure_reason="late aggregation failure",
                created_at=datetime(2025, 8, 30, 12, 30, tzinfo=timezone.utc),
                updated_at=datetime(2025, 8, 30, 12, 30, tzinfo=timezone.utc),
            ),
        ]
    )
    await async_db_session.commit()

    service = OperationsService(async_db_session)

    with patch.object(operations_service_module, "datetime", _FixedDateTime):
        response = await service.get_calculator_slos("P2")

    assert response.generated_at_utc == FIXED_GENERATED_AT
    assert response.business_date == date(2025, 8, 30)
    assert response.valuation.pending_jobs == 1
    assert response.valuation.processing_jobs == 0
    assert response.valuation.failed_jobs == 0
    assert response.valuation.failed_jobs_within_window == 0
    assert response.valuation.oldest_open_job_date == date(2025, 8, 20)
    assert response.valuation.oldest_open_job_correlation_id == "corr-val-old"
    assert response.valuation.backlog_age_days == 10
    assert response.aggregation.pending_jobs == 1
    assert response.aggregation.processing_jobs == 1
    assert response.aggregation.failed_jobs == 0
    assert response.aggregation.failed_jobs_within_window == 0
    assert response.aggregation.oldest_open_job_date == date(2025, 8, 21)
    assert response.aggregation.oldest_open_job_correlation_id == "corr-agg-old"
    assert response.aggregation.backlog_age_days == 9
    assert response.reprocessing.active_reprocessing_keys == 1
    assert response.reprocessing.stale_reprocessing_keys == 1
    assert response.reprocessing.oldest_reprocessing_watermark_date == date(2025, 8, 18)
    assert response.reprocessing.oldest_reprocessing_security_id == "SEC-VAL-OLD"
    assert response.reprocessing.oldest_reprocessing_epoch == 2
    assert response.reprocessing.backlog_age_days == 12


async def test_reconciliation_runs_return_coherent_snapshot_under_run_churn(
    clean_db, async_db_session: AsyncSession
):
    async_db_session.add(
        Portfolio(
            portfolio_id="P3",
            base_currency="USD",
            open_date=date(2025, 1, 1),
            risk_exposure="MODERATE",
            investment_time_horizon="MEDIUM_TERM",
            portfolio_type="DISCRETIONARY",
            booking_center_code="SG",
            client_id="CLIENT-P3",
            is_leverage_allowed=False,
            status="ACTIVE",
        )
    )
    async_db_session.add_all(
        [
            FinancialReconciliationRun(
                run_id="recon-run-old",
                reconciliation_type="transaction_cashflow",
                portfolio_id="P3",
                business_date=date(2025, 8, 30),
                epoch=2,
                status="COMPLETED",
                requested_by="pipeline_orchestrator_service",
                dedupe_key="recon:transaction_cashflow:P3:2025-08-30:2:old",
                correlation_id="corr-recon-run-old",
                started_at=datetime(2025, 8, 30, 10, 30, tzinfo=timezone.utc),
                completed_at=datetime(2025, 8, 30, 10, 40, tzinfo=timezone.utc),
                created_at=datetime(2025, 8, 30, 10, 30, tzinfo=timezone.utc),
                updated_at=datetime(2025, 8, 30, 10, 45, tzinfo=timezone.utc),
            ),
            FinancialReconciliationRun(
                run_id="recon-run-late",
                reconciliation_type="transaction_cashflow",
                portfolio_id="P3",
                business_date=date(2025, 8, 30),
                epoch=2,
                status="FAILED",
                requested_by="pipeline_orchestrator_service",
                dedupe_key="recon:transaction_cashflow:P3:2025-08-30:2:late",
                correlation_id="corr-recon-run-late",
                failure_reason="late reconciliation failure",
                started_at=datetime(2025, 8, 30, 12, 30, tzinfo=timezone.utc),
                created_at=datetime(2025, 8, 30, 12, 30, tzinfo=timezone.utc),
                updated_at=datetime(2025, 8, 30, 12, 30, tzinfo=timezone.utc),
            ),
        ]
    )
    await async_db_session.commit()

    service = OperationsService(async_db_session)

    with patch.object(operations_service_module, "datetime", _FixedDateTime):
        response = await service.get_reconciliation_runs("P3", skip=0, limit=10)

    assert response.generated_at_utc == FIXED_GENERATED_AT
    assert response.total == 1
    assert len(response.items) == 1
    assert response.items[0].run_id == "recon-run-old"
    assert response.items[0].status == "COMPLETED"
    assert response.items[0].correlation_id == "corr-recon-run-old"
    assert response.items[0].failure_reason is None
    assert response.items[0].operational_state == "COMPLETED"


async def test_reconciliation_findings_return_coherent_snapshot_under_finding_churn(
    clean_db, async_db_session: AsyncSession
):
    async_db_session.add(
        Portfolio(
            portfolio_id="P4",
            base_currency="USD",
            open_date=date(2025, 1, 1),
            risk_exposure="MODERATE",
            investment_time_horizon="MEDIUM_TERM",
            portfolio_type="DISCRETIONARY",
            booking_center_code="SG",
            client_id="CLIENT-P4",
            is_leverage_allowed=False,
            status="ACTIVE",
        )
    )
    async_db_session.add(
        FinancialReconciliationRun(
            run_id="recon-findings-old",
            reconciliation_type="transaction_cashflow",
            portfolio_id="P4",
            business_date=date(2025, 8, 30),
            epoch=2,
            status="FAILED",
            requested_by="pipeline_orchestrator_service",
            dedupe_key="recon:transaction_cashflow:P4:2025-08-30:2",
            correlation_id="corr-recon-findings-old",
            failure_reason="older run failure",
            started_at=datetime(2025, 8, 30, 10, 30, tzinfo=timezone.utc),
            created_at=datetime(2025, 8, 30, 10, 30, tzinfo=timezone.utc),
            updated_at=datetime(2025, 8, 30, 11, 0, tzinfo=timezone.utc),
        )
    )
    await async_db_session.commit()
    async_db_session.add_all(
        [
            FinancialReconciliationFinding(
                finding_id="finding-visible",
                run_id="recon-findings-old",
                reconciliation_type="transaction_cashflow",
                finding_type="missing_cashflow",
                severity="ERROR",
                portfolio_id="P4",
                security_id="SEC-VISIBLE",
                transaction_id="TXN-VISIBLE",
                business_date=date(2025, 8, 30),
                epoch=2,
                detail={"message": "visible finding"},
                created_at=datetime(2025, 8, 30, 11, 10, tzinfo=timezone.utc),
            ),
            FinancialReconciliationFinding(
                finding_id="finding-hidden",
                run_id="recon-findings-old",
                reconciliation_type="transaction_cashflow",
                finding_type="late_breakage",
                severity="ERROR",
                portfolio_id="P4",
                security_id="SEC-HIDDEN",
                transaction_id="TXN-HIDDEN",
                business_date=date(2025, 8, 30),
                epoch=2,
                detail={"message": "hidden finding"},
                created_at=datetime(2025, 8, 30, 12, 30, tzinfo=timezone.utc),
            ),
        ]
    )
    await async_db_session.commit()

    service = OperationsService(async_db_session)

    with patch.object(operations_service_module, "datetime", _FixedDateTime):
        response = await service.get_reconciliation_findings("P4", "recon-findings-old", limit=20)

    assert response.generated_at_utc == FIXED_GENERATED_AT
    assert response.total == 1
    assert len(response.items) == 1
    assert response.items[0].finding_id == "finding-visible"
    assert response.items[0].security_id == "SEC-VISIBLE"
    assert response.items[0].transaction_id == "TXN-VISIBLE"
    assert response.items[0].is_blocking is True
    assert response.items[0].operational_state == "BLOCKING"
