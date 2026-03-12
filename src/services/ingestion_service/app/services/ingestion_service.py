# services/ingestion_service/app/services/ingestion_service.py
from typing import List

from fastapi import Depends
from portfolio_common.config import (
    KAFKA_FX_RATES_TOPIC,
    KAFKA_INSTRUMENTS_TOPIC,
    KAFKA_MARKET_PRICES_TOPIC,
    KAFKA_RAW_BUSINESS_DATES_TOPIC,
    KAFKA_RAW_PORTFOLIOS_TOPIC,
    KAFKA_RAW_TRANSACTIONS_TOPIC,
)
from portfolio_common.kafka_utils import KafkaProducer, get_kafka_producer
from portfolio_common.logging_utils import correlation_id_var
from portfolio_common.monitoring import KAFKA_MESSAGES_PUBLISHED_TOTAL

from ..DTOs.business_date_dto import BusinessDate
from ..DTOs.fx_rate_dto import FxRate
from ..DTOs.instrument_dto import Instrument
from ..DTOs.market_price_dto import MarketPrice
from ..DTOs.portfolio_bundle_dto import PortfolioBundleIngestionRequest
from ..DTOs.portfolio_dto import Portfolio
from ..DTOs.transaction_dto import Transaction


class IngestionPublishError(RuntimeError):
    def __init__(self, message: str, failed_record_keys: list[str]):
        super().__init__(message)
        self.failed_record_keys = failed_record_keys


