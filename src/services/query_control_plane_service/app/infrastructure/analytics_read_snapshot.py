"""Request-owned SQL read snapshot, separate from durable export writes."""

from collections.abc import AsyncIterator

from portfolio_common import db as database_provider
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def get_analytics_read_session() -> AsyncIterator[AsyncSession]:
    """Borrow the application pool; own and close only this read transaction/session.

    Establish isolation before the first source read. Export storage uses a separate
    injected write session, so job commits cannot end this acquisition snapshot.
    This is database consistency, not retained provider/source-cut authority.
    """
    async with database_provider.AsyncSessionLocal() as session:
        await session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
        yield session
