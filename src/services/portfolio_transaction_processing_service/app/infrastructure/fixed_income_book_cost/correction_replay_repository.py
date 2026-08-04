"""SQL and transactional-outbox adapter for fixed-income correction replay."""

from __future__ import annotations

from datetime import UTC, date, datetime, time

from portfolio_common.database_models import (
    LotDisposalAllocationRecord,
    LotDisposalReceiptRecord,
    Portfolio,
    Transaction,
)
from portfolio_common.event_contracts import (
    FIXED_INCOME_BOOK_COST_DISPOSAL_REPLAY_EVENT_TYPE,
)
from portfolio_common.outbox_repository import OutboxRepository
from sqlalchemy import Select, and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...application.fixed_income_book_cost import (
    fixed_income_book_cost_disposal_replay_event,
)
from ...domain.fixed_income_book_cost import (
    AffectedLotDisposalReplayAnchor,
    FixedIncomeBookCostCorrectionReplayIntent,
    LotBookCostAuthorityScope,
)


class SqlAlchemyFixedIncomeBookCostCorrectionReplayRepository:
    """Select one deterministic suffix anchor and stage one ordered replay command."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        topic: str,
        outbox_repository: OutboxRepository | None = None,
    ) -> None:
        normalized_topic = topic.strip()
        if not normalized_topic:
            raise ValueError("fixed-income correction replay topic must be nonblank")
        self._session = session
        self._topic = normalized_topic
        self._outbox = outbox_repository or OutboxRepository(session)

    async def find_earliest_affected_disposal(
        self,
        scope: LotBookCostAuthorityScope,
        *,
        effective_date: date,
    ) -> AffectedLotDisposalReplayAnchor | None:
        """Return the earliest latest-active disposal allocation for the exact source lot."""

        row = (
            await self._session.execute(
                _earliest_affected_disposal_statement(
                    scope,
                    effective_date=effective_date,
                )
            )
        ).first()
        if row is None:
            return None
        return AffectedLotDisposalReplayAnchor(
            transaction_id=str(row.transaction_id),
            transaction_timestamp=row.transaction_date,
        )

    async def stage_replay_intent(
        self,
        intent: FixedIncomeBookCostCorrectionReplayIntent,
        *,
        correlation_id: str | None,
        traceparent: str | None,
    ) -> None:
        """Write one strict command to the caller-owned transactional outbox."""

        event = fixed_income_book_cost_disposal_replay_event(
            intent,
            correlation_id=correlation_id,
            traceparent=traceparent,
        )
        await self._outbox.create_outbox_event(
            aggregate_type="FixedIncomeBookCostCorrectionReplay",
            aggregate_id=intent.command_id,
            event_type=FIXED_INCOME_BOOK_COST_DISPOSAL_REPLAY_EVENT_TYPE,
            payload=event.model_dump(mode="json"),
            topic=self._topic,
            partition_key=event.partition_key,
            correlation_id=event.correlation_id,
            traceparent=event.traceparent,
        )


def _earliest_affected_disposal_statement(
    scope: LotBookCostAuthorityScope,
    *,
    effective_date: date,
) -> Select[tuple[str, datetime]]:
    if not isinstance(scope, LotBookCostAuthorityScope):
        raise TypeError("scope must be a LotBookCostAuthorityScope")
    if type(effective_date) is not date:
        raise TypeError("effective_date must be a date")
    receipt = LotDisposalReceiptRecord
    allocation = LotDisposalAllocationRecord
    transaction = Transaction
    portfolio = Portfolio
    latest_receipt = (
        select(
            receipt.disposal_transaction_id.label("disposal_transaction_id"),
            func.max(receipt.receipt_version).label("receipt_version"),
        )
        .group_by(receipt.disposal_transaction_id)
        .subquery("latest_lot_disposal_receipt")
    )
    boundary = datetime.combine(effective_date, time.min, tzinfo=UTC)
    return (
        select(
            transaction.transaction_id.label("transaction_id"),
            transaction.transaction_date.label("transaction_date"),
        )
        .select_from(allocation)
        .join(
            receipt,
            and_(
                receipt.receipt_id == allocation.receipt_id,
                receipt.receipt_version == allocation.receipt_version,
                receipt.portfolio_id == allocation.portfolio_id,
                receipt.security_id == allocation.security_id,
            ),
        )
        .join(
            latest_receipt,
            and_(
                latest_receipt.c.disposal_transaction_id == receipt.disposal_transaction_id,
                latest_receipt.c.receipt_version == receipt.receipt_version,
            ),
        )
        .join(
            transaction,
            transaction.transaction_id == receipt.disposal_transaction_id,
        )
        .join(portfolio, portfolio.portfolio_id == transaction.portfolio_id)
        .where(
            portfolio.tenant_id == scope.tenant_id,
            portfolio.legal_book_id == scope.legal_book_id,
            transaction.portfolio_id == scope.portfolio_id,
            transaction.security_id == scope.security_id,
            transaction.transaction_date >= boundary,
            receipt.status == "ACTIVE",
            allocation.portfolio_id == scope.portfolio_id,
            allocation.security_id == scope.security_id,
            allocation.source_lot_id == scope.lot_id,
        )
        .order_by(
            transaction.transaction_date.asc(),
            transaction.transaction_id.asc(),
        )
        .limit(1)
    )
