# libs/portfolio-common/portfolio_common/logging_utils.py
import logging
import os
import sys
import uuid
from contextvars import ContextVar

from pythonjsonlogger import jsonlogger  # NEW IMPORT

# This shared context variable will hold the correlation ID for each request/event.
# It's initialized with a default value for cases where it's not explicitly set.
correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="<not-set>")
request_id_var: ContextVar[str] = ContextVar("request_id", default="<not-set>")
trace_id_var: ContextVar[str] = ContextVar("trace_id", default="<not-set>")

class CorrelationIdFilter(logging.Filter):
    """
    A logging filter that injects the current correlation ID from a ContextVar
    into the log record.
    """
    def filter(self, record):
        """
        Attaches the correlation ID to the log record.

        Args:
            record: The log record to be filtered.

        Returns:
            True to allow the record to be processed.
        """
        record.correlation_id = correlation_id_var.get()
        record.request_id = request_id_var.get()
        record.trace_id = trace_id_var.get()
        record.service = os.getenv("SERVICE_NAME", "lotus-core-service")
        record.environment = os.getenv("ENVIRONMENT", "local")
        return True

def setup_logging():
    """
    Configures the root logger for standardized, correlation-ID-aware,
    structured JSON logging. This ensures all loggers within an application
    (including libraries) will inherit this configuration.
    """
    # Get the root logger
    root_logger = logging.getLogger()
    
    # Clear any existing handlers to prevent duplicate logs
    if root_logger.hasHandlers():
        root_logger.handlers.clear()
        
    root_logger.setLevel(logging.INFO)

    handler = logging.StreamHandler(sys.stdout)
    
    # --- REFACTORED: Use JsonFormatter ---
    # Define a standard format string that the JsonFormatter will use to structure the JSON output.
    formatter = jsonlogger.JsonFormatter(
        "%(asctime)s %(name)s %(levelname)s %(message)s %(service)s %(environment)s %(correlation_id)s %(request_id)s %(trace_id)s",
        rename_fields={
            "asctime": "timestamp",
            "levelname": "level",
            "name": "logger"
        }
    )
    
    handler.setFormatter(formatter)
    
    # Add our custom filter to the handler
    handler.addFilter(CorrelationIdFilter())

    root_logger.addHandler(handler)

def generate_correlation_id(prefix: str) -> str:
    """
    Generates a new correlation ID with a service-specific prefix.
    Args:
        prefix: A short code for the service (e.g., 'ING').
    Returns:
        A formatted correlation ID string.
    """
    return f"{prefix}:{uuid.uuid4()}"
