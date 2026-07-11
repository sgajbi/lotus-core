"""SQLAlchemy unit-of-work adapter for analytics export lifecycle transitions."""

from __future__ import annotations

from typing import AsyncContextManager, cast

from sqlalchemy.ext.asyncio import AsyncSession


class SqlAlchemyAnalyticsUnitOfWork:
    """Delegate transaction ownership to the request-scoped async session."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def transaction(self) -> AsyncContextManager[None]:
        return cast(AsyncContextManager[None], self._session.begin())
