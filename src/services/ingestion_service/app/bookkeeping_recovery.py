POST_PUBLISH_BOOKKEEPING_REASON_CODE = "POST_PUBLISH_BOOKKEEPING_FAILED"
POST_PERSIST_BOOKKEEPING_REASON_CODE = "POST_PERSIST_BOOKKEEPING_FAILED"
POST_BOOKKEEPING_REPAIR_ACTION = "repair_ingestion_job_bookkeeping"
POST_BOOKKEEPING_RECOVERY_PATH = "ingestion_job_bookkeeping_repair"
POST_BOOKKEEPING_REMEDIATION = (
    "Inspect the job failure history, confirm published or persisted work, then run the governed "
    "bookkeeping repair action before client retry."
)
POST_BOOKKEEPING_FAILURE_PHASES = frozenset({"queue_bookkeeping", "persist_bookkeeping"})


def bookkeeping_reason_code(failure_phase: str) -> str:
    if failure_phase == "persist_bookkeeping":
        return POST_PERSIST_BOOKKEEPING_REASON_CODE
    return POST_PUBLISH_BOOKKEEPING_REASON_CODE
