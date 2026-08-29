"""Coordinate transitional position valuation workflow behavior."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Protocol

from portfolio_common.config import KAFKA_VALUATION_SNAPSHOT_PERSISTED_TOPIC
from portfolio_common.database_models import (
    DailyPositionSnapshot,
    FxRate,
    Instrument,
    MarketPrice,
    Portfolio,
    PositionHistory,
)
from portfolio_common.domain.eventing import portfolio_security_partition_key
from portfolio_common.domain.valuation import (
    BOND_QUOTE_AUTHORITY_REQUIRED_REASON,
    MarketPriceSourceFact,
    MarketPriceSourceFactError,
    PositionValuationEvidence,
    ResolvedValuationPolicyAssignment,
    UnknownValuationPolicyError,
    UnsupportedValuationError,
    ValuationAuthorityScope,
    ValuationBookScope,
    ValuationCalculationReceipt,
    ValuationPolicyAssignmentError,
    ValuationSnapshotIdentity,
    build_authoritative_valuation_receipt,
    build_legacy_valuation_receipt,
    is_quote_independent_flat_position,
    requires_bond_quote_authority,
    resolve_optional_valuation_book_scope,
)
from portfolio_common.events import (
    DailyPositionSnapshotPersistedEvent,
    PortfolioValuationRequiredEvent,
)
from portfolio_common.monitoring import (
    VALUATION_JOBS_FAILED_TOTAL,
    VALUATION_JOBS_SKIPPED_TOTAL,
    VALUATION_QUOTE_AUTHORITY_PATH_TOTAL,
)
from portfolio_common.valuation_job_contracts import ValuationJobTransitionOutcome

from .logic import (
    AuthoritativeValuationRequest,
    AuthoritativeValuationResult,
    calculate_authoritative_valuation,
)
from .logic.valuation_logic import ValuationComponents, ValuationLogic
from .ports import (
    MarketPriceAuthorityRequest,
    ValuationPolicyAuthorityRequest,
)

if TYPE_CHECKING:
    from portfolio_common.idempotency_repository import IdempotencyRepository
    from portfolio_common.outbox_repository import OutboxRepository

    from .ports import (
        MarketPriceSourceFactResolver,
        ValuationPolicyAssignmentResolver,
        ValuationReceiptRepository,
    )
    from .repositories.valuation_repository import ValuationRepository

logger = logging.getLogger(__name__)

SERVICE_NAME = "position-valuation-calculator"
FAILED_JOB_STATUSES = {"FAILED"}
VALUATION_FAILED = "FAILED"
VALUATION_UNVALUED = "UNVALUED"
VALUATION_VALUED_CURRENT = "VALUED_CURRENT"
VALUATION_VALUED_STALE = "VALUED_STALE"
VALUATION_JOB_COMPLETE = "COMPLETE"
VALUATION_JOB_SKIPPED_NO_POSITION = "SKIPPED_NO_POSITION"
ZERO = Decimal("0")


def _normalize_currency_code(value: object) -> str:
    return str(value or "").strip().upper()


class DataNotFoundError(Exception):
    """Custom exception for retryable data fetching errors."""


@dataclass(frozen=True, slots=True)
class ValuationReferenceData:
    instrument: Instrument | None
    portfolio: Portfolio | None
    price: MarketPrice | None


@dataclass(frozen=True, slots=True)
class ValuationSnapshotResult:
    snapshot: DailyPositionSnapshot
    job_failure_reason: str | None
    receipt: ValuationCalculationReceipt | None = None


class ValuationSourceEvidenceBuilder(Protocol):
    """Build calculation evidence from persisted valuation inputs."""

    def __call__(
        self,
        *,
        assignment: ResolvedValuationPolicyAssignment,
        price_fact: MarketPriceSourceFact,
        position: PositionHistory,
        portfolio: Portfolio,
        fx_rate: FxRate | None,
    ) -> PositionValuationEvidence: ...


@dataclass(frozen=True, slots=True)
class ValuationProcessorDependencies:
    repo: ValuationRepository
    idempotency_repo: IdempotencyRepository
    outbox_repo: OutboxRepository
    market_price_source_fact_resolver: MarketPriceSourceFactResolver
    valuation_policy_assignment_resolver: ValuationPolicyAssignmentResolver
    valuation_receipt_repo: ValuationReceiptRepository
    source_evidence_builder: ValuationSourceEvidenceBuilder


class ValuationProcessorDependencyFactory(Protocol):
    """Build valuation collaborators for one caller-owned database session."""

    def from_session(self, db: Any) -> ValuationProcessorDependencies: ...


class ValuationJobProcessor:
    def __init__(
        self,
        *,
        session_provider: Callable[[], Any],
        dependency_factory: ValuationProcessorDependencyFactory,
    ) -> None:
        self._session_provider = session_provider
        self._dependency_factory = dependency_factory

    async def process_valid_event(
        self,
        event: PortfolioValuationRequiredEvent,
        event_id: str,
        correlation_id: str,
        *,
        claim_token: str | None = None,
    ) -> None:
        async for db in self._session_provider():
            try:
                await self._process_event_session(
                    db,
                    event,
                    event_id,
                    correlation_id,
                    claim_token=claim_token,
                )
            except DataNotFoundError as exc:
                await self._mark_no_position_job_skipped(
                    db=db,
                    event=event,
                    event_id=event_id,
                    correlation_id=correlation_id,
                    claim_token=claim_token,
                    error=exc,
                )

    async def _process_event_session(
        self,
        db: Any,
        event: PortfolioValuationRequiredEvent,
        event_id: str,
        correlation_id: str,
        *,
        claim_token: str | None,
    ) -> None:
        async with db.begin():
            dependencies = self._dependency_factory.from_session(db)

            if not await dependencies.idempotency_repo.claim_event_processing(
                event_id,
                event.portfolio_id,
                SERVICE_NAME,
                correlation_id,
            ):
                logger.warning("Event %s already processed. Skipping.", event_id)
                return

            snapshot_result = await self._build_snapshot_for_event(
                dependencies,
                event,
                claim_token=claim_token,
            )
            if snapshot_result is None:
                return

            if not await self._complete_valuation_job(
                dependencies.repo,
                event,
                snapshot_result,
                claim_token=claim_token,
            ):
                return

            await self._persist_and_publish_snapshot(
                repo=dependencies.repo,
                outbox_repo=dependencies.outbox_repo,
                receipt_repo=dependencies.valuation_receipt_repo,
                snapshot_result=snapshot_result,
                correlation_id=correlation_id,
            )

    async def mark_failed_after_unexpected_error(
        self,
        event: PortfolioValuationRequiredEvent,
        exc: Exception,
        *,
        claim_token: str | None = None,
    ) -> None:
        async for db in self._session_provider():
            async with db.begin():
                dependencies = self._dependency_factory.from_session(db)
                outcome = await dependencies.repo.update_job_status(
                    event.portfolio_id,
                    event.security_id,
                    event.valuation_date,
                    event.epoch,
                    status=VALUATION_FAILED,
                    failure_reason=str(exc),
                    expected_claim_token=claim_token,
                )
                self._terminal_transition_applied(
                    outcome,
                    event,
                    side_effect_name="valuation failure transition",
                )

    async def _build_snapshot_for_event(
        self,
        dependencies: ValuationProcessorDependencies,
        event: PortfolioValuationRequiredEvent,
        *,
        claim_token: str | None,
    ) -> ValuationSnapshotResult | None:
        repo = dependencies.repo
        position_state = await self._position_state_for_event(repo, event)
        reference_data = await self._reference_data_for_event(repo, event)

        if not reference_data.instrument or not reference_data.portfolio:
            await self._mark_missing_reference_data(
                repo,
                event,
                reference_data,
                claim_token=claim_token,
            )
            return None

        snapshot = DailyPositionSnapshot(
            portfolio_id=event.portfolio_id,
            security_id=event.security_id,
            date=event.valuation_date,
            epoch=event.epoch,
            quantity=position_state.quantity,
            cost_basis=position_state.cost_basis,
            cost_basis_local=position_state.cost_basis_local,
        )

        return await self._value_snapshot(
            dependencies=dependencies,
            event=event,
            snapshot=snapshot,
            position=position_state,
            instrument=reference_data.instrument,
            portfolio=reference_data.portfolio,
            price=reference_data.price,
        )

    @staticmethod
    async def _position_state_for_event(
        repo: ValuationRepository,
        event: PortfolioValuationRequiredEvent,
    ):
        position_state = await repo.get_last_position_history_before_date(
            event.portfolio_id,
            event.security_id,
            event.valuation_date,
            event.epoch,
        )
        if position_state:
            return position_state
        raise DataNotFoundError(
            "Position history not found for "
            f"epoch {event.epoch} of {event.security_id} "
            f"on or before {event.valuation_date}"
        )

    @staticmethod
    async def _reference_data_for_event(
        repo: ValuationRepository,
        event: PortfolioValuationRequiredEvent,
    ) -> ValuationReferenceData:
        instrument = await repo.get_instrument(event.security_id)
        portfolio = await repo.get_portfolio(event.portfolio_id)
        price = None
        if (
            portfolio is None
            or resolve_optional_valuation_book_scope(
                tenant_id=portfolio.tenant_id,
                legal_book_id=portfolio.legal_book_id,
            )
            is None
        ):
            price = await repo.get_latest_price_for_position(
                event.security_id,
                event.valuation_date,
            )
        return ValuationReferenceData(
            instrument=instrument,
            portfolio=portfolio,
            price=price,
        )

    async def _mark_missing_reference_data(
        self,
        repo: ValuationRepository,
        event: PortfolioValuationRequiredEvent,
        reference_data: ValuationReferenceData,
        *,
        claim_token: str | None,
    ) -> None:
        error_msg = self._missing_reference_data_message(event, reference_data)
        VALUATION_JOBS_FAILED_TOTAL.labels(
            reason="missing_ref_data",
        ).inc()
        logger.error("%s Job will be marked FAILED.", error_msg)
        outcome = await repo.update_job_status(
            event.portfolio_id,
            event.security_id,
            event.valuation_date,
            event.epoch,
            VALUATION_FAILED,
            failure_reason=error_msg,
            expected_claim_token=claim_token,
        )
        self._terminal_transition_applied(
            outcome,
            event,
            side_effect_name="valuation failure completion",
        )

    @staticmethod
    def _missing_reference_data_message(
        event: PortfolioValuationRequiredEvent,
        reference_data: ValuationReferenceData,
    ) -> str:
        error_msg = "Missing critical data. "
        if not reference_data.instrument:
            error_msg += f"Instrument '{event.security_id}' not found. "
        if not reference_data.portfolio:
            error_msg += f"Portfolio '{event.portfolio_id}' not found."
        return error_msg

    async def _value_snapshot(
        self,
        *,
        dependencies: ValuationProcessorDependencies,
        event: PortfolioValuationRequiredEvent,
        snapshot: DailyPositionSnapshot,
        position: PositionHistory,
        instrument: Instrument,
        portfolio: Portfolio,
        price: MarketPrice | None,
    ) -> ValuationSnapshotResult:
        snapshot.valuation_fx_rate_date = None
        snapshot.valuation_fx_rate = None
        book_scope = resolve_optional_valuation_book_scope(
            tenant_id=portfolio.tenant_id,
            legal_book_id=portfolio.legal_book_id,
        )
        if book_scope is not None:
            VALUATION_QUOTE_AUTHORITY_PATH_TOTAL.labels(
                "authoritative",
                "exact_portfolio_scope",
            ).inc()
            try:
                return await self._value_authoritative_snapshot(
                    dependencies=dependencies,
                    event=event,
                    snapshot=snapshot,
                    position=position,
                    instrument=instrument,
                    portfolio=portfolio,
                    book_scope=book_scope,
                )
            except (
                MarketPriceSourceFactError,
                UnknownValuationPolicyError,
                UnsupportedValuationError,
                ValuationPolicyAssignmentError,
            ) as exc:
                snapshot.valuation_status = VALUATION_FAILED
                VALUATION_JOBS_FAILED_TOTAL.labels(
                    reason="authoritative_valuation_unsupported",
                ).inc()
                logger.warning(
                    "Authoritative valuation failed closed.",
                    extra={
                        "portfolio_id": event.portfolio_id,
                        "security_id": event.security_id,
                        "valuation_date": event.valuation_date.isoformat(),
                        "epoch": event.epoch,
                        "reason": str(exc),
                    },
                )
                return ValuationSnapshotResult(
                    snapshot=snapshot,
                    job_failure_reason=str(exc),
                )
        VALUATION_QUOTE_AUTHORITY_PATH_TOTAL.labels(
            "legacy",
            "unscoped_portfolio",
        ).inc()
        return await self._value_legacy_snapshot(
            repo=dependencies.repo,
            event=event,
            snapshot=snapshot,
            instrument=instrument,
            portfolio=portfolio,
            price=price,
        )

    async def _value_legacy_snapshot(
        self,
        *,
        repo: ValuationRepository,
        event: PortfolioValuationRequiredEvent,
        snapshot: DailyPositionSnapshot,
        instrument: Instrument,
        portfolio: Portfolio,
        price: MarketPrice | None,
    ) -> ValuationSnapshotResult:
        if self._is_flat_position(snapshot):
            self._apply_flat_position_valuation(snapshot)
            return ValuationSnapshotResult(
                snapshot=snapshot,
                job_failure_reason=None,
                receipt=build_legacy_valuation_receipt(
                    snapshot_identity=_snapshot_identity(snapshot)
                ),
            )
        if not price:
            snapshot.valuation_status = VALUATION_UNVALUED
            return ValuationSnapshotResult(snapshot=snapshot, job_failure_reason=None)
        if requires_bond_quote_authority(
            product_type=instrument.product_type,
            quantity=snapshot.quantity,
            cost_basis_reporting=snapshot.cost_basis,
            cost_basis_local=snapshot.cost_basis_local,
        ):
            snapshot.valuation_status = VALUATION_FAILED
            VALUATION_JOBS_FAILED_TOTAL.labels(
                reason="missing_bond_quote_authority",
            ).inc()
            logger.warning(
                "Legacy bond valuation failed closed because quote authority is unavailable.",
                extra={
                    "portfolio_id": event.portfolio_id,
                    "security_id": event.security_id,
                    "valuation_date": event.valuation_date.isoformat(),
                    "epoch": event.epoch,
                },
            )
            return ValuationSnapshotResult(
                snapshot=snapshot,
                job_failure_reason=BOND_QUOTE_AUTHORITY_REQUIRED_REASON,
            )

        instrument_currency = _normalize_currency_code(instrument.currency)
        portfolio_currency = _normalize_currency_code(portfolio.base_currency)
        price_currency = _normalize_currency_code(price.currency)
        fx_rate = await self._instrument_to_portfolio_fx_rate(
            repo=repo,
            event=event,
            instrument_currency=instrument_currency,
            portfolio_currency=portfolio_currency,
        )

        if instrument_currency != portfolio_currency and not fx_rate:
            return self._failed_missing_fx_snapshot(
                snapshot=snapshot,
                event=event,
                instrument_currency=instrument_currency,
                portfolio_currency=portfolio_currency,
            )

        valuation_result = ValuationLogic.calculate_valuation_components(
            quantity=snapshot.quantity,
            market_price=price.price,
            cost_basis_base=snapshot.cost_basis,
            cost_basis_local=snapshot.cost_basis_local,
            price_currency=price_currency,
            instrument_currency=instrument_currency,
            portfolio_currency=portfolio_currency,
            product_type=instrument.product_type,
            price_to_instrument_fx_rate=None,
            instrument_to_portfolio_fx_rate=fx_rate.rate if fx_rate else None,
        )
        if valuation_result:
            self._apply_valuation_result(
                snapshot=snapshot,
                price=price,
                event=event,
                valuation_result=valuation_result,
                fx_rate=fx_rate,
            )
            return ValuationSnapshotResult(
                snapshot=snapshot,
                job_failure_reason=None,
                receipt=build_legacy_valuation_receipt(
                    snapshot_identity=_snapshot_identity(snapshot),
                    calculation_lineage=valuation_result.calculation_lineage,
                ),
            )

        snapshot.valuation_status = VALUATION_FAILED
        failure_reason = (
            f"Valuation logic returned no result for {event.security_id} on {event.valuation_date}"
        )
        VALUATION_JOBS_FAILED_TOTAL.labels(
            reason="valuation_logic_failed",
        ).inc()
        return ValuationSnapshotResult(snapshot=snapshot, job_failure_reason=failure_reason)

    @staticmethod
    def _is_flat_position(snapshot: DailyPositionSnapshot) -> bool:
        """Return whether a quote-independent zero valuation is fully supported."""

        return is_quote_independent_flat_position(
            quantity=snapshot.quantity,
            cost_basis_reporting=snapshot.cost_basis,
            cost_basis_local=snapshot.cost_basis_local,
        )

    @staticmethod
    def _apply_flat_position_valuation(snapshot: DailyPositionSnapshot) -> None:
        """Persist an exact zero valuation without fabricating price authority."""

        snapshot.market_value = ZERO
        snapshot.market_value_local = ZERO
        snapshot.unrealized_gain_loss = ZERO
        snapshot.unrealized_gain_loss_local = ZERO
        snapshot.unrealized_price_gain_loss = ZERO
        snapshot.unrealized_fx_gain_loss = ZERO
        snapshot.valuation_status = VALUATION_VALUED_CURRENT

    async def _value_authoritative_snapshot(
        self,
        *,
        dependencies: ValuationProcessorDependencies,
        event: PortfolioValuationRequiredEvent,
        snapshot: DailyPositionSnapshot,
        position: PositionHistory,
        instrument: Instrument,
        portfolio: Portfolio,
        book_scope: ValuationBookScope,
    ) -> ValuationSnapshotResult:
        scope = ValuationAuthorityScope(
            tenant_id=book_scope.tenant_id,
            legal_book_id=book_scope.legal_book_id,
            security_id=event.security_id,
        )
        policy_request = ValuationPolicyAuthorityRequest(
            scope=scope,
            valuation_date=event.valuation_date,
        )
        price_request = MarketPriceAuthorityRequest(
            scope=scope,
            price_date=event.valuation_date,
        )
        policy_resolution = (
            await dependencies.valuation_policy_assignment_resolver.resolve_many([policy_request])
        )[policy_request.key]
        price_fact = (
            await dependencies.market_price_source_fact_resolver.resolve_many([price_request])
        )[price_request.key]
        instrument_currency = _normalize_currency_code(instrument.currency)
        if price_fact.currency != instrument_currency:
            raise UnsupportedValuationError(
                "authoritative market-price currency must match instrument currency"
            )
        portfolio_currency = _normalize_currency_code(portfolio.base_currency)
        fx_rate = await self._instrument_to_portfolio_fx_rate(
            repo=dependencies.repo,
            event=event,
            instrument_currency=instrument_currency,
            portfolio_currency=portfolio_currency,
        )
        if instrument_currency != portfolio_currency and fx_rate is None:
            return self._failed_missing_fx_snapshot(
                snapshot=snapshot,
                event=event,
                instrument_currency=instrument_currency,
                portfolio_currency=portfolio_currency,
            )
        evidence = dependencies.source_evidence_builder(
            assignment=policy_resolution.assignment,
            price_fact=price_fact,
            position=position,
            portfolio=portfolio,
            fx_rate=fx_rate,
        )
        result = calculate_authoritative_valuation(
            AuthoritativeValuationRequest(
                policy=policy_resolution.policy,
                price_fact=price_fact,
                signed_quantity=snapshot.quantity,
                cost_basis_reporting=snapshot.cost_basis,
                cost_basis_local=snapshot.cost_basis_local,
                reporting_currency=portfolio_currency,
                evidence=evidence,
                direct_source_to_reporting_fx_rate=fx_rate.rate if fx_rate else None,
            )
        )
        self._apply_authoritative_valuation_result(
            snapshot=snapshot,
            price_fact=price_fact,
            result=result,
            fx_rate=fx_rate,
        )
        assignment = policy_resolution.assignment
        return ValuationSnapshotResult(
            snapshot=snapshot,
            job_failure_reason=None,
            receipt=build_authoritative_valuation_receipt(
                snapshot_identity=_snapshot_identity(snapshot),
                policy_id=policy_resolution.policy.policy_id,
                policy_version=policy_resolution.policy.policy_version,
                assignment_version=assignment.assignment.assignment_version,
                assignment_content_hash=assignment.cache_key.assignment_content_hash,
                policy_assignment_source=assignment.assignment.source_reference(),
                price_fact=price_fact,
                calculation_lineage=result.calculation_lineage,
            ),
        )

    @staticmethod
    def _apply_authoritative_valuation_result(
        *,
        snapshot: DailyPositionSnapshot,
        price_fact: MarketPriceSourceFact,
        result: AuthoritativeValuationResult,
        fx_rate: FxRate | None,
    ) -> None:
        snapshot.market_price = price_fact.price
        snapshot.market_value = result.market_value_reporting
        snapshot.market_value_local = result.market_value_local
        snapshot.unrealized_gain_loss = result.unrealized_total_reporting
        snapshot.unrealized_gain_loss_local = result.unrealized_total_local
        snapshot.unrealized_price_gain_loss = result.unrealized_price_reporting
        snapshot.unrealized_fx_gain_loss = result.unrealized_fx_reporting
        snapshot.valuation_status = VALUATION_VALUED_CURRENT
        snapshot.valuation_fx_rate_date = fx_rate.rate_date if fx_rate is not None else None
        snapshot.valuation_fx_rate = fx_rate.rate if fx_rate is not None else None

    @staticmethod
    async def _instrument_to_portfolio_fx_rate(
        *,
        repo: ValuationRepository,
        event: PortfolioValuationRequiredEvent,
        instrument_currency: str,
        portfolio_currency: str,
    ) -> FxRate | None:
        if instrument_currency == portfolio_currency:
            return None
        return await repo.get_fx_rate(
            instrument_currency,
            portfolio_currency,
            event.valuation_date,
        )

    def _failed_missing_fx_snapshot(
        self,
        *,
        snapshot: DailyPositionSnapshot,
        event: PortfolioValuationRequiredEvent,
        instrument_currency: str,
        portfolio_currency: str,
    ) -> ValuationSnapshotResult:
        snapshot.valuation_status = VALUATION_FAILED
        failure_reason = (
            "Missing FX rate for "
            f"{instrument_currency}->{portfolio_currency} on or before {event.valuation_date}"
        )
        VALUATION_JOBS_FAILED_TOTAL.labels(
            reason="missing_fx_rate",
        ).inc()
        logger.error(
            "Missing required FX rate for valuation. Job will be marked FAILED.",
            extra={
                "portfolio_id": event.portfolio_id,
                "security_id": event.security_id,
                "valuation_date": str(event.valuation_date),
            },
        )
        return ValuationSnapshotResult(snapshot=snapshot, job_failure_reason=failure_reason)

    @staticmethod
    def _apply_valuation_result(
        *,
        snapshot: DailyPositionSnapshot,
        price: MarketPrice,
        event: PortfolioValuationRequiredEvent,
        valuation_result: ValuationComponents,
        fx_rate: FxRate | None,
    ) -> None:
        snapshot.market_price = price.price
        snapshot.market_value = valuation_result.market_value_base
        snapshot.market_value_local = valuation_result.market_value_local
        snapshot.unrealized_gain_loss = valuation_result.unrealized_total_base
        snapshot.unrealized_gain_loss_local = valuation_result.unrealized_total_local
        snapshot.unrealized_price_gain_loss = valuation_result.unrealized_price_base
        snapshot.unrealized_fx_gain_loss = valuation_result.unrealized_fx_base
        snapshot.valuation_status = (
            VALUATION_VALUED_CURRENT
            if price.price_date == event.valuation_date
            else VALUATION_VALUED_STALE
        )
        snapshot.valuation_fx_rate_date = fx_rate.rate_date if fx_rate is not None else None
        snapshot.valuation_fx_rate = fx_rate.rate if fx_rate is not None else None

    async def _complete_valuation_job(
        self,
        repo: ValuationRepository,
        event: PortfolioValuationRequiredEvent,
        snapshot_result: ValuationSnapshotResult,
        *,
        claim_token: str | None,
    ) -> bool:
        terminal_status = (
            VALUATION_FAILED
            if snapshot_result.snapshot.valuation_status in FAILED_JOB_STATUSES
            else VALUATION_JOB_COMPLETE
        )
        outcome = await repo.update_job_status(
            event.portfolio_id,
            event.security_id,
            event.valuation_date,
            event.epoch,
            terminal_status,
            failure_reason=snapshot_result.job_failure_reason,
            expected_claim_token=claim_token,
        )
        return self._terminal_transition_applied(
            outcome,
            event,
            side_effect_name="valuation completion side effects",
        )

    @staticmethod
    async def _persist_and_publish_snapshot(
        *,
        repo: ValuationRepository,
        outbox_repo: OutboxRepository,
        receipt_repo: ValuationReceiptRepository,
        snapshot_result: ValuationSnapshotResult,
        correlation_id: str,
    ) -> None:
        persisted_snapshot = await repo.upsert_daily_snapshot(snapshot_result.snapshot)
        if snapshot_result.receipt is None:
            await receipt_repo.delete(snapshot_id=persisted_snapshot.id)
        else:
            await receipt_repo.upsert(
                snapshot_id=persisted_snapshot.id,
                receipt=snapshot_result.receipt,
            )
        completion_event = DailyPositionSnapshotPersistedEvent.model_validate(persisted_snapshot)

        await outbox_repo.create_outbox_event(
            aggregate_type="DailyPositionSnapshot",
            aggregate_id=persisted_snapshot.portfolio_id,
            partition_key=portfolio_security_partition_key(
                persisted_snapshot.portfolio_id,
                persisted_snapshot.security_id,
            ),
            event_type="DailyPositionSnapshotPersisted",
            topic=KAFKA_VALUATION_SNAPSHOT_PERSISTED_TOPIC,
            payload=completion_event.model_dump(mode="json"),
            correlation_id=correlation_id,
        )

    async def _mark_no_position_job_skipped(
        self,
        *,
        db: Any,
        event: PortfolioValuationRequiredEvent,
        event_id: str,
        correlation_id: str,
        claim_token: str | None,
        error: DataNotFoundError,
    ) -> None:
        VALUATION_JOBS_SKIPPED_TOTAL.labels(reason="no_position_history").inc()
        logger.warning(
            "Skipping job due to missing position data: %s",
            error,
            extra={
                "portfolio_id": event.portfolio_id,
                "security_id": event.security_id,
                "date": event.valuation_date,
            },
        )
        async with db.begin():
            dependencies = self._dependency_factory.from_session(db)
            outcome = await dependencies.repo.update_job_status(
                event.portfolio_id,
                event.security_id,
                event.valuation_date,
                event.epoch,
                status=VALUATION_JOB_SKIPPED_NO_POSITION,
                failure_reason=str(error),
                expected_claim_token=claim_token,
            )
            if not self._terminal_transition_applied(
                outcome,
                event,
                side_effect_name="valuation no-position completion",
            ):
                return
            await dependencies.idempotency_repo.mark_event_processed(
                event_id, event.portfolio_id, SERVICE_NAME, correlation_id
            )

    @staticmethod
    def _terminal_transition_applied(
        outcome: ValuationJobTransitionOutcome,
        event: PortfolioValuationRequiredEvent,
        *,
        side_effect_name: str,
    ) -> bool:
        if outcome is ValuationJobTransitionOutcome.TERMINAL_APPLIED:
            return True
        reason = (
            "newer source work requested requeue"
            if outcome is ValuationJobTransitionOutcome.REQUEUED
            else "job ownership was lost"
        )
        logger.warning(
            "Skipping %s because %s.",
            side_effect_name,
            reason,
            extra={
                "portfolio_id": event.portfolio_id,
                "security_id": event.security_id,
                "valuation_date": str(event.valuation_date),
                "transition_outcome": outcome.value,
            },
        )
        return False


def _snapshot_identity(snapshot: DailyPositionSnapshot) -> ValuationSnapshotIdentity:
    return ValuationSnapshotIdentity(
        portfolio_id=snapshot.portfolio_id,
        security_id=snapshot.security_id,
        valuation_date=snapshot.date,
        epoch=snapshot.epoch,
    )
