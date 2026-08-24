"""Failure evidence shared by durable valuation reprocessing paths."""


def reprocessing_failure_reason(exc: Exception) -> str:
    """Return non-empty, bounded-authority evidence for a failed durable job."""
    return str(exc).strip() or type(exc).__name__
