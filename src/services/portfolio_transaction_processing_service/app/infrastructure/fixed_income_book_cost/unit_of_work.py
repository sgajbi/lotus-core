"""Atomic SQLAlchemy boundary for fixed-income book-cost authority events."""

from __future__ import annotations

from collections.abc import Callable
from types import TracebackType
from typing import TypeVar

from portfolio_common.config import (
    KAFKA_FIXED_INCOME_BOOK_COST_DISPOSAL_REPLAY_REQUESTED_TOPIC,
)
from sqlalchemy.ext.asyncio import AsyncSession, AsyncSessionTransaction

from ...ports import (
    FixedIncomeBookCostCorrectionReplayPort,
    LotAmortizedCostAuthorityPort,
    LotAmortizedCostProfilePort,
)
from .correction_replay_repository import (
    SqlAlchemyFixedIncomeBookCostCorrectionReplayRepository,
)
from .profile_repository import SqlAlchemyLotAmortizedCostProfileRepository
from .source_authority_repository import SqlAlchemyLotAmortizedCostAuthorityRepository

_AdapterT = TypeVar("_AdapterT")


class SqlAlchemyFixedIncomeBookCostAuthorityUnitOfWork:
    """Build authority and profile adapters over one database transaction."""

    def __init__(self, session_factory: Callable[[], AsyncSession]) -> None:
        self._session_factory = session_factory
        self._session: AsyncSession | None = None
        self._transaction: AsyncSessionTransaction | None = None
        self._committed = False
        self._authority: LotAmortizedCostAuthorityPort | None = None
        self._profiles: LotAmortizedCostProfilePort | None = None
        self._correction_replay: FixedIncomeBookCostCorrectionReplayPort | None = None

    @property
    def authority(self) -> LotAmortizedCostAuthorityPort:
        return _required_adapter(self._authority, "authority")

    @property
    def profiles(self) -> LotAmortizedCostProfilePort:
        return _required_adapter(self._profiles, "profiles")

    @property
    def correction_replay(self) -> FixedIncomeBookCostCorrectionReplayPort:
        return _required_adapter(self._correction_replay, "correction replay")

    async def __aenter__(self) -> SqlAlchemyFixedIncomeBookCostAuthorityUnitOfWork:
        if self._session is not None:
            raise RuntimeError("fixed-income book-cost unit of work cannot be reused")
        session = self._session_factory()
        transaction = session.begin()
        self._session = session
        try:
            await transaction.start()
            self._transaction = transaction
            self._authority = SqlAlchemyLotAmortizedCostAuthorityRepository(session)
            self._profiles = SqlAlchemyLotAmortizedCostProfileRepository(session)
            self._correction_replay = SqlAlchemyFixedIncomeBookCostCorrectionReplayRepository(
                session,
                topic=KAFKA_FIXED_INCOME_BOOK_COST_DISPOSAL_REPLAY_REQUESTED_TOPIC,
            )
        except BaseException:
            if self._transaction is not None:
                await self._transaction.rollback()
            await session.close()
            raise
        return self

    async def __aexit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc_value: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None:
        try:
            if not self._committed and self._transaction is not None:
                await self._transaction.rollback()
        finally:
            if self._session is not None:
                await self._session.close()

    async def commit(self) -> None:
        if self._transaction is None:
            raise RuntimeError("fixed-income book-cost unit of work has not been entered")
        if self._committed:
            raise RuntimeError("fixed-income book-cost unit of work was already committed")
        await self._transaction.commit()
        self._committed = True


def _required_adapter(adapter: _AdapterT | None, name: str) -> _AdapterT:
    if adapter is None:
        raise RuntimeError(f"fixed-income book-cost {name} adapter is not initialized")
    return adapter
