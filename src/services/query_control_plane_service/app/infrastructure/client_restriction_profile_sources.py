"""SQLAlchemy source adapter for effective client restriction resolution."""

from datetime import date
from typing import Any

from portfolio_common.database_models import ClientRestrictionProfile
from portfolio_common.source_lifecycle_predicates import (
    CLIENT_RESTRICTION_ACTIVE,
)
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..domain.client_restriction_profile import (
    ClientRestrictionSourceRecord,
)
from ..domain.effective_mandate import EffectiveMandateBinding
from .effective_mandate_sources import resolve_effective_mandate_binding
from .effective_profile_queries import effective_on, ranked_latest_ids


class SqlAlchemyClientRestrictionProfileSourceReader:
    """Select effective mandate and restriction records with deterministic precedence."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def resolve_mandate_binding(
        self,
        *,
        portfolio_id: str,
        as_of_date: date,
        mandate_id: str | None,
    ) -> EffectiveMandateBinding | None:
        return await resolve_effective_mandate_binding(
            self._session,
            portfolio_id=portfolio_id,
            as_of_date=as_of_date,
            mandate_id=mandate_id,
        )

    async def list_restrictions(
        self,
        *,
        portfolio_id: str,
        client_id: str,
        as_of_date: date,
        mandate_id: str | None,
        include_inactive_restrictions: bool,
    ) -> list[ClientRestrictionSourceRecord]:
        predicates = [
            ClientRestrictionProfile.portfolio_id == portfolio_id,
            ClientRestrictionProfile.client_id == client_id,
            effective_on(
                ClientRestrictionProfile.effective_from,
                ClientRestrictionProfile.effective_to,
                as_of_date,
            ),
        ]
        if mandate_id:
            predicates.append(
                or_(
                    ClientRestrictionProfile.mandate_id.is_(None),
                    ClientRestrictionProfile.mandate_id == mandate_id,
                )
            )
        if not include_inactive_restrictions:
            predicates.append(
                CLIENT_RESTRICTION_ACTIVE.sqlalchemy_filter(
                    ClientRestrictionProfile.restriction_status
                )
            )

        ranked = ranked_latest_ids(
            ClientRestrictionProfile,
            ClientRestrictionProfile.restriction_scope,
            ClientRestrictionProfile.restriction_code,
            predicates=predicates,
            order_by=(
                ClientRestrictionProfile.effective_from.desc(),
                ClientRestrictionProfile.observed_at.desc().nullslast(),
                ClientRestrictionProfile.restriction_version.desc(),
                ClientRestrictionProfile.updated_at.desc(),
                ClientRestrictionProfile.created_at.desc(),
                ClientRestrictionProfile.id.desc(),
            ),
        )
        statement = (
            select(ClientRestrictionProfile)
            .join(ranked, ClientRestrictionProfile.id == ranked.c.id)
            .where(ranked.c.rn == 1)
            .order_by(
                ClientRestrictionProfile.restriction_scope.asc(),
                ClientRestrictionProfile.restriction_code.asc(),
            )
        )
        result = await self._session.execute(statement)
        return [_restriction_record(row) for row in result.scalars().all()]


def _restriction_record(row: Any) -> ClientRestrictionSourceRecord:
    return ClientRestrictionSourceRecord(
        restriction_scope=row.restriction_scope,
        restriction_code=row.restriction_code,
        restriction_status=row.restriction_status,
        restriction_source=row.restriction_source,
        applies_to_buy=bool(row.applies_to_buy),
        applies_to_sell=bool(row.applies_to_sell),
        instrument_ids=_string_tuple(row.instrument_ids),
        asset_classes=_string_tuple(row.asset_classes),
        issuer_ids=_string_tuple(row.issuer_ids),
        country_codes=_string_tuple(row.country_codes),
        effective_from=row.effective_from,
        effective_to=row.effective_to,
        restriction_version=int(row.restriction_version),
        source_record_id=row.source_record_id,
        observed_at=row.observed_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _string_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(str(item) for item in value if str(item).strip())
