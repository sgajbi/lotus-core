from fastapi import Depends

from src.services.ingestion_service.app.dependencies import (
    get_ingestion_service,
)
from src.services.ingestion_service.app.services.ingestion_job_service import (
    IngestionJobService,
    get_ingestion_job_service,
)
from src.services.ingestion_service.app.services.ingestion_service import IngestionService

from .application.bookkeeping_repair_commands import BookkeepingRepairCommandService
from .application.consumer_dlq_replay_commands import ConsumerDlqReplayCommandService
from .application.ingestion_operations_queries import IngestionOperationsQueryService
from .application.ingestion_retry_commands import IngestionRetryCommandService
from .application.ops_control_commands import OpsControlCommandService
from .application.replay_payload_dispatcher import (
    IngestionServiceReplayPayloadDispatcher,
    ReplayPayloadDispatcher,
)


def get_replay_payload_dispatcher(
    ingestion_service: IngestionService = Depends(get_ingestion_service),
) -> ReplayPayloadDispatcher:
    return IngestionServiceReplayPayloadDispatcher(ingestion_service)


def get_ingestion_retry_command_service(
    ingestion_job_service: IngestionJobService = Depends(get_ingestion_job_service),
    replay_payload_dispatcher: ReplayPayloadDispatcher = Depends(get_replay_payload_dispatcher),
) -> IngestionRetryCommandService:
    return IngestionRetryCommandService(
        ingestion_job_service=ingestion_job_service,
        replay_payload_dispatcher=replay_payload_dispatcher,
    )


def get_consumer_dlq_replay_command_service(
    ingestion_job_service: IngestionJobService = Depends(get_ingestion_job_service),
    replay_payload_dispatcher: ReplayPayloadDispatcher = Depends(get_replay_payload_dispatcher),
) -> ConsumerDlqReplayCommandService:
    return ConsumerDlqReplayCommandService(
        ingestion_job_service=ingestion_job_service,
        replay_payload_dispatcher=replay_payload_dispatcher,
    )


def get_bookkeeping_repair_command_service(
    ingestion_job_service: IngestionJobService = Depends(get_ingestion_job_service),
) -> BookkeepingRepairCommandService:
    return BookkeepingRepairCommandService(ingestion_job_service=ingestion_job_service)


def get_ops_control_command_service(
    ingestion_job_service: IngestionJobService = Depends(get_ingestion_job_service),
) -> OpsControlCommandService:
    return OpsControlCommandService(ingestion_job_service=ingestion_job_service)


def get_ingestion_operations_query_service(
    ingestion_job_service: IngestionJobService = Depends(get_ingestion_job_service),
) -> IngestionOperationsQueryService:
    return IngestionOperationsQueryService(ingestion_job_service=ingestion_job_service)
