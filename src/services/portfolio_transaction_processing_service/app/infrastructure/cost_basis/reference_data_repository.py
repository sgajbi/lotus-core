"""SQLAlchemy adapter for cost-basis portfolio and instrument reference data."""

from datetime import date

from portfolio_common.database_models import CashAccountMaster, Instrument, Portfolio
from portfolio_common.domain.cost_basis_method import normalize_cost_basis_method
from portfolio_common.identifiers import normalize_lookup_identifier
from portfolio_common.utils import async_timed
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...ports import (
    CostBasisInstrumentReference,
    CostBasisPortfolioReference,
    CostBasisReferenceData,
    SettlementCashAccountReference,
)


class SqlAlchemyCostBasisReferenceDataRepository:
    """Map persisted reference rows to framework-neutral cost-basis records."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @async_timed(
        repository="CostBasisReferenceDataRepository",
        method="get_cost_basis_reference_data",
    )
    async def get_cost_basis_reference_data(
        self,
        *,
        portfolio_id: str,
        security_id: str,
    ) -> CostBasisReferenceData | None:
        """Load both reference owners in one round trip for the processing hot path."""

        normalized_security_id = normalize_lookup_identifier(security_id)
        stmt = (
            select(
                Portfolio.portfolio_id.label("portfolio_id"),
                Portfolio.base_currency.label("base_currency"),
                Portfolio.cost_basis_method.label("cost_basis_method"),
                Portfolio.tenant_id.label("tenant_id"),
                Portfolio.legal_book_id.label("legal_book_id"),
                Instrument.security_id.label("instrument_security_id"),
                Instrument.product_type.label("instrument_product_type"),
                Instrument.asset_class.label("instrument_asset_class"),
                Instrument.currency.label("instrument_currency"),
            )
            .select_from(Portfolio)
            .outerjoin(
                Instrument,
                func.trim(Instrument.security_id) == normalized_security_id,
            )
            .where(Portfolio.portfolio_id == portfolio_id)
            .limit(1)
        )
        row = (await self._session.execute(stmt)).mappings().first()
        if row is None:
            return None

        instrument_security_id = row["instrument_security_id"]
        instrument = (
            None
            if instrument_security_id is None
            else CostBasisInstrumentReference(
                security_id=instrument_security_id,
                product_type=row["instrument_product_type"],
                asset_class=row["instrument_asset_class"],
                currency=row["instrument_currency"],
            )
        )
        return CostBasisReferenceData(
            portfolio=CostBasisPortfolioReference(
                portfolio_id=row["portfolio_id"],
                base_currency=row["base_currency"],
                cost_basis_method=normalize_cost_basis_method(row["cost_basis_method"]),
                tenant_id=row["tenant_id"],
                legal_book_id=row["legal_book_id"],
            ),
            instrument=instrument,
        )

    @async_timed(
        repository="CostBasisReferenceDataRepository",
        method="get_settlement_cash_account_reference",
    )
    async def get_settlement_cash_account_reference(
        self,
        *,
        portfolio_id: str,
        tenant_id: str,
        cash_account_id: str,
        as_of_date: date,
    ) -> SettlementCashAccountReference | None:
        """Load one active cash-account mapping within admitted portfolio authority."""

        row = (
            await self._session.execute(
                select(
                    CashAccountMaster.cash_account_id,
                    CashAccountMaster.security_id,
                    CashAccountMaster.account_currency,
                    Instrument.product_type.label("instrument_product_type"),
                    Instrument.currency.label("instrument_currency"),
                )
                .join(Portfolio, Portfolio.portfolio_id == CashAccountMaster.portfolio_id)
                .join(
                    Instrument,
                    func.trim(Instrument.security_id) == func.trim(CashAccountMaster.security_id),
                )
                .where(
                    CashAccountMaster.portfolio_id == portfolio_id,
                    Portfolio.tenant_id == tenant_id,
                    CashAccountMaster.cash_account_id == cash_account_id,
                    func.upper(func.trim(CashAccountMaster.lifecycle_status)) == "ACTIVE",
                    or_(
                        CashAccountMaster.opened_on.is_(None),
                        CashAccountMaster.opened_on <= as_of_date,
                    ),
                    or_(
                        CashAccountMaster.closed_on.is_(None),
                        CashAccountMaster.closed_on >= as_of_date,
                    ),
                )
                .with_for_update(
                    read=True,
                    of=(CashAccountMaster, Instrument, Portfolio),
                )
                .limit(1)
            )
        ).one_or_none()
        if row is None:
            return None
        return SettlementCashAccountReference(
            cash_account_id=row.cash_account_id,
            security_id=row.security_id,
            account_currency=row.account_currency,
            instrument_product_type=row.instrument_product_type,
            instrument_currency=row.instrument_currency,
        )
