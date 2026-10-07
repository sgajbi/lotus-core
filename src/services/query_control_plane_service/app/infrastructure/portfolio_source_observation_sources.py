"""One PostgreSQL statement snapshot; original pins never join mutable heads."""

from portfolio_common.portfolio_source_observation_models import (
    SOURCE_IDENTITY_COLUMNS,
    CashAvailabilityObservationHead,
    CashAvailabilityObservationRow,
    FundingInvestmentObservationHead,
    FundingInvestmentObservationRow,
    observation_from_row,
)
from sqlalchemy import and_, false, literal, select, true
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from ..contracts.portfolio_source_observations import (
    ObservationSelector,
    PortfolioSourceObservationsRequest,
)
from ..ports.portfolio_source_observations import PersistedSourceObservation


def _selected_fact(
    model, head, selector: ObservationSelector | None, tenant_id: str, portfolio_id: str
):
    statement = select(model).where(
        model.tenant_id == tenant_id, model.portfolio_id == portfolio_id
    )
    if selector is None:
        return statement.where(false()).subquery()
    statement = statement.where(
        model.producer_id == selector.producer_id,
        model.source_record_id == selector.source_record_id,
    )
    if selector.latest_restated:
        statement = statement.join(
            head,
            and_(
                *(getattr(head, name) == getattr(model, name) for name in SOURCE_IDENTITY_COLUMNS),
                head.observation_id == model.observation_id,
                head.content_hash == model.content_hash,
            ),
        )
    else:
        statement = statement.where(
            model.observation_id == selector.observation_id,
            model.content_hash == selector.content_hash,
            model.source_cut_id == selector.source_cut_id,
            model.source_revision == selector.source_version,
        )
    return statement.subquery()


def observation_snapshot_statement(
    *, tenant_id: str, portfolio_id: str, request: PortfolioSourceObservationsRequest
):
    cash = _selected_fact(
        CashAvailabilityObservationRow,
        CashAvailabilityObservationHead,
        request.cash,
        tenant_id,
        portfolio_id,
    )
    funding = _selected_fact(
        FundingInvestmentObservationRow,
        FundingInvestmentObservationHead,
        request.funding_investment,
        tenant_id,
        portfolio_id,
    )
    anchor = select(literal(1).label("snapshot_anchor")).subquery()
    return select(
        aliased(CashAvailabilityObservationRow, cash),
        aliased(FundingInvestmentObservationRow, funding),
    ).select_from(anchor.outerjoin(cash, true()).outerjoin(funding, true()))


class SqlAlchemyPortfolioSourceObservationReader:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def read_snapshot(
        self, *, tenant_id: str, portfolio_id: str, request: PortfolioSourceObservationsRequest
    ) -> tuple[PersistedSourceObservation | None, PersistedSourceObservation | None]:
        result = await self.session.execute(
            observation_snapshot_statement(
                tenant_id=tenant_id, portfolio_id=portfolio_id, request=request
            )
        )
        cash, funding = result.one()
        return self._persisted(cash), self._persisted(funding)

    @staticmethod
    def _persisted(row) -> PersistedSourceObservation | None:
        if row is None:
            return None
        return PersistedSourceObservation(
            fact=observation_from_row(row),
            observation_id=row.observation_id,
            received_at=row.received_at,
            receipt_job_id=row.receipt_job_id,
            qualification=row.qualification,
        )
