from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.ingestion_service.app.DTOs.instrument_dto import Instrument
from src.services.ingestion_service.app.services.upload_publishers import (
    IngestionServiceUploadPublisher,
)


@pytest.mark.asyncio
async def test_ingestion_service_upload_publisher_dispatches_by_entity() -> None:
    ingestion_service = MagicMock()
    ingestion_service.publish_instruments = AsyncMock()
    publisher = IngestionServiceUploadPublisher(ingestion_service)
    instrument = Instrument(
        security_id="SEC1",
        name="Bond A",
        isin="ISIN1",
        currency="USD",
        product_type="bond",
    )

    await publisher.publish_records("instruments", [instrument])

    ingestion_service.publish_instruments.assert_awaited_once_with([instrument])
