# src/services/calculators/position_valuation_calculator/app/consumers/valuation_consumer.py
import json
import logging
import re

from confluent_kafka import Message
from portfolio_common.event_mapping import EventContractValidationError
from portfolio_common.events import PortfolioValuationRequiredEvent
from portfolio_common.kafka_consumer import BaseConsumer
from portfolio_common.valuation_job_contracts import VALUATION_CLAIM_TOKEN_HEADER
from pydantic import ValidationError
from sqlalchemy.exc import DBAPIError, OperationalError
from tenacity import before_log, retry, retry_if_exception_type, stop_after_attempt, wait_fixed

from ..infrastructure import build_valuation_job_processor
from ..valuation_processor import ValuationJobProcessor

logger = logging.getLogger(__name__)
_CLAIM_TOKEN_PATTERN = re.compile(r"^[0-9a-f]{32}$")


def _valuation_claim_token(msg: Message) -> str | None:
    """Return one valid claim token, preserving only legacy headerless dispatch."""

    try:
        headers = msg.headers() or []
    except Exception as exc:
        raise EventContractValidationError(
            "Valuation claim headers could not be inspected"
        ) from exc
    raw_values = [value for name, value in headers if name == VALUATION_CLAIM_TOKEN_HEADER]
    if not raw_values:
        return None
    if len(raw_values) != 1:
        raise EventContractValidationError(
            "Valuation dispatch must contain exactly one claim token"
        )
    raw_value = raw_values[0]
    if isinstance(raw_value, (bytes, bytearray)):
        try:
            claim_token = raw_value.decode("ascii")
        except UnicodeDecodeError as exc:
            raise EventContractValidationError("Valuation claim token must be ASCII") from exc
    elif isinstance(raw_value, str):
        claim_token = raw_value
    else:
        raise EventContractValidationError("Valuation claim token must be text")
    if not _CLAIM_TOKEN_PATTERN.fullmatch(claim_token):
        raise EventContractValidationError("Valuation claim token has an invalid format")
    return claim_token


class ValuationConsumer(BaseConsumer):
    """
    Consumes scheduled valuation jobs and delegates valid-message valuation workflow.
    """

    def __init__(
        self,
        *args,
        valuation_processor: ValuationJobProcessor | None = None,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._valuation_processor = valuation_processor or build_valuation_job_processor()

    @staticmethod
    def _build_processing_event_id(*, msg: Message) -> str:
        return f"{msg.topic()}-{msg.partition()}-{msg.offset()}"

    @retry(
        wait=wait_fixed(3),
        stop=stop_after_attempt(5),
        before=before_log(logger, logging.INFO),
        retry=retry_if_exception_type((DBAPIError, OperationalError)),
        reraise=True,
    )
    async def process_message(self, msg: Message):
        key = msg.key().decode("utf-8") if msg.key() else "NoKey"
        value = msg.value().decode("utf-8")
        event_id = None
        event = None
        claim_token = None

        try:
            event_data = json.loads(value)
            with self._message_correlation_context(
                msg,
                fallback_correlation_id=event_data.get("correlation_id"),
            ) as correlation_id:
                event = PortfolioValuationRequiredEvent.model_validate(event_data)
                event_id = self._build_processing_event_id(msg=msg)
                claim_token = _valuation_claim_token(msg)

                self._log_valuation_job_start(event)
                await self._valuation_processor.process_valid_event(
                    event,
                    event_id,
                    correlation_id,
                    claim_token=claim_token,
                )

        except (json.JSONDecodeError, ValidationError, EventContractValidationError):
            logger.error(
                "Message validation failed for key '%s'.",
                key,
                exc_info=True,
            )
            raise
        except (DBAPIError, OperationalError) as exc:
            logger.warning(
                "DB or data availability error for event %s: %s. Retrying...",
                event_id,
                exc,
                exc_info=False,
            )
            raise
        except Exception as exc:
            logger.error(
                "Unexpected error processing message with key '%s'.",
                key,
                exc_info=True,
            )
            if event:
                await self._valuation_processor.mark_failed_after_unexpected_error(
                    event,
                    exc,
                    claim_token=claim_token,
                )
            raise

    @staticmethod
    def _log_valuation_job_start(event: PortfolioValuationRequiredEvent) -> None:
        logger.debug(
            "Processing valuation job.",
            extra={
                "security_id": event.security_id,
                "portfolio_id": event.portfolio_id,
                "valuation_date": event.valuation_date.isoformat(),
                "epoch": event.epoch,
            },
        )
