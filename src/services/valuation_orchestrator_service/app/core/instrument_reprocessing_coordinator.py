import logging

from portfolio_common.logging_utils import operation_log_extra
from portfolio_common.monitoring import INSTRUMENT_REPROCESSING_TRIGGERS_PENDING

from ..repositories.instrument_reprocessing_conversion_repository import (
    InstrumentReprocessingConversionRepository,
    InstrumentTriggerConversionResult,
)
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
        conversion_repository: InstrumentReprocessingConversionRepository,
    ) -> InstrumentTriggerConversionResult:
        result = await conversion_repository.convert_pending_triggers(batch_size=self._batch_size)
        if not result.claimed_count:
            return result

        logger.info(
            "Instrument-level reprocessing triggers claimed.",
            extra=operation_log_extra(
                event_name="valuation.scheduler.instrument_triggers_claimed",
                operation="valuation.scheduler.process_instrument_triggers",
                status="started",
                reason_code="triggers_claimed",
                trigger_count=result.claimed_count,
            ),
        )

        logger.info(
            "Consumed %s instrument-level triggers into durable replay jobs.",
            result.claimed_count,
            extra=operation_log_extra(
                event_name="valuation.scheduler.instrument_triggers_consumed",
                operation="valuation.scheduler.process_instrument_triggers",
                status="succeeded",
                reason_code="jobs_staged",
                trigger_count=result.claimed_count,
                jobs_created=result.created_count,
                jobs_coalesced_pending=result.coalesced_pending_count,
            ),
        )
        return result
