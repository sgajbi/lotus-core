from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession


class SqlAlchemyUnitOfWork:
    def __init__(self, db: AsyncSession):
        self._db = db

    async def commit(self) -> None:
        await self._db.commit()

    async def rollback(self) -> None:
        await self._db.rollback()

    async def refresh(self, entity: Any) -> None:
        await self._db.refresh(entity)