class IngestionService:
    def __init__(self, kafka_producer: KafkaProducer):
        self._kafka_producer = kafka_producer

    def _get_headers(self, idempotency_key: str | None = None):
        """Constructs Kafka headers with the current correlation ID."""
        corr_id = correlation_id_var.get()
        if corr_id == "<not-set>":
            corr_id = None
        headers: list[tuple[str, bytes]] = []
        if corr_id:
            headers.append(("correlation_id", corr_id.encode("utf-8")))
        if idempotency_key:
            headers.append(("idempotency_key", idempotency_key.encode("utf-8")))
        return headers or None

    @staticmethod
    def _partition_key_or_raise(*, key: str, field_name: str) -> str:
        normalized = key.strip()
        if not normalized:
            raise ValueError(f"Partition key field '{field_name}' must be non-empty.")
        return normalized

    async def publish_business_dates(
        self, business_dates: List[BusinessDate], idempotency_key: str | None = None
    ) -> None:
        """Publishes a list of business dates to the raw business dates topic."""
        headers = self._get_headers(idempotency_key)
        for business_date in business_dates:
            key = f"{business_date.calendar_code}|{business_date.business_date.isoformat()}"
            payload = business_date.model_dump()
            try:
                self._kafka_producer.publish_message(
                    topic=KAFKA_RAW_BUSINESS_DATES_TOPIC, key=key, value=payload, headers=headers
                )
                KAFKA_MESSAGES_PUBLISHED_TOTAL.labels(topic=KAFKA_RAW_BUSINESS_DATES_TOPIC).inc()
            except Exception as exc:
                raise IngestionPublishError(
                    f"Failed to publish business date '{key}'.", [key]
                ) from exc

    async def publish_portfolios(
        self, portfolios: List[Portfolio], idempotency_key: str | None = None
    ) -> None:
        """Publishes a list of portfolios to the raw portfolios topic."""
        headers = self._get_headers(idempotency_key)
        for portfolio in portfolios:
            portfolio_payload = portfolio.model_dump()
            try:
                self._kafka_producer.publish_message(
                    topic=KAFKA_RAW_PORTFOLIOS_TOPIC,
                    key=portfolio.portfolio_id,
                    value=portfolio_payload,
                    headers=headers,
                )
                KAFKA_MESSAGES_PUBLISHED_TOTAL.labels(topic=KAFKA_RAW_PORTFOLIOS_TOPIC).inc()
            except Exception as exc:
                raise IngestionPublishError(
                    f"Failed to publish portfolio '{portfolio.portfolio_id}'.",
                    [portfolio.portfolio_id],
                ) from exc

    async def publish_transaction(
        self, transaction: Transaction, idempotency_key: str | None = None
    ) -> None:
        """Publishes a single transaction to the raw transactions topic."""
        headers = self._get_headers(idempotency_key)
        transaction_payload = transaction.model_dump()
        partition_key = self._partition_key_or_raise(
            key=transaction.portfolio_id, field_name="portfolio_id"
        )
        try:
            self._kafka_producer.publish_message(
                topic=KAFKA_RAW_TRANSACTIONS_TOPIC,
                key=partition_key,
                value=transaction_payload,
                headers=headers,
            )
            KAFKA_MESSAGES_PUBLISHED_TOTAL.labels(topic=KAFKA_RAW_TRANSACTIONS_TOPIC).inc()
        except Exception as exc:
            raise IngestionPublishError(
                f"Failed to publish transaction '{transaction.transaction_id}'.",
                [transaction.transaction_id],
            ) from exc

    async def publish_transactions(
        self, transactions: List[Transaction], idempotency_key: str | None = None
    ) -> None:
        """Publishes a list of transactions to the raw transactions topic."""
        headers = self._get_headers(idempotency_key)
        for transaction in transactions:
            transaction_payload = transaction.model_dump()
            partition_key = self._partition_key_or_raise(
                key=transaction.portfolio_id, field_name="portfolio_id"
            )
            try:
                self._kafka_producer.publish_message(
                    topic=KAFKA_RAW_TRANSACTIONS_TOPIC,
                    key=partition_key,
                    value=transaction_payload,
                    headers=headers,
                )
                KAFKA_MESSAGES_PUBLISHED_TOTAL.labels(topic=KAFKA_RAW_TRANSACTIONS_TOPIC).inc()
            except Exception as exc:
                raise IngestionPublishError(
                    f"Failed to publish transaction '{transaction.transaction_id}'.",
                    [transaction.transaction_id],
                ) from exc

    async def publish_instruments(
        self, instruments: List[Instrument], idempotency_key: str | None = None
    ) -> None:
        """Publishes a list of instruments to the instruments topic."""
        headers = self._get_headers(idempotency_key)
        for instrument in instruments:
            instrument_payload = instrument.model_dump()
            try:
                self._kafka_producer.publish_message(
                    topic=KAFKA_INSTRUMENTS_TOPIC,
                    key=instrument.security_id,
                    value=instrument_payload,
                    headers=headers,
                )
                KAFKA_MESSAGES_PUBLISHED_TOTAL.labels(topic=KAFKA_INSTRUMENTS_TOPIC).inc()
            except Exception as exc:
                raise IngestionPublishError(
                    f"Failed to publish instrument '{instrument.security_id}'.",
                    [instrument.security_id],
                ) from exc

    async def publish_market_prices(
        self, market_prices: List[MarketPrice], idempotency_key: str | None = None
    ) -> None:
        """Publishes a list of market prices to the market prices topic."""
        headers = self._get_headers(idempotency_key)
        for price in market_prices:
            price_payload = price.model_dump()
            try:
                self._kafka_producer.publish_message(
                    topic=KAFKA_MARKET_PRICES_TOPIC,
                    key=price.security_id,
                    value=price_payload,
                    headers=headers,
                )
                KAFKA_MESSAGES_PUBLISHED_TOTAL.labels(topic=KAFKA_MARKET_PRICES_TOPIC).inc()
            except Exception as exc:
                raise IngestionPublishError(
                    f"Failed to publish market price for '{price.security_id}'.",
                    [price.security_id],
                ) from exc

    async def publish_fx_rates(
        self, fx_rates: List[FxRate], idempotency_key: str | None = None
    ) -> None:
        """Publishes a list of FX rates to the fx_rates topic."""
        headers = self._get_headers(idempotency_key)
        for rate in fx_rates:
            key = f"{rate.from_currency}-{rate.to_currency}-{rate.rate_date.isoformat()}"
            rate_payload = rate.model_dump()
            try:
                self._kafka_producer.publish_message(
                    topic=KAFKA_FX_RATES_TOPIC, key=key, value=rate_payload, headers=headers
                )
                KAFKA_MESSAGES_PUBLISHED_TOTAL.labels(topic=KAFKA_FX_RATES_TOPIC).inc()
            except Exception as exc:
                raise IngestionPublishError(
                    f"Failed to publish fx rate '{key}'.",
                    [key],
                ) from exc

    async def publish_portfolio_bundle(
        self, bundle: PortfolioBundleIngestionRequest, idempotency_key: str | None = None
    ) -> dict[str, int]:
        """
        Publishes a mixed portfolio bundle for UI/file-upload workflows.
        The bundle is fan-out published to existing domain topics to keep downstream
        processing unchanged.
        """
        await self.publish_business_dates(bundle.business_dates, idempotency_key)
        await self.publish_portfolios(bundle.portfolios, idempotency_key)
        await self.publish_instruments(bundle.instruments, idempotency_key)
        await self.publish_transactions(bundle.transactions, idempotency_key)
        await self.publish_market_prices(bundle.market_prices, idempotency_key)
        await self.publish_fx_rates(bundle.fx_rates, idempotency_key)

        return {
            "business_dates": len(bundle.business_dates),
            "portfolios": len(bundle.portfolios),
            "instruments": len(bundle.instruments),
            "transactions": len(bundle.transactions),
            "market_prices": len(bundle.market_prices),
            "fx_rates": len(bundle.fx_rates),
        }


def get_ingestion_service(
    kafka_producer: KafkaProducer = Depends(get_kafka_producer),
) -> IngestionService:
    """Dependency injector for the IngestionService."""
    return IngestionService(kafka_producer)
