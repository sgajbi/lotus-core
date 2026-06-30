# services/query-service/app/repositories/instrument_repository.py
import logging
from typing import List, Optional

from portfolio_common.database_models import Instrument
from portfolio_common.utils import async_timed
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .identifier_normalization import normalize_security_id

logger = logging.getLogger(__name__)


class InstrumentRepository:
    """
    Handles read-only database queries for instrument data.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    @async_timed(repository="InstrumentRepository", method="get_by_security_ids")
    async def get_by_security_ids(self, security_ids: List[str]) -> List[Instrument]:
        """Fetches multiple instruments by a list of their security_id strings."""
        if not security_ids:
            return []
        normalized_security_ids = list(
            dict.fromkeys(
                normalized
                for security_id in security_ids
                if (normalized := normalize_security_id(security_id))
            )
        )
        if not normalized_security_ids:
            return []
        stmt = select(Instrument).where(
            func.trim(Instrument.security_id).in_(normalized_security_ids)
        )
        result = await self.db.execute(stmt)
        return result.scalars().all()

    def _get_base_query(
        self, security_id: Optional[str] = None, product_type: Optional[str] = None
    ):
        """
        Constructs a base query with all the common filters.
        """
        stmt = select(Instrument)
        if security_id:
            normalized_security_id = normalize_security_id(security_id)
            if normalized_security_id:
                stmt = stmt.where(func.trim(Instrument.security_id) == normalized_security_id)
        if product_type:
            stmt = stmt.filter_by(product_type=product_type)
        return stmt

    async def get_instruments(
        self,
        skip: int,
        limit: int,
        security_id: Optional[str] = None,
        product_type: Optional[str] = None,
    ) -> List[Instrument]:
        """
        Retrieves a paginated list of instruments with optional filters.
        """
        stmt = self._get_base_query(security_id, product_type)
        results = await self.db.execute(
            stmt.order_by(Instrument.name.asc()).offset(skip).limit(limit)
        )
        instruments = results.scalars().all()
        logger.info(f"Found {len(instruments)} instruments with given filters.")
        return instruments

    async def search_instrument_lookup_rows(
        self,
        *,
        product_type: str | None = None,
        q: str | None = None,
        limit: int,
    ) -> list[tuple[str, str]]:
        """Return bounded instrument selector rows."""
        security_id = func.trim(Instrument.security_id)
        stmt = select(security_id, Instrument.name)

        if product_type:
            stmt = stmt.where(Instrument.product_type == product_type)

        if q and (q_norm := q.strip().upper()):
            stmt = stmt.where(
                func.upper(security_id).like(f"%{q_norm}%")
                | func.upper(Instrument.name).like(f"%{q_norm}%")
            )

        result = await self.db.execute(stmt.order_by(security_id.asc()).limit(limit))
        return [(security_id, name) for security_id, name in result.all()]

    async def list_currency_lookup_codes(
        self,
        *,
        q: str | None = None,
        limit: int,
    ) -> list[str]:
        """Return bounded distinct instrument currencies for selector workflows."""
        currency_code = func.upper(func.trim(Instrument.currency))
        stmt = (
            select(currency_code)
            .distinct()
            .where(Instrument.currency.is_not(None))
            .where(func.trim(Instrument.currency) != "")
        )

        if q and (q_norm := q.strip().upper()):
            stmt = stmt.where(currency_code.like(f"%{q_norm}%"))

        result = await self.db.execute(stmt.order_by(currency_code.asc()).limit(limit))
        return list(result.scalars().all())

    async def get_instruments_count(
        self, security_id: Optional[str] = None, product_type: Optional[str] = None
    ) -> int:
        """
        Returns the total count of instruments for the given filters.
        """
        stmt = self._get_base_query(security_id, product_type)
        count_stmt = select(func.count()).select_from(stmt.subquery())
        count = (await self.db.execute(count_stmt)).scalar()
        return count or 0
