"""Source-safe logging policy for terminal Kafka consumer failures."""

import logging
from collections.abc import Callable

from .consumer_error_evidence import terminal_error_log_evidence


def log_terminal_processing_error(
    log_consumer_event: Callable[..., None],
    error: Exception,
    *,
    reason_code: str,
) -> None:
    """Emit terminal failure identity without raw exception fields."""

    log_consumer_event(
        logging.ERROR,
        "Kafka message processing failed terminally.",
        event_name="kafka.consumer.processing_terminal",
        status="terminal_failure",
        reason_code=reason_code,
        **terminal_error_log_evidence(error),
    )
