"""SQLAlchemy source adapter for sustainability preference resolution."""

from datetime import date
from decimal import Decimal
from typing import Any

from portfolio_common.database_models import SustainabilityPreferenceProfile
from portfolio_common.source_lifecycle_predicates import SUSTAINABILITY_PREFERENCE_ACTIVE
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..domain.sustainability_preference_profile import SustainabilityPreferenceSourceRecord
from .effective_profile_queries import effective_on, ranked_latest_ids


class SqlAlchemySustainabilityPreferenceProfileSourceReader:
    """Select effective sustainability preferences with deterministic precedence."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_preferences(
        self,
        *,
        portfolio_id: str,
        client_id: str,
        as_of_date: date,
        mandate_id: str | None,
        include_inactive_preferences: bool,
    ) -> list[SustainabilityPreferenceSourceRecord]:
        predicates = [
            SustainabilityPreferenceProfile.portfolio_id == portfolio_id,
            SustainabilityPreferenceProfile.client_id == client_id,
            effective_on(
                SustainabilityPreferenceProfile.effective_from,
                SustainabilityPreferenceProfile.effective_to,
                as_of_date,
            ),
        ]
        if mandate_id:
            predicates.append(
                or_(
                    SustainabilityPreferenceProfile.mandate_id.is_(None),
                    SustainabilityPreferenceProfile.mandate_id == mandate_id,
                )
            )
        if not include_inactive_preferences:
            predicates.append(
                SUSTAINABILITY_PREFERENCE_ACTIVE.sqlalchemy_filter(
                    SustainabilityPreferenceProfile.preference_status
                )
            )
        ranked = ranked_latest_ids(
            SustainabilityPreferenceProfile,
            SustainabilityPreferenceProfile.preference_framework,
            SustainabilityPreferenceProfile.preference_code,
            predicates=predicates,
            order_by=(
                SustainabilityPreferenceProfile.effective_from.desc(),
                SustainabilityPreferenceProfile.observed_at.desc().nullslast(),
                SustainabilityPreferenceProfile.preference_version.desc(),
                SustainabilityPreferenceProfile.updated_at.desc(),
                SustainabilityPreferenceProfile.created_at.desc(),
                SustainabilityPreferenceProfile.id.desc(),
            ),
        )
        result = await self._session.execute(
            select(SustainabilityPreferenceProfile)
            .join(ranked, SustainabilityPreferenceProfile.id == ranked.c.id)
            .where(ranked.c.rn == 1)
            .order_by(
                SustainabilityPreferenceProfile.preference_framework.asc(),
                SustainabilityPreferenceProfile.preference_code.asc(),
            )
        )
        return [_record(row) for row in result.scalars().all()]


def _record(row: Any) -> SustainabilityPreferenceSourceRecord:
    return SustainabilityPreferenceSourceRecord(
        preference_framework=row.preference_framework,
        preference_code=row.preference_code,
        preference_status=row.preference_status,
        preference_source=row.preference_source,
        minimum_allocation=_optional_decimal(row.minimum_allocation),
        maximum_allocation=_optional_decimal(row.maximum_allocation),
        applies_to_asset_classes=_string_tuple(row.applies_to_asset_classes),
        exclusion_codes=_string_tuple(row.exclusion_codes),
        positive_tilt_codes=_string_tuple(row.positive_tilt_codes),
        effective_from=row.effective_from,
        effective_to=row.effective_to,
        preference_version=int(row.preference_version),
        source_record_id=row.source_record_id,
        observed_at=row.observed_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _optional_decimal(value: object) -> Decimal | None:
    if value is None or str(value).strip() == "":
        return None
    return Decimal(str(value))


def _string_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(str(item) for item in value if str(item).strip())
