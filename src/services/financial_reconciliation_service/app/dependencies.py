from __future__ import annotations

from fastapi import Depends
from portfolio_common.db import get_async_db_session
from sqlalchemy.ext.asyncio import AsyncSession

from .application import ReconciliationUseCases
from .repositories import ReconciliationRepository
from .services import ReconciliationService


class AsyncSessionUnitOfWork:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def commit(self) -> None:
        await self._session.commit()


def build_reconciliation_use_cases(db_session: AsyncSession) -> ReconciliationUseCases:
    repository = ReconciliationRepository(db_session)
    return ReconciliationUseCases(
        service=ReconciliationService(repository),
        repository=repository,
        unit_of_work=AsyncSessionUnitOfWork(db_session),
    )


def get_reconciliation_use_cases(
    db_session: AsyncSession = Depends(get_async_db_session),
) -> ReconciliationUseCases:
    return build_reconciliation_use_cases(db_session)
