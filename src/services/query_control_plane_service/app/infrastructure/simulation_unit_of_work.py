"""SQLAlchemy unit of work for generic simulation mutations."""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(slots=True)
class SqlAlchemySimulationUnitOfWork:
    """Commit and roll back the injected SQLAlchemy session."""

    session: AsyncSession

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()
