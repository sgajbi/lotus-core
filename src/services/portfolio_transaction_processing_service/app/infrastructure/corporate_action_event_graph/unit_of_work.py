"""Own lightweight atomic persistence for corporate-action parent graphs."""

from __future__ import annotations

from collections.abc import Callable
from types import TracebackType

from sqlalchemy.ext.asyncio import AsyncSession, AsyncSessionTransaction

from ...ports.corporate_action_event_graph import CorporateActionEventGraphPort
from .repository import SqlAlchemyCorporateActionEventGraphRepository


class SqlAlchemyCorporateActionEventGraphUnitOfWork:
    """Create one repository over one caller-visible SQLAlchemy transaction."""

    def __init__(self, session_factory: Callable[[], AsyncSession]) -> None:
        self._session_factory = session_factory
        self._session: AsyncSession | None = None
        self._transaction: AsyncSessionTransaction | None = None
        self._event_graph: CorporateActionEventGraphPort | None = None
        self._committed = False

    @property
    def event_graph(self) -> CorporateActionEventGraphPort:
        if self._event_graph is None:
            raise RuntimeError("Corporate-action event-graph repository is not initialized")
        return self._event_graph

    async def __aenter__(self) -> SqlAlchemyCorporateActionEventGraphUnitOfWork:
        if self._session is not None:
            raise RuntimeError("Corporate-action event-graph unit of work cannot be reused")
        session = self._session_factory()
        transaction = session.begin()
        self._session = session
        try:
            await transaction.start()
            self._transaction = transaction
            self._event_graph = SqlAlchemyCorporateActionEventGraphRepository(session)
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
            raise RuntimeError("Corporate-action event-graph unit of work has not been entered")
        if self._committed:
            raise RuntimeError("Corporate-action event-graph unit of work was already committed")
        await self._transaction.commit()
        self._committed = True
