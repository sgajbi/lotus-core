import contextvars

# This shared context variable will hold the correlation ID for each request.
correlation_id_cv = contextvars.ContextVar("correlation_id", default=None)
