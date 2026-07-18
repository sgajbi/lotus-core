# src/libs/portfolio-common/portfolio_common/exceptions.py


class RetryableConsumerError(Exception):
    """
    Custom exception raised by a consumer when a transient, recoverable error
    occurs (e.g., temporary database outage).

    The BaseConsumer catches this exception, preserves partition order, and
    retries the same message in-process after the governed backoff. The offset
    remains uncommitted until processing succeeds or the configured retry
    budget routes the message through terminal recovery.
    """

    pass
