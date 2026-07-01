DISPATCH_PUBLISH_FAILURE_PHASE = "publish"
DISPATCH_CONFIRMATION_TIMEOUT_PHASE = "delivery_confirmation_timeout"


class SchedulerDispatchError(RuntimeError):
    def __init__(
        self,
        *,
        message: str,
        recovery_job_ids: tuple[int, ...],
        recovery_record_keys: tuple[str, ...],
        published_record_keys: tuple[str, ...],
        failure_phase: str,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.recovery_job_ids = recovery_job_ids
        self.recovery_record_keys = recovery_record_keys
        self.published_record_keys = published_record_keys
        self.failure_phase = failure_phase

    def __str__(self) -> str:
        return self.message


def dispatch_failure_reason(*, failure_phase: str, record_keys: tuple[str, ...]) -> str:
    key_summary = ", ".join(record_keys)
    if failure_phase == DISPATCH_CONFIRMATION_TIMEOUT_PHASE:
        return (
            "Scheduler dispatch delivery confirmation timed out; delivery state is unknown for "
            f"record keys: {key_summary}"
        )
    return f"Scheduler dispatch publish failed before queueing record keys: {key_summary}"


def present_job_ids(jobs: list[object]) -> tuple[int, ...]:
    return tuple(job_id for job in jobs if isinstance((job_id := getattr(job, "id", None)), int))
