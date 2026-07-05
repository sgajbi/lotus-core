from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from tenacity import (
    RetryCallState,
    before_log,
    retry_if_exception_type,
    stop_after_attempt,
    stop_after_delay,
    wait_random_exponential,
)

from portfolio_common.logging_utils import operation_log_extra
from portfolio_common.monitoring import observe_retry_policy_event


@dataclass(frozen=True, slots=True)
class RetryPolicyProfile:
    name: str
    max_attempts: int
    max_elapsed_seconds: float
    initial_backoff_seconds: float
    max_backoff_seconds: float
    reason: str


KAFKA_ADMIN_STARTUP_RETRY = RetryPolicyProfile(
    name="kafka_admin_startup",
    max_attempts=15,
    max_elapsed_seconds=60.0,
    initial_backoff_seconds=1.0,
    max_backoff_seconds=4.0,
    reason="kafka_admin_startup_retry",
)

CONSUMER_DB_SHORT_RETRY = RetryPolicyProfile(
    name="consumer_db_short",
    max_attempts=8,
    max_elapsed_seconds=30.0,
    initial_backoff_seconds=0.5,
    max_backoff_seconds=2.0,
    reason="consumer_db_retry",
)

CONSUMER_DB_STANDARD_RETRY = RetryPolicyProfile(
    name="consumer_db_standard",
    max_attempts=12,
    max_elapsed_seconds=60.0,
    initial_backoff_seconds=1.0,
    max_backoff_seconds=5.0,
    reason="consumer_db_retry",
)

CONSUMER_DB_EXTENDED_RETRY = RetryPolicyProfile(
    name="consumer_db_extended",
    max_attempts=15,
    max_elapsed_seconds=90.0,
    initial_backoff_seconds=0.5,
    max_backoff_seconds=5.0,
    reason="consumer_db_retry",
)


def tenacity_retry_kwargs(
    *,
    profile: RetryPolicyProfile,
    retry_exceptions: tuple[type[BaseException], ...],
    logger: logging.Logger,
    reraise: bool = True,
) -> dict[str, Any]:
    return {
        "wait": wait_random_exponential(
            multiplier=profile.initial_backoff_seconds,
            max=profile.max_backoff_seconds,
        ),
        "stop": stop_after_attempt(profile.max_attempts)
        | stop_after_delay(profile.max_elapsed_seconds),
        "before": before_log(logger, logging.INFO),
        "before_sleep": retry_before_sleep(profile=profile, logger=logger),
        "retry": retry_if_exception_type(retry_exceptions),
        "reraise": reraise,
    }


def retry_before_sleep(*, profile: RetryPolicyProfile, logger: logging.Logger):
    def _before_sleep(retry_state: RetryCallState) -> None:
        exception = _retry_exception(retry_state)
        observe_retry_policy_event(
            profile=profile.name,
            outcome="retrying",
            reason=profile.reason,
        )
        logger.warning(
            "Retryable operation failed; retrying with bounded policy.",
            extra=operation_log_extra(
                event_name="retry.policy.retrying",
                operation="retry.policy",
                status="retrying",
                reason_code=profile.reason,
                profile=profile.name,
                attempt_number=retry_state.attempt_number,
                max_attempts=profile.max_attempts,
                max_elapsed_seconds=profile.max_elapsed_seconds,
                error_type=type(exception).__name__ if exception is not None else None,
            ),
        )

    return _before_sleep


def _retry_exception(retry_state: RetryCallState) -> BaseException | None:
    if retry_state.outcome is None:
        return None
    return retry_state.outcome.exception()
