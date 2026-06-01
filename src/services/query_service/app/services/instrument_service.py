# services/query-service/app/services/instrument_service.py
import logging
from typing import List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ..dtos.instrument_dto import InstrumentRecord, PaginatedInstrumentResponse
from ..repositories.identifier_normalization import normalize_security_id
from ..repositories.instrument_repository import InstrumentRepository

logger = logging.getLogger(__name__)


class InstrumentService:
    """
    Handles the business logic for querying instrument data.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = InstrumentRepository(db)

    async def get_instruments_by_ids(self, security_ids: List[str]) -> List[InstrumentRecord]:
        """Retrieves a list of instruments for a given list of security IDs."""
        normalized_security_ids = list(
            dict.fromkeys(
                normalized
                for security_id in security_ids
                if (normalized := normalize_security_id(security_id))
            )
        )
        if not normalized_security_ids:
            return []
        logger.info(f"Fetching details for {len(normalized_security_ids)} instruments.")
        db_results = await self.repo.get_by_security_ids(normalized_security_ids)
        return [self._to_instrument_record(row) for row in db_results]

    async def get_instruments(
        self,
        skip: int,
        limit: int,
        security_id: Optional[str] = None,
        product_type: Optional[str] = None,
    ) -> PaginatedInstrumentResponse:
        """
        Retrieves a paginated and filtered list of instruments.
        """
        logger.info("Fetching instruments.")
        security_id = normalize_security_id(security_id) if security_id else None

        total_count = await self.repo.get_instruments_count(
            security_id=security_id, product_type=product_type
        )

        db_results = (
            await self.repo.get_instruments(
                skip=skip, limit=limit, security_id=security_id, product_type=product_type
            )
            if total_count
            else []
        )

        instruments = [self._to_instrument_record(row) for row in db_results]

        return PaginatedInstrumentResponse(
            total=total_count, skip=skip, limit=limit, instruments=instruments
        )

    @staticmethod
    def _to_instrument_record(row) -> InstrumentRecord:
        record = InstrumentRecord.model_validate(row, from_attributes=True)
        return record.model_copy(update={"security_id": normalize_security_id(record.security_id)})
