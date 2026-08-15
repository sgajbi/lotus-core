import logging

from portfolio_common.logging_utils import operation_log_extra
from portfolio_common.monitoring import (
    INSTRUMENT_REPROCESSING_TRIGGERS_PENDING,
    observe_instrument_reprocessing_trigger_conversion,
)

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
        return await conversion_repository.convert_pending_triggers(batch_size=self._batch_size)

    @staticmethod
    def observe_committed_conversion(result: InstrumentTriggerConversionResult) -> None:
        """Publish durable evidence only after the caller commits the conversion."""
        if not result.claimed_count:
            return
        observe_instrument_reprocessing_trigger_conversion("created", result.created_count)
        observe_instrument_reprocessing_trigger_conversion(
            "coalesced_pending", result.coalesced_pending_count
        )
        logger.info(
            "Committed %s instrument-level triggers into durable replay jobs.",
            result.claimed_count,
            extra=operation_log_extra(
                event_name="valuation.scheduler.instrument_triggers_committed",
                operation="valuation.scheduler.commit_instrument_triggers",
                status="succeeded",
                reason_code="jobs_committed",
                trigger_count=result.claimed_count,
                jobs_created=result.created_count,
                jobs_coalesced_pending=result.coalesced_pending_count,
            ),
        )
