"""Persist position history while keeping SQLAlchemy rows behind a domain port."""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Callable, Sequence
from dataclasses import replace
from datetime import UTC, date, datetime, time
from decimal import Decimal
from time import monotonic
from typing import cast

from portfolio_common.database_models import (
    DailyPositionSnapshot,
    Portfolio,
    PositionHistory,
    PositionState,
    Transaction,
)
from portfolio_common.domain.calculation_lineage import calculation_lineage_from_payload
from portfolio_common.domain.transaction.type_registry import get_transaction_type_definition
from portfolio_common.identifiers import normalize_lookup_identifier
from portfolio_common.monitoring import observe_position_history_replay_lock_wait
from portfolio_common.utils import async_timed
from sqlalchemy import delete, func, select, text, true
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, joinedload

from ...domain.cost_basis.calculation.lot_restatement import LotRestatement
from ...domain.position.history import PositionHistoryRecord
from ...domain.transaction.booked import BookedTransaction
from ...domain.transaction.corporate_action.classification import (
    SAME_INSTRUMENT_CORPORATE_ACTION_TYPES,
    normalize_corporate_action_transaction_type,
)
from ...domain.transaction.semantic_identity import build_transaction_semantic_identity
from ...ports.position_history import (
    AdmittedPositionCorrectionGroup,
    MaterializedPositionReceipt,
    PositionMaterializationProgress,
    PositionReplayWindow,
)
from ..cost_basis.transaction_repository import (
    load_derived_financial_transactions,
    project_derived_financial_transaction,
)

logger = logging.getLogger(__name__)


def _position_history_replay_lock_key(portfolio_id: str, security_id: str, epoch: int) -> int:
    normalized_portfolio_id = normalize_lookup_identifier(portfolio_id)
    normalized_security_id = normalize_lookup_identifier(security_id)
    lock_scope = (
        f"position-history-replay:{normalized_portfolio_id}:{normalized_security_id}:{epoch}"
    )
    digest = hashlib.blake2b(lock_scope.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, byteorder="big", signed=True)


