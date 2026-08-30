"""Source-safe HTTP error mapping for portfolio evidence routes."""

from typing import NoReturn

from fastapi import status

from .response_helpers import raise_problem


def _raise_source_evidence_problem(
    *,
    status_code: int,
    title: str,
    detail: str,
    error_code: str,
    source_product: str,
    portfolio_id: str,
    reason: str,
) -> NoReturn:
    raise_problem(
        status_code=status_code,
        title=title,
        detail=detail,
        error_code=error_code,
        metadata={
            "source_product": source_product,
            "portfolio_id": portfolio_id,
            "reason": reason,
        },
    )
    raise AssertionError("raise_problem returned unexpectedly")


def raise_source_evidence_not_found(
    *,
    source_product: str,
    portfolio_id: str,
    exc: Exception,
) -> NoReturn:
    _raise_source_evidence_problem(
        status_code=status.HTTP_404_NOT_FOUND,
        title="Portfolio source evidence not found",
        detail="Requested portfolio source evidence was not found.",
        error_code="QCP_SOURCE_EVIDENCE_NOT_FOUND",
        source_product=source_product,
        portfolio_id=portfolio_id,
        reason=exc.__class__.__name__,
    )


def raise_source_evidence_invalid_request(
    *,
    source_product: str,
    portfolio_id: str,
    exc: Exception,
) -> NoReturn:
    _raise_source_evidence_problem(
        status_code=status.HTTP_400_BAD_REQUEST,
        title="Portfolio source evidence request is invalid",
        detail="Portfolio source evidence request is invalid.",
        error_code="QCP_SOURCE_EVIDENCE_INVALID_REQUEST",
        source_product=source_product,
        portfolio_id=portfolio_id,
        reason=exc.__class__.__name__,
    )
