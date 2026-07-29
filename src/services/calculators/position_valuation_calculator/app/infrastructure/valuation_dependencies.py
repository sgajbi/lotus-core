"""Construct concrete valuation repositories for a database session."""

from __future__ import annotations

from typing import Any

from portfolio_common.idempotency_repository import IdempotencyRepository
from portfolio_common.outbox_repository import OutboxRepository

from ..repositories.valuation_repository import ValuationRepository
from ..valuation_processor import ValuationProcessorDependencies
from .market_price_source_fact_repository import SqlAlchemyMarketPriceSourceFactResolver
from .source_evidence import build_authoritative_valuation_evidence
from .valuation_policy_assignment_repository import (
    SqlAlchemyValuationPolicyAssignmentResolver,
)
from .valuation_receipt_repository import SqlAlchemyValuationReceiptRepository


class SqlAlchemyValuationProcessorDependencyFactory:
    """Build SQLAlchemy-backed collaborators inside the caller's transaction."""

    def from_session(self, db: Any) -> ValuationProcessorDependencies:
        return ValuationProcessorDependencies(
            repo=ValuationRepository(db),
            idempotency_repo=IdempotencyRepository(db),
            outbox_repo=OutboxRepository(db),
            market_price_source_fact_resolver=SqlAlchemyMarketPriceSourceFactResolver(db),
            valuation_policy_assignment_resolver=SqlAlchemyValuationPolicyAssignmentResolver(db),
            valuation_receipt_repo=SqlAlchemyValuationReceiptRepository(db),
            source_evidence_builder=build_authoritative_valuation_evidence,
        )
