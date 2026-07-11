"""SQLAlchemy source adapter for effective client tax-rule resolution."""

from datetime import date
from decimal import Decimal
from typing import Any

from portfolio_common.database_models import ClientTaxRuleSet
from portfolio_common.source_lifecycle_predicates import CLIENT_TAX_RULE_SET_ACTIVE
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..domain.client_tax_rule_set import ClientTaxRuleSourceRecord
from .effective_profile_queries import effective_on, ranked_latest_ids


class SqlAlchemyClientTaxRuleSetSourceReader:
    """Select effective tax rules with deterministic precedence."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_rules(
        self,
        *,
        portfolio_id: str,
        client_id: str,
        as_of_date: date,
        mandate_id: str | None,
        include_inactive_rules: bool,
    ) -> list[ClientTaxRuleSourceRecord]:
        predicates = [
            ClientTaxRuleSet.portfolio_id == portfolio_id,
            ClientTaxRuleSet.client_id == client_id,
            effective_on(
                ClientTaxRuleSet.effective_from, ClientTaxRuleSet.effective_to, as_of_date
            ),
        ]
        if mandate_id:
            predicates.append(
                or_(
                    ClientTaxRuleSet.mandate_id.is_(None), ClientTaxRuleSet.mandate_id == mandate_id
                )
            )
        if not include_inactive_rules:
            predicates.append(
                CLIENT_TAX_RULE_SET_ACTIVE.sqlalchemy_filter(ClientTaxRuleSet.rule_status)
            )
        ranked = ranked_latest_ids(
            ClientTaxRuleSet,
            ClientTaxRuleSet.rule_set_id,
            ClientTaxRuleSet.jurisdiction_code,
            ClientTaxRuleSet.rule_code,
            predicates=predicates,
            order_by=(
                ClientTaxRuleSet.effective_from.desc(),
                ClientTaxRuleSet.observed_at.desc().nullslast(),
                ClientTaxRuleSet.rule_version.desc(),
                ClientTaxRuleSet.updated_at.desc(),
                ClientTaxRuleSet.created_at.desc(),
                ClientTaxRuleSet.id.desc(),
            ),
        )
        result = await self._session.execute(
            select(ClientTaxRuleSet)
            .join(ranked, ClientTaxRuleSet.id == ranked.c.id)
            .where(ranked.c.rn == 1)
            .order_by(
                ClientTaxRuleSet.rule_set_id.asc(),
                ClientTaxRuleSet.jurisdiction_code.asc(),
                ClientTaxRuleSet.rule_code.asc(),
            )
        )
        return [_record(row) for row in result.scalars().all()]


def _record(row: Any) -> ClientTaxRuleSourceRecord:
    return ClientTaxRuleSourceRecord(
        rule_set_id=row.rule_set_id,
        tax_year=int(row.tax_year),
        jurisdiction_code=row.jurisdiction_code,
        rule_code=row.rule_code,
        rule_category=row.rule_category,
        rule_status=row.rule_status,
        rule_source=row.rule_source,
        applies_to_asset_classes=_string_tuple(row.applies_to_asset_classes),
        applies_to_security_ids=_string_tuple(row.applies_to_security_ids),
        applies_to_income_types=_string_tuple(row.applies_to_income_types),
        rate=_optional_decimal(row.rate),
        threshold_amount=_optional_decimal(row.threshold_amount),
        threshold_currency=row.threshold_currency,
        effective_from=row.effective_from,
        effective_to=row.effective_to,
        rule_version=int(row.rule_version),
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
