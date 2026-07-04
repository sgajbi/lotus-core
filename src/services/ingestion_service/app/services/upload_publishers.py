from __future__ import annotations

from pydantic import BaseModel

from ..application.upload_commands import UploadEntity
from ..DTOs.business_date_dto import BusinessDate
from ..DTOs.fx_rate_dto import FxRate
from ..DTOs.instrument_dto import Instrument
from ..DTOs.market_price_dto import MarketPrice
from ..DTOs.portfolio_dto import Portfolio
from ..DTOs.transaction_dto import Transaction
from ..ports.upload_record_publisher import UploadRecordPublisher
from .ingestion_service import IngestionService


class IngestionServiceUploadPublisher(UploadRecordPublisher):
    def __init__(self, ingestion_service: IngestionService) -> None:
        self._ingestion_service = ingestion_service

    async def publish_records(
        self,
        entity_type: UploadEntity,
        valid_models: list[BaseModel],
    ) -> None:
        publishers = {
            "portfolios": self._publish_portfolios,
            "instruments": self._publish_instruments,
            "transactions": self._publish_transactions,
            "market_prices": self._publish_market_prices,
            "fx_rates": self._publish_fx_rates,
            "business_dates": self._publish_business_dates,
        }
        await publishers[entity_type](valid_models)

    async def _publish_portfolios(self, valid_models: list[BaseModel]) -> None:
        await self._ingestion_service.publish_portfolios(
            [model for model in valid_models if isinstance(model, Portfolio)]
        )

    async def _publish_instruments(self, valid_models: list[BaseModel]) -> None:
        await self._ingestion_service.publish_instruments(
            [model for model in valid_models if isinstance(model, Instrument)]
        )

    async def _publish_transactions(self, valid_models: list[BaseModel]) -> None:
        await self._ingestion_service.publish_transactions(
            [model for model in valid_models if isinstance(model, Transaction)]
        )

    async def _publish_market_prices(self, valid_models: list[BaseModel]) -> None:
        await self._ingestion_service.publish_market_prices(
            [model for model in valid_models if isinstance(model, MarketPrice)]
        )

    async def _publish_fx_rates(self, valid_models: list[BaseModel]) -> None:
        await self._ingestion_service.publish_fx_rates(
            [model for model in valid_models if isinstance(model, FxRate)]
        )

    async def _publish_business_dates(self, valid_models: list[BaseModel]) -> None:
        await self._ingestion_service.publish_business_dates(
            [model for model in valid_models if isinstance(model, BusinessDate)]
        )
