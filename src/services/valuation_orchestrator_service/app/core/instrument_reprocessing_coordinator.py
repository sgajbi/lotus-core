import logging

from portfolio_common.logging_utils import operation_log_extra
from portfolio_common.monitoring import INSTRUMENT_REPROCESSING_TRIGGERS_PENDING
from portfolio_common.reprocessing_job_repository import ReprocessingJobRepository

from ..repositories.valuation_repository import ValuationRepository

logger = logging.getLogger(__name__)


class InstrumentReprocessingCoordinator:
    """Coordinates instrument-level valuation reprocessing triggers."""

    def __init__(self, *, batch_size: int) -> None:
        self._batch_size = batch_size

    async def update_reprocessing_metrics(self, *, repo: ValuationRepository) -> None:
        pending_triggers = await repo.get_instrument_reprocessing_triggers_count()
        INSTRUMENT_REPROCESSING_TRIGGERS_PENDING.set(pending_triggers)

    async def process_instrument_level_triggers(
        self,
        *,
        repo: ValuationRepository,
        reprocessing_job_repo: ReprocessingJobRepository,
    ) -> None:
        triggers = await repo.claim_instrument_reprocessing_triggers(self._batch_size)
        if not triggers:
            return

        logger.info(
            "Instrument-level reprocessing triggers claimed.",
            extra=operation_log_extra(
                event_name="valuation.scheduler.instrument_triggers_claimed",
                operation="valuation.scheduler.process_instrument_triggers",
                status="started",
                reason_code="triggers_claimed",
                trigger_count=len(triggers),
            ),
        )

        for trigger in triggers:
            payload = {
                "security_id": trigger.security_id,
                "earliest_impacted_date": trigger.earliest_impacted_date.isoformat(),
            }
            await reprocessing_job_repo.create_job(
                job_type="RESET_WATERMARKS",
                payload=payload,
                correlation_id=trigger.correlation_id,
            )
        logger.info(
            "Consumed %s instrument-level triggers into durable replay jobs.",
            len(triggers),
            extra=operation_log_extra(
                event_name="valuation.scheduler.instrument_triggers_consumed",
                operation="valuation.scheduler.process_instrument_triggers",
                status="succeeded",
                reason_code="jobs_created",
                trigger_count=len(triggers),
            ),
        )