class SqlAlchemyPositionHistoryRepository:
    """Implement position-history persistence in the caller-owned SQL transaction."""

    def __init__(self, session: AsyncSession, *, clock: Callable[[], float] = monotonic) -> None:
        self._session = session
        self._clock = clock

    @async_timed(repository="PositionRepository", method="acquire_position_history_replay_lock")
    async def acquire_replay_lock(self, *, portfolio_id: str, security_id: str, epoch: int) -> None:
        """Serialize destructive replay for one normalized position key and epoch."""
        lock_key = _position_history_replay_lock_key(portfolio_id, security_id, epoch)
        started_at = self._clock()
        try:
            await self._session.execute(
                text("SELECT pg_advisory_xact_lock(:lock_key)").bindparams(lock_key=lock_key)
            )
        except BaseException:
            wait_seconds = max(0.0, self._clock() - started_at)
            observe_position_history_replay_lock_wait(
                outcome="failed",
                seconds=wait_seconds,
            )
            logger.warning(
                "Position history replay lock acquisition failed.",
                extra={
                    "portfolio_id": normalize_lookup_identifier(portfolio_id),
                    "security_id": normalize_lookup_identifier(security_id),
                    "epoch": epoch,
                    "lock_wait_seconds": wait_seconds,
                },
                exc_info=True,
            )
            raise
        wait_seconds = max(0.0, self._clock() - started_at)
        observe_position_history_replay_lock_wait(
            outcome="acquired",
            seconds=wait_seconds,
        )
        logger.debug(
            "Position history replay lock acquired.",
            extra={
                "portfolio_id": normalize_lookup_identifier(portfolio_id),
                "security_id": normalize_lookup_identifier(security_id),
                "epoch": epoch,
                "lock_wait_seconds": wait_seconds,
            },
        )

    @async_timed(repository="PositionRepository", method="load_materialization_progress")
    async def load_materialization_progress(
        self, *, portfolio_id: str, security_id: str, epoch: int
    ) -> PositionMaterializationProgress:
        """Load both epoch progress boundaries in one database round trip."""
        normalized_portfolio_id = normalize_lookup_identifier(portfolio_id)
        normalized_security_id = normalize_lookup_identifier(security_id)
        latest_history_date = (
            select(func.max(PositionHistory.position_date))
            .where(
                func.trim(PositionHistory.portfolio_id) == normalized_portfolio_id,
                func.trim(PositionHistory.security_id) == normalized_security_id,
                PositionHistory.epoch == epoch,
            )
            .scalar_subquery()
        )
        latest_completed_snapshot_date = (
            select(func.max(DailyPositionSnapshot.date))
            .where(
                func.trim(DailyPositionSnapshot.portfolio_id) == normalized_portfolio_id,
                func.trim(DailyPositionSnapshot.security_id) == normalized_security_id,
                DailyPositionSnapshot.epoch == epoch,
            )
            .scalar_subquery()
        )
        statement = select(
            latest_history_date.label("latest_history_date"),
            latest_completed_snapshot_date.label("latest_completed_snapshot_date"),
        )
        result = await self._session.execute(statement)
        history_date, snapshot_date = result.one()
        return PositionMaterializationProgress(
            latest_history_date=cast(date | None, history_date),
            latest_completed_snapshot_date=cast(date | None, snapshot_date),
        )

    async def load_materialized_receipt(
        self, transaction: BookedTransaction, *, expected_epoch: int
    ) -> MaterializedPositionReceipt | None:
        """Retain owned portfolio, exact state and history locks in this UOW."""
        if not transaction.tenant_id:
            return None
        owner = (
            await self._session.execute(
                select(Portfolio.tenant_id)
                .where(
                    func.trim(Portfolio.portfolio_id)
                    == normalize_lookup_identifier(transaction.portfolio_id),
                    Portfolio.tenant_id == transaction.tenant_id,
                )
                .with_for_update(of=Portfolio)
            )
        ).scalar_one_or_none()
        if owner is None:
            return None
        state_epoch = (
            await self._session.execute(
                select(PositionState.epoch)
                .where(
                    func.trim(PositionState.portfolio_id)
                    == normalize_lookup_identifier(transaction.portfolio_id),
                    func.trim(PositionState.security_id)
                    == normalize_lookup_identifier(transaction.security_id),
                    PositionState.epoch == expected_epoch,
                )
                .with_for_update(of=PositionState)
            )
        ).scalar_one_or_none()
        if state_epoch is None:
            return None
        await self.acquire_replay_lock(
            portfolio_id=transaction.portfolio_id,
            security_id=transaction.security_id,
            epoch=state_epoch,
        )
        row = (
            (
                await self._session.execute(
                    select(PositionHistory)
                    .where(
                        func.trim(PositionHistory.portfolio_id)
                        == normalize_lookup_identifier(transaction.portfolio_id),
                        func.trim(PositionHistory.security_id)
                        == normalize_lookup_identifier(transaction.security_id),
                        func.trim(PositionHistory.transaction_id)
                        == normalize_lookup_identifier(transaction.transaction_id),
                        PositionHistory.epoch == state_epoch,
                        PositionHistory.position_date == transaction.transaction_date.date(),
                    )
                    .with_for_update(read=True, of=PositionHistory)
                )
            )
            .scalars()
            .one_or_none()
        )
        if row is None or row.quantity is None:
            return None
        return MaterializedPositionReceipt(
            tenant_id=str(owner),
            portfolio_id=str(row.portfolio_id),
            security_id=str(row.security_id),
            transaction_id=str(row.transaction_id),
            epoch=int(row.epoch),
            quantity=Decimal(row.quantity),
        )

    @async_timed(repository="PositionRepository", method="get_all_transactions_for_security")
    async def list_all_transactions(
        self,
        *,
        portfolio_id: str,
        security_id: str,
        admitted_correction: AdmittedPositionCorrectionGroup | None = None,
    ) -> tuple[BookedTransaction, ...]:
        """Return every booked transaction for one position key."""
        statement = (
            select(Transaction, Portfolio.tenant_id, Portfolio.cost_basis_method)
            .join(Portfolio, Portfolio.portfolio_id == Transaction.portfolio_id)
            .options(joinedload(Transaction.costs))
            .where(
                func.trim(Transaction.portfolio_id) == normalize_lookup_identifier(portfolio_id),
                func.trim(Transaction.security_id) == normalize_lookup_identifier(security_id),
            )
            .order_by(Transaction.transaction_date.asc(), Transaction.transaction_id.asc())
        )
        result = await self._session.execute(statement)
        return await self._project_replay_transactions(
            result.unique().all(), admitted_correction=admitted_correction
        )

    @async_timed(repository="PositionRepository", method="load_position_replay_window")
    async def load_replay_window(
        self,
        *,
        portfolio_id: str,
        security_id: str,
        position_date: date,
        epoch: int,
        admitted_correction: AdmittedPositionCorrectionGroup | None = None,
    ) -> PositionReplayWindow:
        """Load the prior anchor and ordered replay transactions in one query."""
        if admitted_correction is not None and admitted_correction.replay_epoch != epoch:
            raise ValueError("Admitted position correction has a conflicting replay epoch")
        normalized_portfolio_id = normalize_lookup_identifier(portfolio_id)
        normalized_security_id = normalize_lookup_identifier(security_id)
        anchor_cte = (
            select(PositionHistory)
            .where(
                func.trim(PositionHistory.portfolio_id) == normalized_portfolio_id,
                func.trim(PositionHistory.security_id) == normalized_security_id,
                PositionHistory.position_date < position_date,
                PositionHistory.epoch == epoch,
            )
            .order_by(PositionHistory.position_date.desc(), PositionHistory.id.desc())
            .limit(1)
            .cte("position_replay_anchor")
        )
        anchor = aliased(PositionHistory, anchor_cte)
        statement = (
            select(Transaction, anchor, Portfolio.tenant_id, Portfolio.cost_basis_method)
            .select_from(Transaction)
            .join(Portfolio, Portfolio.portfolio_id == Transaction.portfolio_id)
            .outerjoin(anchor, true())
            .options(joinedload(Transaction.costs))
            .where(
                func.trim(Transaction.portfolio_id) == normalized_portfolio_id,
                func.trim(Transaction.security_id) == normalized_security_id,
                Transaction.transaction_date
                >= datetime.combine(position_date, time.min, tzinfo=UTC),
            )
            .order_by(Transaction.transaction_date.asc(), Transaction.transaction_id.asc())
        )
        rows = (await self._session.execute(statement)).unique().all()
        anchor_row = rows[0][1] if rows else None
        return PositionReplayWindow(
            anchor=(_to_position_history_record(anchor_row) if anchor_row is not None else None),
            transactions=await self._project_replay_transactions(
                [(row, tenant_id, method) for row, _anchor, tenant_id, method in rows],
                admitted_correction=admitted_correction,
            ),
        )

    async def _project_replay_transactions(
        self,
        rows: Sequence[tuple[Transaction, str, str]],
        *,
        admitted_correction: AdmittedPositionCorrectionGroup | None,
    ) -> tuple[BookedTransaction, ...]:
        """Qualify history unchanged; admit only persisted exact cost-result members."""
        if admitted_correction is None:
            return await load_derived_financial_transactions(self._session, rows)
        active = admitted_correction.active_transaction_id
        if active is None or sum(entry[0].transaction_id == active for entry in rows) != 1:
            raise ValueError("Admitted position group requires one exact persisted active row")
        members = {member.transaction_id: member for member in admitted_correction.members}
        admitted_rows = [entry for entry in rows if entry[0].transaction_id in members]
        identifiers = [entry[0].transaction_id for entry in admitted_rows]
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("Admitted position group has duplicate persisted members")
        for row, tenant, method in admitted_rows:
            self._validate_admitted_effect(
                row,
                tenant,
                method,
                members[row.transaction_id],
                admitted_tenant=admitted_correction.root_transaction.tenant_id,
            )
        historical = iter(
            await load_derived_financial_transactions(
                self._session,
                [entry for entry in rows if entry[0].transaction_id not in members],
            )
        )
        return tuple(
            members[entry[0].transaction_id]
            if entry[0].transaction_id in members
            else next(historical)
            for entry in rows
        )

    @staticmethod
    def _validate_admitted_effect(
        row: Transaction,
        tenant: str,
        method: str,
        current: BookedTransaction,
        *,
        admitted_tenant: str | None,
    ) -> None:
        if (tenant, row.portfolio_id, row.security_id) != (
            admitted_tenant,
            current.portfolio_id,
            current.security_id,
        ):
            raise ValueError("Admitted position correction has conflicting source scope")
        projected = project_derived_financial_transaction(
            row,
            tenant_id=tenant,
            cost_basis_method=method,
            qualified_fees={
                name: getattr(current, name)
                for name in (
                    "brokerage",
                    "stamp_duty",
                    "exchange_fee",
                    "gst",
                    "other_fees",
                    "trade_fee",
                )
            },
        )
        # ORM source has no epoch column; retain the admitted command's source cut.
        # The distinct replay epoch remains fenced by the application and window loader.
        projected = replace(projected, epoch=current.epoch, tenant_id=current.tenant_id)
        if build_transaction_semantic_identity(projected) != build_transaction_semantic_identity(
            current
        ):
            raise ValueError("Admitted position correction has conflicting material identity")
        # Material identity already checks effective generated booking defaults. Compare
        # every remaining field, including calculation output and lineage, exactly.
        if replace(
            projected,
            created_at=current.created_at,
            external_cash_transaction_id=current.external_cash_transaction_id,
            cash_entry_mode=current.cash_entry_mode,
            calculation_policy_id=current.calculation_policy_id,
            calculation_policy_version=current.calculation_policy_version,
            economic_event_id=current.economic_event_id,
            linked_transaction_group_id=current.linked_transaction_group_id,
        ) != replace(current, lot_restatement=None):
            raise ValueError("Admitted position correction has conflicting calculated effects")
        if current.lot_restatement is not None:
            context = current.lot_restatement
            if set(context) != {
                "quantity_before",
                "quantity_after",
                "factor_numerator",
                "factor_denominator",
            }:
                raise ValueError("Admitted position correction has invalid restatement keys")
            if any(
                not isinstance(value, Decimal) or not value.is_finite()
                for value in context.values()
            ):
                raise ValueError("Admitted position correction has invalid restatement quantities")
            transaction_type = normalize_corporate_action_transaction_type(current.transaction_type)
            definition = get_transaction_type_definition(transaction_type)
            if transaction_type not in SAME_INSTRUMENT_CORPORATE_ACTION_TYPES or definition is None:
                raise ValueError("Admitted position correction has unrelated restatement context")
            restatement = LotRestatement.from_signed_delta(
                quantity_before=context["quantity_before"],
                signed_quantity_delta=(
                    -current.quantity
                    if definition.position_effect == "decrease"
                    else current.quantity
                ),
            )
            if context != restatement.lineage_payload():
                raise ValueError("Admitted position correction has conflicting restatement ratio")

    @async_timed(repository="PositionRepository", method="delete_positions_from")
    async def delete_records_from(
        self,
        *,
        portfolio_id: str,
        security_id: str,
        position_date: date,
        epoch: int,
    ) -> int:
        """Delete stale records in the caller-owned replay transaction."""
        statement = delete(PositionHistory).where(
            func.trim(PositionHistory.portfolio_id) == normalize_lookup_identifier(portfolio_id),
            func.trim(PositionHistory.security_id) == normalize_lookup_identifier(security_id),
            PositionHistory.position_date >= position_date,
            PositionHistory.epoch == epoch,
        )
        result = await self._session.execute(statement)
        deleted_count = result.rowcount or 0
        logger.debug(
            "Deleted stale position history records.",
            extra={
                "portfolio_id": normalize_lookup_identifier(portfolio_id),
                "security_id": normalize_lookup_identifier(security_id),
                "epoch": epoch,
                "position_date": position_date.isoformat(),
                "deleted_count": deleted_count,
            },
        )
        return int(deleted_count)

    @async_timed(repository="PositionRepository", method="save_positions")
    async def save_records(self, records: tuple[PositionHistoryRecord, ...]) -> None:
        """Stage domain history records for the caller-owned transaction commit."""
        if not records:
            return
        rows = [_to_position_history_row(record) for record in records]
        self._session.add_all(rows)
        logger.debug(
            "Staged position history records.",
            extra={"position_record_count": len(rows)},
        )


def _to_position_history_record(row: PositionHistory) -> PositionHistoryRecord:
    return PositionHistoryRecord(
        portfolio_id=str(row.portfolio_id),
        security_id=str(row.security_id),
        transaction_id=str(row.transaction_id),
        position_date=cast(date, row.position_date),
        quantity=Decimal(row.quantity),
        cost_basis=Decimal(row.cost_basis),
        cost_basis_local=Decimal(row.cost_basis_local or 0),
        epoch=int(row.epoch),
        calculation_lineage=calculation_lineage_from_payload(row.calculation_lineage),
    )


def _to_position_history_row(record: PositionHistoryRecord) -> PositionHistory:
    return PositionHistory(
        portfolio_id=record.portfolio_id,
        security_id=record.security_id,
        transaction_id=record.transaction_id,
        position_date=record.position_date,
        quantity=record.quantity,
        cost_basis=record.cost_basis,
        cost_basis_local=record.cost_basis_local,
        epoch=record.epoch,
        calculation_lineage=(
            record.calculation_lineage.lineage_payload()
            if record.calculation_lineage is not None
            else None
        ),
    )
