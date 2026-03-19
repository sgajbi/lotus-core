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
    KAFKA_TRANSACTIONS_REPROCESSING_REQUESTED_TOPIC,
)
from portfolio_common.kafka_utils import KafkaProducer, get_kafka_producer
from portfolio_common.logging_utils import correlation_id_var, normalize_lineage_value
from portfolio_common.monitoring import KAFKA_MESSAGES_PUBLISHED_TOTAL

from ..DTOs.business_date_dto import BusinessDate
from ..DTOs.fx_rate_dto import FxRate
from ..DTOs.instrument_dto import Instrument
from ..DTOs.market_price_dto import MarketPrice
from ..DTOs.portfolio_bundle_dto import PortfolioBundleIngestionRequest
from ..DTOs.portfolio_dto import Portfolio
from ..DTOs.transaction_dto import Transaction


class IngestionPublishError(RuntimeError):
    def __init__(
        self,
        message: str,
        failed_record_keys: list[str],
        published_record_count: int = 0,
    ):
        super().__init__(message)
        self.failed_record_keys = failed_record_keys
        self.published_record_count = published_record_count


class IngestionService:
    def __init__(self, kafka_producer: KafkaProducer):
        self._kafka_producer = kafka_producer

    def _get_headers(self, idempotency_key: str | None = None):
        """Constructs Kafka headers with the current correlation ID."""
        corr_id = normalize_lineage_value(correlation_id_var.get())
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

    @staticmethod
    def _raise_batch_publish_error(
        *,
        entity_label: str,
        failed_key: str,
        record_keys: list[str],
        failure_index: int,
    ) -> None:
        unpublished_record_keys = record_keys[failure_index:]
        published_record_count = failure_index
        earlier_records = (
            f"{published_record_count} earlier record(s) were already published"
            if published_record_count
            else "no earlier records were published"
        )
        unpublished_keys = ", ".join(unpublished_record_keys)
        raise IngestionPublishError(
            (
                f"Failed to publish {entity_label} '{failed_key}' after {earlier_records}. "
                f"Remaining unpublished record keys: {unpublished_keys}."
            ),
            failed_record_keys=unpublished_record_keys,
            published_record_count=published_record_count,
        )

    @staticmethod
    def _raise_flush_timeout_error(
        *,
        entity_label: str,
        record_keys: list[str],
    ) -> None:
        record_key_list = ", ".join(record_keys)
        raise IngestionPublishError(
            (
                f"Delivery confirmation timed out for {entity_label}. Affected record keys: "
                f"{record_key_list}."
            ),
            failed_record_keys=record_keys,
            published_record_count=0,
        )

    async def publish_business_dates(
        self, business_dates: List[BusinessDate], idempotency_key: str | None = None
    ) -> None:
        """Publishes a list of business dates to the raw business dates topic."""
        headers = self._get_headers(idempotency_key)
        record_keys = [
            f"{business_date.calendar_code}|{business_date.business_date.isoformat()}"
            for business_date in business_dates
        ]
        for idx, business_date in enumerate(business_dates):
            key = record_keys[idx]
            payload = business_date.model_dump()
            try:
                self._kafka_producer.publish_message(
                    topic=KAFKA_RAW_BUSINESS_DATES_TOPIC, key=key, value=payload, headers=headers
                )
                KAFKA_MESSAGES_PUBLISHED_TOTAL.labels(topic=KAFKA_RAW_BUSINESS_DATES_TOPIC).inc()
            except Exception as exc:
                try:
                    self._raise_batch_publish_error(
                        entity_label="business date",
                        failed_key=key,
                        record_keys=record_keys,
                        failure_index=idx,
                    )
                except IngestionPublishError as publish_exc:
                    raise publish_exc from exc

    async def publish_portfolios(
        self, portfolios: List[Portfolio], idempotency_key: str | None = None
    ) -> None:
        """Publishes a list of portfolios to the raw portfolios topic."""
        headers = self._get_headers(idempotency_key)
        record_keys = [portfolio.portfolio_id for portfolio in portfolios]
        for idx, portfolio in enumerate(portfolios):
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
                try:
                    self._raise_batch_publish_error(
                        entity_label="portfolio",
                        failed_key=portfolio.portfolio_id,
                        record_keys=record_keys,
                        failure_index=idx,
                    )
                except IngestionPublishError as publish_exc:
                    raise publish_exc from exc

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
        record_keys = [transaction.transaction_id for transaction in transactions]
        for idx, transaction in enumerate(transactions):
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
                try:
                    self._raise_batch_publish_error(
                        entity_label="transaction",
                        failed_key=transaction.transaction_id,
                        record_keys=record_keys,
                        failure_index=idx,
                    )
                except IngestionPublishError as publish_exc:
                    raise publish_exc from exc

    async def publish_instruments(
        self, instruments: List[Instrument], idempotency_key: str | None = None
    ) -> None:
        """Publishes a list of instruments to the instruments topic."""
        headers = self._get_headers(idempotency_key)
        record_keys = [instrument.security_id for instrument in instruments]
        for idx, instrument in enumerate(instruments):
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
                try:
                    self._raise_batch_publish_error(
                        entity_label="instrument",
                        failed_key=instrument.security_id,
                        record_keys=record_keys,
                        failure_index=idx,
                    )
                except IngestionPublishError as publish_exc:
                    raise publish_exc from exc

    async def publish_market_prices(
        self, market_prices: List[MarketPrice], idempotency_key: str | None = None
    ) -> None:
        """Publishes a list of market prices to the market prices topic."""
        headers = self._get_headers(idempotency_key)
        record_keys = [price.security_id for price in market_prices]
        for idx, price in enumerate(market_prices):
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
                try:
                    self._raise_batch_publish_error(
                        entity_label="market price",
                        failed_key=price.security_id,
                        record_keys=record_keys,
                        failure_index=idx,
                    )
                except IngestionPublishError as publish_exc:
                    raise publish_exc from exc

    async def publish_fx_rates(
        self, fx_rates: List[FxRate], idempotency_key: str | None = None
    ) -> None:
        """Publishes a list of FX rates to the fx_rates topic."""
        headers = self._get_headers(idempotency_key)
        record_keys = [
            f"{rate.from_currency}-{rate.to_currency}-{rate.rate_date.isoformat()}"
            for rate in fx_rates
        ]
        for idx, rate in enumerate(fx_rates):
            key = record_keys[idx]
            rate_payload = rate.model_dump()
            try:
                self._kafka_producer.publish_message(
                    topic=KAFKA_FX_RATES_TOPIC, key=key, value=rate_payload, headers=headers
                )
                KAFKA_MESSAGES_PUBLISHED_TOTAL.labels(topic=KAFKA_FX_RATES_TOPIC).inc()
            except Exception as exc:
                try:
                    self._raise_batch_publish_error(
                        entity_label="fx rate",
                        failed_key=key,
                        record_keys=record_keys,
                        failure_index=idx,
                    )
                except IngestionPublishError as publish_exc:
                    raise publish_exc from exc

    async def publish_portfolio_bundle(
        self, bundle: PortfolioBundleIngestionRequest, idempotency_key: str | None = None
    ) -> dict[str, int]:
        """
        Publishes a mixed portfolio bundle for UI/file-upload workflows.
        The bundle is fan-out published to existing domain topics to keep downstream
        processing unchanged.
        """
        published_counts = {
            "business_dates": 0,
            "portfolios": 0,
            "instruments": 0,
            "transactions": 0,
            "market_prices": 0,
            "fx_rates": 0,
        }
        try:
            await self.publish_business_dates(bundle.business_dates, idempotency_key)
            published_counts["business_dates"] = len(bundle.business_dates)

            await self.publish_portfolios(bundle.portfolios, idempotency_key)
            published_counts["portfolios"] = len(bundle.portfolios)

            await self.publish_instruments(bundle.instruments, idempotency_key)
            published_counts["instruments"] = len(bundle.instruments)

            await self.publish_transactions(bundle.transactions, idempotency_key)
            published_counts["transactions"] = len(bundle.transactions)

            await self.publish_market_prices(bundle.market_prices, idempotency_key)
            published_counts["market_prices"] = len(bundle.market_prices)

            await self.publish_fx_rates(bundle.fx_rates, idempotency_key)
            published_counts["fx_rates"] = len(bundle.fx_rates)
        except IngestionPublishError as exc:
            raise IngestionPublishError(
                (
                    "Portfolio bundle publish stopped after these entity groups were already "
                    f"published: {published_counts}. {exc}"
                ),
                failed_record_keys=exc.failed_record_keys,
                published_record_count=exc.published_record_count,
            ) from exc

        return published_counts

    async def publish_reprocessing_requests(
        self,
        transaction_ids: List[str],
        idempotency_key: str | None = None,
    ) -> None:
        """Publishes transaction reprocessing requests with batch failure accounting."""
        headers = self._get_headers(idempotency_key)
        for idx, txn_id in enumerate(transaction_ids):
            try:
                self._kafka_producer.publish_message(
                    topic=KAFKA_TRANSACTIONS_REPROCESSING_REQUESTED_TOPIC,
                    key=txn_id,
                    value={"transaction_id": txn_id},
                    headers=headers,
                )
                KAFKA_MESSAGES_PUBLISHED_TOTAL.labels(
                    topic=KAFKA_TRANSACTIONS_REPROCESSING_REQUESTED_TOPIC
                ).inc()
            except Exception as exc:
                try:
                    self._raise_batch_publish_error(
                        entity_label="reprocessing request",
                        failed_key=txn_id,
                        record_keys=transaction_ids,
                        failure_index=idx,
                    )
                except IngestionPublishError as publish_exc:
                    raise publish_exc from exc

        undelivered_count = self._kafka_producer.flush(timeout=5)
        if undelivered_count:
            self._raise_flush_timeout_error(
                entity_label="reprocessing request delivery confirmation",
                record_keys=transaction_ids,
            )


def get_ingestion_service(
    kafka_producer: KafkaProducer = Depends(get_kafka_producer),
) -> IngestionService:
    """Dependency injector for the IngestionService."""
    return IngestionService(kafka_producer)
