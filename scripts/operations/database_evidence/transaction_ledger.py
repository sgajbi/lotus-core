"""Exact production-method plan evidence for transaction-ledger reads."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from src.services.query_service.app.application.transaction_query import (
    TransactionLedgerFilters,
    transaction_ledger_query_spec,
)
from src.services.query_service.app.repositories.transaction_repository import (
    TransactionRepository,
)

from .contract import HotPathPlanResult, HotPathScenario, evaluate_hot_path_plan
from .plan_capture import capture_single_production_statement, explain_captured_statement


async def measure_transaction_ledger_reads(
    session: AsyncSession,
    *,
    portfolio_id: str,
    count_scenario: HotPathScenario,
    page_scenario: HotPathScenario,
) -> tuple[HotPathPlanResult, HotPathPlanResult]:
    """Measure count and first-page SQL emitted by the production repository."""

    filters = TransactionLedgerFilters(portfolio_id=portfolio_id)
    repository = TransactionRepository(session)
    count_statement = await capture_single_production_statement(
        session,
        lambda: repository.get_transactions_count(filters=filters),
    )
    count_plan = await explain_captured_statement(session, count_statement)

    page_statement = await capture_single_production_statement(
        session,
        lambda: repository.get_transactions(
            query_spec=transaction_ledger_query_spec(
                filters=filters,
                sort_by=None,
                sort_order=None,
            ),
            skip=0,
            limit=page_scenario.max_root_actual_rows,
        ),
    )
    page_plan = await explain_captured_statement(session, page_statement)
    return (
        evaluate_hot_path_plan(count_scenario, count_plan),
        evaluate_hot_path_plan(page_scenario, page_plan),
    )
