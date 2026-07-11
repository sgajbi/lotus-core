"""SQLAlchemy adapter for governed business-date lookup."""

from __future__ import annotations

import logging
from datetime import date

from portfolio_common.config import DEFAULT_BUSINESS_CALENDAR_CODE
from portfolio_common.database_models import BusinessDate
from portfolio_common.db import SessionLocal
from sqlalchemy import func, select

from ..settings import load_query_control_plane_settings

logger = logging.getLogger(__name__)


class SqlAlchemyBusinessDateProvider:
    """Read the latest default-calendar business date from Core persistence."""

    def latest_business_date(self) -> date | None:
        if not load_query_control_plane_settings().has_database_url:
            return None
        try:
            with SessionLocal() as session:
                statement = select(func.max(BusinessDate.date)).where(
                    BusinessDate.calendar_code == DEFAULT_BUSINESS_CALENDAR_CODE
                )
                latest = session.execute(statement).scalar_one_or_none()
                return latest if isinstance(latest, date) else None
        except Exception:
            logger.warning(
                "Failed to resolve as_of_date from business_dates; "
                "falling back to current UTC date.",
                exc_info=True,
            )
            return None
