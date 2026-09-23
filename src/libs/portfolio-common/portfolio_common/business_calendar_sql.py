"""Shared SQL predicates for canonical business-calendar identity."""

from typing import Any

from sqlalchemy import func, text
from sqlalchemy.ext.asyncio import AsyncSession

from .config import DEFAULT_BUSINESS_CALENDAR_CODE
from .domain.business_calendar import normalize_business_calendar_code


def normalized_business_calendar_code_expression(column: Any) -> Any:
    """Normalize persisted calendar identities at the read boundary.

    Older databases can contain mixed-case or whitespace-padded identities. Readers
    must continue to admit those rows while all supported writes store canonical codes.
    PostgreSQL's one-argument ``trim`` removes only spaces, whereas Python ``strip``
    admits tabs and line breaks too, so use the database whitespace character class.
    """

    return func.upper(func.regexp_replace(column, r"^[[:space:]]+|[[:space:]]+$", "", "g"))


def business_calendar_code_matches(column: Any, calendar_code: object) -> Any:
    """Return a canonical, legacy-compatible calendar identity predicate."""

    return normalized_business_calendar_code_expression(column) == normalize_business_calendar_code(
        calendar_code
    )


def default_business_calendar_matches(column: Any) -> Any:
    """Return the legacy-compatible predicate for the configured default calendar."""

    return business_calendar_code_matches(column, DEFAULT_BUSINESS_CALENDAR_CODE)


def _default_business_calendar_lock_params() -> dict[str, str]:
    return {"lock_identity": f"lotus-core:valuation-calendar:{DEFAULT_BUSINESS_CALENDAR_CODE}"}


async def acquire_default_business_calendar_activation_lock(session: AsyncSession) -> None:
    """Exclusively fence first-calendar activation against fallback valuation readers."""

    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_identity, 0))"),
        _default_business_calendar_lock_params(),
    )


async def acquire_default_business_calendar_fallback_lock(session: AsyncSession) -> None:
    """Share the activation fence across concurrent empty-calendar valuation work."""

    await session.execute(
        text("SELECT pg_advisory_xact_lock_shared(hashtextextended(:lock_identity, 0))"),
        _default_business_calendar_lock_params(),
    )
