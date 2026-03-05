# services/persistence_service/app/monitoring.py
from prometheus_client import Counter, Histogram
from prometheus_fastapi_instrumentator import Instrumentator

# 1. Define custom metrics
EVENTS_PROCESSED_TOTAL = Counter(
    "events_processed_total",
    "Total number of successfully processed Kafka events.",
    ["topic", "consumer_group"],
)

EVENTS_DLQD_TOTAL = Counter(
    "events_dlqd_total",
    "Total number of Kafka events sent to the Dead-Letter Queue.",
    ["topic", "consumer_group"],
)

EVENT_PROCESSING_LATENCY_SECONDS = Histogram(
    "event_processing_latency_seconds",
    "Latency of Kafka event processing in seconds.",
    ["topic", "consumer_group"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10],
)

# Bundle custom metrics into a dictionary for easy injection
CUSTOM_METRICS = {
    "processed": EVENTS_PROCESSED_TOTAL,
    "dlqd": EVENTS_DLQD_TOTAL,
    "latency": EVENT_PROCESSING_LATENCY_SECONDS,
}


def setup_metrics(app):
    """
    Sets up and attaches the Prometheus FastAPI Instrumentator to the app
    and returns the custom metric objects for dependency injection.
    """
    Instrumentator(excluded_handlers=["/metrics"]).instrument(app).expose(app)

    return CUSTOM_METRICS
