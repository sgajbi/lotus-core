from __future__ import annotations

from portfolio_common.domain.currency import normalize_currency_code
from sqlalchemy.ext.asyncio import AsyncSession

from ..application.reporting_currency_support import (
    FxSupportEvidence,
    ReportingCurrencySupportQuery,
    ReportingCurrencySupportResult,
)
from ..repositories.reporting_currency_support_repository import ReportingCurrencySupportRepository


class ReportingCurrencySupportService:
    """Evaluate reporting-currency support without conflating selector presence with support."""

    def __init__(self, db: AsyncSession):
        self._repository = ReportingCurrencySupportRepository(db)

    async def evaluate(
        self, query: ReportingCurrencySupportQuery
    ) -> ReportingCurrencySupportResult:
        portfolio_id = query.portfolio_id.strip()
        if not portfolio_id:
            raise ValueError("portfolio_id must not be blank")
        reporting_currency = normalize_currency_code(query.reporting_currency)
        observed = await self._repository.is_selector_currency_observed(currency=reporting_currency)
        base = dict(
            portfolio_id=portfolio_id,
            tenant_id=query.tenant_id,
            reporting_currency=reporting_currency,
            as_of_date=query.as_of_date,
            observed_selector_currency=observed,
        )
        try:
            source = await self._repository.get_portfolio_currency_source(
                portfolio_id=portfolio_id,
                tenant_id=query.tenant_id,
                as_of_date=query.as_of_date,
            )
        except ValueError:
            return ReportingCurrencySupportResult(
                **base,
                status="UNAVAILABLE",
                reason_code="portfolio_currency_source_invalid",
            )
        if source is None:
            return ReportingCurrencySupportResult(
                **base,
                status="UNAVAILABLE",
                reason_code="portfolio_source_unavailable",
            )

        base["tenant_id"] = source.tenant_id
        rate_dates = await self._repository.get_latest_fx_rate_dates(
            from_currencies=source.source_currencies,
            to_currency=reporting_currency,
            as_of_date=query.as_of_date,
        )
        evidence: list[FxSupportEvidence] = []
        missing: list[str] = []
        for source_currency in source.source_currencies:
            rate_date = (
                query.as_of_date
                if source_currency == reporting_currency
                else rate_dates.get(source_currency)
            )
            available = rate_date is not None
            evidence.append(
                FxSupportEvidence(
                    source_currency=source_currency,
                    rate_date=rate_date,
                    rate_available=available,
                )
            )
            if not available:
                missing.append(source_currency)

        status = "SUPPORTED" if not missing else "UNSUPPORTED"
        return ReportingCurrencySupportResult(
            **base,
            status=status,
            reason_code="supported" if not missing else "required_fx_source_unavailable",
            source_currencies=source.source_currencies,
            missing_source_currencies=tuple(missing),
            fx_evidence=tuple(evidence),
        )
