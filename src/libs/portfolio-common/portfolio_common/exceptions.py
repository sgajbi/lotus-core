# src/libs/portfolio-common/portfolio_common/exceptions.py


class RetryableConsumerError(Exception):
    """
    Custom exception raised by a consumer when a transient, recoverable error
    occurs (e.g., temporary database outage).

    The BaseConsumer's main loop will catch this exception and intentionally
    NOT commit the Kafka offset, forcing the message to be redelivered and
    re-processed later.
    """

    pass
