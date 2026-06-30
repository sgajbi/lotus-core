from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from src.services.ingestion_service.app.DTOs.business_date_dto import BusinessDateIngestionRequest
from src.services.ingestion_service.app.DTOs.fx_rate_dto import FxRateIngestionRequest
from src.services.ingestion_service.app.DTOs.instrument_dto import InstrumentIngestionRequest
from src.services.ingestion_service.app.DTOs.market_price_dto import MarketPriceIngestionRequest
from src.services.ingestion_service.app.DTOs.portfolio_bundle_dto import (
    PortfolioBundleIngestionRequest,
)
from src.services.ingestion_service.app.DTOs.portfolio_dto import PortfolioIngestionRequest
from src.services.ingestion_service.app.DTOs.reprocessing_dto import ReprocessingRequest
from src.services.ingestion_service.app.DTOs.transaction_dto import TransactionIngestionRequest


class ReplayPayloadDispatcher(Protocol):
    async def replay_payload(
        self,
        *,
        endpoint: str,
        payload: dict[str, Any],
        idempotency_key: str | None,
    ) -> None: ...


class IngestionReplayPublisher(Protocol):
    async def publish_business_dates(
        self, business_dates: Any, idempotency_key: str | None = None
    ) -> None: ...

    async def publish_transactions(
        self, transactions: Any, idempotency_key: str | None = None
    ) -> None: ...

    async def publish_portfolios(
        self, portfolios: Any, idempotency_key: str | None = None
    ) -> None: ...

    async def publish_instruments(
        self, instruments: Any, idempotency_key: str | None = None
    ) -> None: ...

    async def publish_market_prices(
        self, market_prices: Any, idempotency_key: str | None = None
    ) -> None: ...

    async def publish_fx_rates(self, fx_rates: Any, idempotency_key: str | None = None) -> None: ...

    async def publish_portfolio_bundle(
        self, bundle: Any, idempotency_key: str | None = None
    ) -> None: ...

    async def publish_reprocessing_requests(
        self, transaction_ids: Any, idempotency_key: str | None = None
    ) -> None: ...


@dataclass(frozen=True)
class _ReplayPayloadPublisher:
    request_model: type[Any]
    publish_method: str
    payload_field: str | None

    async def publish(
        self,
        *,
        payload: dict[str, Any],
        idempotency_key: str | None,
        ingestion_service: IngestionReplayPublisher,
    ) -> None:
        request_model = self.request_model.model_validate(payload)
        publish_payload = (
            request_model
            if self.payload_field is None
            else getattr(request_model, self.payload_field)
        )
        await getattr(ingestion_service, self.publish_method)(
            publish_payload,
            idempotency_key=idempotency_key,
        )


_REPLAY_PAYLOAD_PUBLISHERS = {
    "/ingest/transactions": _ReplayPayloadPublisher(
        request_model=TransactionIngestionRequest,
        publish_method="publish_transactions",
        payload_field="transactions",
    ),
    "/ingest/portfolios": _ReplayPayloadPublisher(
        request_model=PortfolioIngestionRequest,
        publish_method="publish_portfolios",
        payload_field="portfolios",
    ),
    "/ingest/instruments": _ReplayPayloadPublisher(
        request_model=InstrumentIngestionRequest,
        publish_method="publish_instruments",
        payload_field="instruments",
    ),
    "/ingest/market-prices": _ReplayPayloadPublisher(
        request_model=MarketPriceIngestionRequest,
        publish_method="publish_market_prices",
        payload_field="market_prices",
    ),
    "/ingest/fx-rates": _ReplayPayloadPublisher(
        request_model=FxRateIngestionRequest,
        publish_method="publish_fx_rates",
        payload_field="fx_rates",
    ),
    "/ingest/business-dates": _ReplayPayloadPublisher(
        request_model=BusinessDateIngestionRequest,
        publish_method="publish_business_dates",
        payload_field="business_dates",
    ),
    "/ingest/portfolio-bundle": _ReplayPayloadPublisher(
        request_model=PortfolioBundleIngestionRequest,
        publish_method="publish_portfolio_bundle",
        payload_field=None,
    ),
    "/reprocess/transactions": _ReplayPayloadPublisher(
        request_model=ReprocessingRequest,
        publish_method="publish_reprocessing_requests",
        payload_field="transaction_ids",
    ),
}


@dataclass(frozen=True)
class IngestionServiceReplayPayloadDispatcher:
    ingestion_service: IngestionReplayPublisher

    async def replay_payload(
        self,
        *,
        endpoint: str,
        payload: dict[str, Any],
        idempotency_key: str | None,
    ) -> None:
        try:
            publisher = _REPLAY_PAYLOAD_PUBLISHERS[endpoint]
        except KeyError as exc:
            raise ValueError(f"Retry not supported for endpoint '{endpoint}'.") from exc

        await publisher.publish(
            payload=payload,
            idempotency_key=idempotency_key,
            ingestion_service=self.ingestion_service,
        )
