"""Construct concrete valuation repositories for a database session."""

from __future__ import annotations

from typing import Any

from portfolio_common.idempotency_repository import IdempotencyRepository
from portfolio_common.outbox_repository import OutboxRepository

from ..repositories.valuation_repository import ValuationRepository
from ..valuation_processor import ValuationProcessorDependencies


class SqlAlchemyValuationProcessorDependencyFactory:
    """Build SQLAlchemy-backed collaborators inside the caller's transaction."""

    def from_session(self, db: Any) -> ValuationProcessorDependencies:
        return ValuationProcessorDependencies(
            repo=ValuationRepository(db),
            idempotency_repo=IdempotencyRepository(db),
            outbox_repo=OutboxRepository(db),
        )
