import json
import logging

from confluent_kafka import Message
from portfolio_common.db import get_async_db_session
from portfolio_common.events import PortfolioAggregationDayCompletedEvent
from portfolio_common.idempotency_repository import IdempotencyRepository
from portfolio_common.kafka_consumer import BaseConsumer
from portfolio_common.logging_utils import correlation_id_var
from portfolio_common.outbox_repository import OutboxRepository
from pydantic import ValidationError
from sqlalchemy.exc import DBAPIError, IntegrityError
from tenacity import before_log, retry, retry_if_exception_type, stop_after_attempt, wait_fixed

from ..repositories.pipeline_stage_repository import PipelineStageRepository
from ..services.pipeline_orchestrator_service import PipelineOrchestratorService

logger = logging.getLogger(__name__)
SERVICE_NAME = "pipeline-orchestrator-portfolio-aggregation"


class PortfolioAggregationStageConsumer(BaseConsumer):
    @retry(
        wait=wait_fixed(2),
        stop=stop_after_attempt(8),
        before=before_log(logger, logging.INFO),
        retry=retry_if_exception_type((DBAPIError, IntegrityError)),
        reraise=True,
    )
    async def process_message(self, msg: Message):
        value = msg.value().decode("utf-8")
        event_id = f"{msg.topic()}-{msg.partition()}-{msg.offset()}"
        correlation_id = correlation_id_var.get()

        try:
            event = PortfolioAggregationDayCompletedEvent.model_validate(json.loads(value))

            async for db in get_async_db_session():
                async with db.begin():
                    idempotency_repo = IdempotencyRepository(db)
                    if await idempotency_repo.is_event_processed(event_id, SERVICE_NAME):
                        return

                    service = PipelineOrchestratorService(
                        repo=PipelineStageRepository(db),
                        outbox_repo=OutboxRepository(db),
                    )
                    await service.register_portfolio_aggregation_completed(event, correlation_id)

                    await idempotency_repo.mark_event_processed(
                        event_id,
                        event.portfolio_id,
                        SERVICE_NAME,
                        correlation_id,
                    )

        except (json.JSONDecodeError, ValidationError):
            logger.error(
                "Invalid portfolio aggregation completion payload; sending to DLQ.",
                exc_info=True,
            )
            await self._send_to_dlq_async(msg, ValueError("invalid payload"))
        except (DBAPIError, IntegrityError):
            logger.warning("DB error in portfolio aggregation stage consumer; retrying.")
            raise
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("Unexpected orchestrator error; sending to DLQ.", exc_info=True)
            await self._send_to_dlq_async(msg, exc)
