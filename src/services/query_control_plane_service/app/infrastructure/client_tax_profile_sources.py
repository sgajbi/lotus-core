"""SQLAlchemy source adapter for effective client tax-profile resolution."""

from datetime import date
from decimal import Decimal
from typing import Any

from portfolio_common.database_models import ClientTaxProfile
from portfolio_common.source_lifecycle_predicates import CLIENT_TAX_PROFILE_ACTIVE
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..domain.client_tax_profile import ClientTaxProfileSourceRecord
from .effective_profile_queries import effective_on, ranked_latest_ids


class SqlAlchemyClientTaxProfileSourceReader:
    """Select effective tax profiles with deterministic precedence."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_profiles(
        self,
        *,
        portfolio_id: str,
        client_id: str,
        as_of_date: date,
        mandate_id: str | None,
        include_inactive_profiles: bool,
    ) -> list[ClientTaxProfileSourceRecord]:
        predicates = [
            ClientTaxProfile.portfolio_id == portfolio_id,
            ClientTaxProfile.client_id == client_id,
            effective_on(
                ClientTaxProfile.effective_from, ClientTaxProfile.effective_to, as_of_date
            ),
        ]
        if mandate_id:
            predicates.append(
                or_(
                    ClientTaxProfile.mandate_id.is_(None), ClientTaxProfile.mandate_id == mandate_id
                )
            )
        if not include_inactive_profiles:
            predicates.append(
                CLIENT_TAX_PROFILE_ACTIVE.sqlalchemy_filter(ClientTaxProfile.profile_status)
            )
        ranked = ranked_latest_ids(
            ClientTaxProfile,
            ClientTaxProfile.tax_profile_id,
            predicates=predicates,
            order_by=(
                ClientTaxProfile.effective_from.desc(),
                ClientTaxProfile.observed_at.desc().nullslast(),
                ClientTaxProfile.profile_version.desc(),
                ClientTaxProfile.updated_at.desc(),
                ClientTaxProfile.created_at.desc(),
                ClientTaxProfile.id.desc(),
            ),
        )
        result = await self._session.execute(
            select(ClientTaxProfile)
            .join(ranked, ClientTaxProfile.id == ranked.c.id)
            .where(ranked.c.rn == 1)
            .order_by(ClientTaxProfile.tax_profile_id.asc())
        )
        return [_record(row) for row in result.scalars().all()]


def _record(row: Any) -> ClientTaxProfileSourceRecord:
    return ClientTaxProfileSourceRecord(
        tax_profile_id=row.tax_profile_id,
        tax_residency_country=row.tax_residency_country,
        booking_tax_jurisdiction=row.booking_tax_jurisdiction,
        tax_status=row.tax_status,
        profile_status=row.profile_status,
        withholding_tax_rate=_optional_decimal(row.withholding_tax_rate),
        capital_gains_tax_applicable=bool(row.capital_gains_tax_applicable),
        income_tax_applicable=bool(row.income_tax_applicable),
        treaty_codes=_string_tuple(row.treaty_codes),
        eligible_account_types=_string_tuple(row.eligible_account_types),
        effective_from=row.effective_from,
        effective_to=row.effective_to,
        profile_version=int(row.profile_version),
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
