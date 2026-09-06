"""PostgreSQL contract tests for lot amortized-cost source authority."""

from __future__ import annotations

import runpy
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from portfolio_common.database_models import (
    LotAmortizedCostAuthorityRecord,
    LotDisposalAllocationRecord,
    LotDisposalReceiptRecord,
    OutboxEvent,
    PositionLotState,
    Transaction,
)
from portfolio_common.event_contracts import FixedIncomeBookCostAuthorityEvent
from portfolio_common.events import TransactionEvent
from sqlalchemy import func, inspect, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.services.portfolio_transaction_processing_service.app.application import (
    ReplayBookedTransactionCommand,
    TransactionProcessingIntent,
    TransactionProcessingStatus,
)
from src.services.portfolio_transaction_processing_service.app.application.fixed_income_book_cost import (  # noqa: E501
    HandleFixedIncomeBookCostAuthorityEventUseCase,
    MaterializeLotAmortizedCostProfileUseCase,
)
from src.services.portfolio_transaction_processing_service.app.delivery.kafka.transaction_event_mapper import (  # noqa: E501
    map_transaction_event,
)
from src.services.portfolio_transaction_processing_service.app.domain.fixed_income_book_cost import (  # noqa: E501
    AmortizedCostPolicyRegistry,
    LotAmortizedCostBasisFact,
    allocate_recognized_lot_book_cost,
    resolve_lot_amortized_cost_inputs,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.cost_basis import (
    SqlAlchemyCostBasisProcessingStateRepository,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.fixed_income_book_cost import (  # noqa: E501
    ConflictingLotAmortizedCostAuthorityError,
    SqlAlchemyFixedIncomeBookCostAuthorityUnitOfWork,
    SqlAlchemyLotAmortizedCostAuthorityRepository,
    SqlAlchemyLotAmortizedCostProfileRepository,
)
from src.services.portfolio_transaction_processing_service.app.ports import (
    LotAmortizedCostAuthorityAppendOutcome,
)
from src.services.portfolio_transaction_processing_service.app.runtime.dependency_composition import (  # noqa: E501
    build_replay_booked_transaction_use_case,
)
from tests.test_support.fixed_income_book_cost import (
    fixed_income_book_cost_scope,
    resolved_fixed_income_book_cost_inputs,
)
from tests.test_support.transaction_processing import (
    booked_transaction_event,
    persist_and_process_booked_transaction,
    transaction_processing_test_context,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.integration_db, pytest.mark.db_direct]

MIGRATION = (
    Path(__file__).resolve().parents[4]
    / "alembic"
    / "versions"
    / "c140b2c3d50d_feat_add_lot_amortized_cost_authority.py"
)
PREDECESSOR_MIGRATION = (
    Path(__file__).resolve().parents[4]
    / "alembic"
    / "versions"
    / "c139b2c3d50c_feat_add_lot_amortized_cost_profiles.py"
)


class _CapturingReplayProducer:
    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []

    def publish_message(
        self,
        *,
        topic: str,
        key: str,
        value: dict[str, Any],
        headers: list[tuple[str, bytes]],
    ) -> None:
        self.messages.append({"topic": topic, "key": key, "value": value, "headers": headers})

    def flush(self) -> int:
        return 0


@pytest.fixture
def authority_schema(clean_db, db_engine) -> None:
    """Apply the branch migration when the cached local integration image predates it."""

    with db_engine.begin() as connection:
        if inspect(connection).has_table("lot_amortized_cost_authority"):
            return
        if not inspect(connection).has_table("lot_amortized_cost_profiles"):
            predecessor = runpy.run_path(str(PREDECESSOR_MIGRATION))
            predecessor["upgrade"].__globals__["op"] = Operations(
                MigrationContext.configure(connection)
            )
            predecessor["upgrade"]()
        else:
            operations = Operations(MigrationContext.configure(connection))
            existing_portfolio_constraints = {
                item["name"] for item in inspect(connection).get_unique_constraints("portfolios")
            }
            if "uq_portfolios_book_scope_identity" not in existing_portfolio_constraints:
                operations.create_unique_constraint(
                    "uq_portfolios_book_scope_identity",
                    "portfolios",
                    ["tenant_id", "legal_book_id", "portfolio_id"],
                )
            existing_lot_constraints = {
                item["name"]
                for item in inspect(connection).get_unique_constraints("position_lot_state")
            }
            if "uq_position_lot_scope_identity" not in existing_lot_constraints:
                operations.create_unique_constraint(
                    "uq_position_lot_scope_identity",
                    "position_lot_state",
                    ["lot_id", "portfolio_id", "security_id"],
                )
        migration = runpy.run_path(str(MIGRATION))
        migration["upgrade"].__globals__["op"] = Operations(MigrationContext.configure(connection))
        migration["upgrade"]()


async def test_repository_round_trips_every_authority_family_and_exact_retry(
    clean_db,
    authority_schema,
    async_db_session: AsyncSession,
) -> None:
    await _seed_source_lot(async_db_session)
    repository = SqlAlchemyLotAmortizedCostAuthorityRepository(async_db_session)
    resolved = resolved_fixed_income_book_cost_inputs()
    authorities = (
        resolved.assignment,
        resolved.basis_fact,
        resolved.schedule_fact,
        resolved.yield_fact,
    )

    for authority in authorities:
        assert authority is not None
        assert await repository.append(authority) is LotAmortizedCostAuthorityAppendOutcome.APPENDED
        assert (
            await repository.append(authority) is LotAmortizedCostAuthorityAppendOutcome.UNCHANGED
        )

    bundle = await repository.load(fixed_income_book_cost_scope())
    assert bundle.assignments == (resolved.assignment,)
    assert bundle.basis_facts == (resolved.basis_fact,)
    assert bundle.schedule_facts == (resolved.schedule_fact,)
    assert bundle.yield_facts == (resolved.yield_fact,)
    assert await async_db_session.scalar(
        text("SELECT COUNT(*) FROM lot_amortized_cost_authority")
    ) == len(authorities)


@pytest.mark.lifecycle
async def test_authority_correction_survives_restart_with_one_durable_replay_intent(
    clean_db,
    authority_schema,
    async_db_session: AsyncSession,
) -> None:
    production_lot_id = "LOT-AMORT_BUY_001"
    await _seed_source_lot(async_db_session, lot_id=production_lot_id)
    fixture_inputs = resolved_fixed_income_book_cost_inputs()
    assert fixture_inputs.yield_fact is not None
    scope = replace(fixture_inputs.cache_key.scope, lot_id=production_lot_id)
    resolved = resolve_lot_amortized_cost_inputs(
        assignments=[replace(fixture_inputs.assignment, scope=scope)],
        basis_facts=[replace(fixture_inputs.basis_fact, scope=scope)],
        schedule_facts=[replace(fixture_inputs.schedule_fact, scope=scope)],
        yield_facts=[replace(fixture_inputs.yield_fact, scope=scope)],
        scope=scope,
        effective_date=fixture_inputs.cache_key.effective_date,
        policy=fixture_inputs.policy,
    )
    authority = SqlAlchemyLotAmortizedCostAuthorityRepository(async_db_session)
    for source in (
        resolved.assignment,
        resolved.basis_fact,
        resolved.schedule_fact,
        resolved.yield_fact,
    ):
        assert source is not None
        assert await authority.append(source) is LotAmortizedCostAuthorityAppendOutcome.APPENDED
    initial_profile = await MaterializeLotAmortizedCostProfileUseCase(
        authority=authority,
        profiles=SqlAlchemyLotAmortizedCostProfileRepository(async_db_session),
    ).execute(
        scope=resolved.cache_key.scope,
        effective_date=resolved.cache_key.effective_date,
        policy=resolved.policy,
    )
    await async_db_session.commit()

    disposal = booked_transaction_event(
        transaction_id="AMORT_SELL_001",
        portfolio_id=resolved.cache_key.scope.portfolio_id,
        security_id=resolved.cache_key.scope.security_id,
        transaction_date=datetime(2026, 7, 1, 8, tzinfo=timezone.utc),
        transaction_type="SELL",
        quantity="10",
        price="1",
        gross_amount="10",
        trade_currency="SGD",
    )
    initial_context = transaction_processing_test_context(async_db_session)
    initial_disposal = await persist_and_process_booked_transaction(
        session=async_db_session,
        context=initial_context,
        event=disposal,
        event_id="transactions.persisted-0-47801",
        correlation_id="corr-amortized-cost-disposal-01",
    )
    assert initial_disposal.status is TransactionProcessingStatus.PROCESSED
    assert async_db_session.bind is not None
    session_factory = async_sessionmaker(async_db_session.bind, expire_on_commit=False)
    async with session_factory() as checkpoint_session:
        initial_checkpoint = await SqlAlchemyCostBasisProcessingStateRepository(
            checkpoint_session
        ).get_cost_basis_processing_checkpoint(
            portfolio_id=scope.portfolio_id,
            security_id=scope.security_id,
        )
    assert initial_checkpoint is not None

    corrected_basis = replace(
        resolved.basis_fact,
        initial_clean_cost_local=Decimal("96"),
        redemption_value_local=Decimal("98.9484536082"),
        source=replace(
            resolved.basis_fact.source,
            source_revision="revision-2",
            fact_version=2,
        ),
    )

    first = await HandleFixedIncomeBookCostAuthorityEventUseCase(
        unit_of_work_factory=lambda: SqlAlchemyFixedIncomeBookCostAuthorityUnitOfWork(
            session_factory
        ),
        policies=AmortizedCostPolicyRegistry((resolved.policy,)),
        correction_replay_enabled=True,
    ).execute(
        _basis_event(corrected_basis),
        correlation_id="corr-amortized-cost-correction-01",
    )

    assert first.correction_replay_intent is not None
    assert first.correction_replay_intent.anchor.transaction_id == "AMORT_SELL_001"
    command_id = first.correction_replay_intent.command_id
    async with session_factory() as restarted_session:
        staged = tuple(
            (
                await restarted_session.scalars(
                    select(OutboxEvent).where(
                        OutboxEvent.aggregate_type == "FixedIncomeBookCostCorrectionReplay"
                    )
                )
            ).all()
        )
    assert len(staged) == 1
    assert staged[0].aggregate_id == command_id
    assert staged[0].status == "PENDING"
    assert staged[0].payload["source_authority_event_content_hash"] == (
        _basis_event(corrected_basis).content_hash()
    )

    producer = _CapturingReplayProducer()
    restarted_context = transaction_processing_test_context(async_db_session)
    replay_result = await build_replay_booked_transaction_use_case(
        session_factory=restarted_context.session_factory,
        kafka_producer=producer,
    ).execute(
        ReplayBookedTransactionCommand(
            transaction_id=first.correction_replay_intent.anchor.transaction_id,
            correlation_id="corr-amortized-cost-correction-01",
            repair_delivery_id=command_id,
        )
    )
    assert replay_result.transaction_id == "AMORT_SELL_001"
    replay_event = TransactionEvent.model_validate(producer.messages[0]["value"])
    replay_event = replay_event.model_copy(update={"tenant_id": scope.tenant_id})
    repair_command = map_transaction_event(
        replay_event,
        event_id="transactions.persisted-0-47802",
        correlation_id="corr-amortized-cost-correction-01",
        processing_intent=TransactionProcessingIntent.REPAIR,
        repair_delivery_id=command_id,
    )
    repaired = await restarted_context.use_case.execute(repair_command)
    duplicate_repair = await restarted_context.use_case.execute(repair_command)

    assert repaired.status is TransactionProcessingStatus.PROCESSED
    assert duplicate_repair.status is TransactionProcessingStatus.DUPLICATE

    duplicate = await HandleFixedIncomeBookCostAuthorityEventUseCase(
        unit_of_work_factory=lambda: SqlAlchemyFixedIncomeBookCostAuthorityUnitOfWork(
            session_factory
        ),
        policies=AmortizedCostPolicyRegistry((resolved.policy,)),
        correction_replay_enabled=True,
    ).execute(_basis_event(corrected_basis))

    assert duplicate.persistence.unchanged_count == 1
    assert duplicate.correction_replay_intent is None
    async with session_factory() as verification_session:
        assert (
            await verification_session.scalar(
                select(func.count())
                .select_from(OutboxEvent)
                .where(OutboxEvent.aggregate_type == "FixedIncomeBookCostCorrectionReplay")
            )
            == 1
        )
        receipts = tuple(
            (
                await verification_session.scalars(
                    select(LotDisposalReceiptRecord)
                    .where(LotDisposalReceiptRecord.disposal_transaction_id == "AMORT_SELL_001")
                    .order_by(LotDisposalReceiptRecord.receipt_version)
                )
            ).all()
        )
        head_allocation = await verification_session.scalar(
            select(LotDisposalAllocationRecord).where(
                LotDisposalAllocationRecord.receipt_id == receipts[-1].receipt_id,
                LotDisposalAllocationRecord.receipt_version == receipts[-1].receipt_version,
            )
        )
        corrected_profile = await SqlAlchemyLotAmortizedCostProfileRepository(
            verification_session
        ).latest(scope)
        repaired_lot = await verification_session.scalar(
            select(PositionLotState).where(PositionLotState.lot_id == production_lot_id)
        )
        repaired_transaction = await verification_session.scalar(
            select(Transaction).where(Transaction.transaction_id == "AMORT_SELL_001")
        )
        repaired_checkpoint = await SqlAlchemyCostBasisProcessingStateRepository(
            verification_session
        ).get_cost_basis_processing_checkpoint(
            portfolio_id=scope.portfolio_id,
            security_id=scope.security_id,
        )
    assert [receipt.receipt_version for receipt in receipts] == [1, 2]
    assert receipts[0].consumed_cost_local != receipts[1].consumed_cost_local
    assert head_allocation is not None
    assert corrected_profile is not None
    assert repaired_lot is not None
    assert repaired_transaction is not None
    uninterrupted_control = allocate_recognized_lot_book_cost(
        corrected_profile,
        disposal_date=disposal.transaction_date.date(),
        original_quantity=Decimal("100"),
        open_quantity_before=Decimal("100"),
        consumed_quantity=disposal.quantity,
        book_cost_fx_rate_to_base=Decimal("1"),
    )
    assert corrected_profile.profile_version > initial_profile.profile_version
    assert head_allocation.amortized_cost_profile_version == corrected_profile.profile_version
    assert head_allocation.consumed_cost_local == uninterrupted_control.consumed_cost_local
    assert head_allocation.consumed_cost_base == uninterrupted_control.consumed_cost_base
    assert (
        head_allocation.amortized_cost_calculation_lineage
        == uninterrupted_control.calculation_lineage.lineage_payload()
    )
    assert repaired_transaction.realized_gain_loss_local == (
        disposal.gross_transaction_amount - uninterrupted_control.consumed_cost_local
    )
    assert repaired_transaction.realized_gain_loss == (
        disposal.gross_transaction_amount - uninterrupted_control.consumed_cost_base
    )
    assert repaired_lot.open_quantity == uninterrupted_control.residual_quantity
    assert repaired_lot.amortized_book_carrying_local == (uninterrupted_control.residual_cost_local)
    assert repaired_lot.amortized_book_carrying_base == uninterrupted_control.residual_cost_base
    assert repaired_lot.amortized_cost_profile_version == corrected_profile.profile_version
    assert repaired_checkpoint == initial_checkpoint


async def test_repository_appends_corrections_and_rejects_version_collision(
    clean_db,
    authority_schema,
    async_db_session: AsyncSession,
) -> None:
    await _seed_source_lot(async_db_session)
    repository = SqlAlchemyLotAmortizedCostAuthorityRepository(async_db_session)
    first = resolved_fixed_income_book_cost_inputs().basis_fact
    corrected = replace(
        first,
        source=replace(
            first.source,
            fact_version=2,
            source_revision="revision-2",
        ),
        initial_clean_cost_local=first.initial_clean_cost_local + 1,
    )
    collision = replace(first, source=replace(first.source, source_revision="different"))
    version_three = replace(
        first,
        source=replace(
            first.source,
            source_record_id="AMORT_LOT_001_BASIS_LATE",
            fact_version=3,
            source_revision="revision-3",
        ),
    )
    late_version_two = replace(
        version_three,
        source=replace(
            version_three.source,
            fact_version=2,
            source_revision="revision-2",
        ),
    )

    await repository.append(first)
    assert await repository.append(corrected) is LotAmortizedCostAuthorityAppendOutcome.APPENDED
    with pytest.raises(
        ConflictingLotAmortizedCostAuthorityError,
        match="different content",
    ):
        await repository.append(collision)
    await repository.append(version_three)
    with pytest.raises(
        ConflictingLotAmortizedCostAuthorityError,
        match="increase monotonically",
    ):
        await repository.append(late_version_two)

    bundle = await repository.load(fixed_income_book_cost_scope())
    assert bundle.basis_facts == (first, corrected, version_three)


async def test_repository_rejects_persisted_payload_tampering_and_wrong_scope(
    clean_db,
    authority_schema,
    async_db_session: AsyncSession,
) -> None:
    await _seed_source_lot(async_db_session)
    repository = SqlAlchemyLotAmortizedCostAuthorityRepository(async_db_session)
    basis = resolved_fixed_income_book_cost_inputs().basis_fact
    await repository.append(basis)
    await async_db_session.execute(
        update(LotAmortizedCostAuthorityRecord)
        .where(LotAmortizedCostAuthorityRecord.authority_content_hash == basis.content_hash())
        .values(
            authority_payload={
                "currency": "SGD",
                "discount_origin": "MARKET_DISCOUNT",
                "fees_in_basis_local": "0",
                "initial_clean_cost_local": "96",
                "redemption_value_local": "100",
            }
        )
    )

    with pytest.raises(
        ConflictingLotAmortizedCostAuthorityError,
        match="immutable hash",
    ):
        await repository.load(fixed_income_book_cost_scope())
    with pytest.raises(TypeError, match="scope"):
        await repository.load(object())  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("family", "nested_period"),
    [
        ("assignment", False),
        ("basis", False),
        ("schedule", False),
        ("yield", False),
        ("schedule", True),
    ],
)
async def test_repository_rejects_unsupported_authority_payload_keys(
    clean_db,
    authority_schema,
    async_db_session: AsyncSession,
    family: str,
    nested_period: bool,
) -> None:
    await _seed_source_lot(async_db_session)
    repository = SqlAlchemyLotAmortizedCostAuthorityRepository(async_db_session)
    resolved = resolved_fixed_income_book_cost_inputs()
    authorities = {
        "assignment": resolved.assignment,
        "basis": resolved.basis_fact,
        "schedule": resolved.schedule_fact,
        "yield": resolved.yield_fact,
    }
    authority = authorities[family]
    assert authority is not None
    await repository.append(authority)
    record = await async_db_session.scalar(
        select(LotAmortizedCostAuthorityRecord).where(
            LotAmortizedCostAuthorityRecord.authority_content_hash == authority.content_hash()
        )
    )
    assert record is not None
    payload = dict(record.authority_payload)
    if nested_period:
        period_payloads = payload["periods"]
        assert isinstance(period_payloads, list)
        assert all(isinstance(period, dict) for period in period_payloads)
        periods = [dict(period) for period in period_payloads]
        periods[0]["unsupported"] = "tampered"
        payload["periods"] = periods
    else:
        payload["unsupported"] = "tampered"
    await async_db_session.execute(
        update(LotAmortizedCostAuthorityRecord)
        .where(LotAmortizedCostAuthorityRecord.id == record.id)
        .values(authority_payload=payload)
    )

    with pytest.raises(
        ConflictingLotAmortizedCostAuthorityError,
        match="keys do not match the immutable schema",
    ):
        await repository.load(fixed_income_book_cost_scope())


async def test_repository_rejects_non_string_optional_period_rate(
    clean_db,
    authority_schema,
    async_db_session: AsyncSession,
) -> None:
    await _seed_source_lot(async_db_session)
    repository = SqlAlchemyLotAmortizedCostAuthorityRepository(async_db_session)
    schedule = resolved_fixed_income_book_cost_inputs().schedule_fact
    await repository.append(schedule)
    record = await async_db_session.scalar(
        select(LotAmortizedCostAuthorityRecord).where(
            LotAmortizedCostAuthorityRecord.authority_content_hash == schedule.content_hash()
        )
    )
    assert record is not None
    payload = dict(record.authority_payload)
    period_payloads = payload["periods"]
    assert isinstance(period_payloads, list)
    assert all(isinstance(period, dict) for period in period_payloads)
    periods = [dict(period) for period in period_payloads]
    periods[0]["supplied_period_rate"] = 0
    payload["periods"] = periods
    await async_db_session.execute(
        update(LotAmortizedCostAuthorityRecord)
        .where(LotAmortizedCostAuthorityRecord.id == record.id)
        .values(authority_payload=payload)
    )

    with pytest.raises(
        ConflictingLotAmortizedCostAuthorityError,
        match="supplied_period_rate must be a string or null",
    ):
        await repository.load(fixed_income_book_cost_scope())


@pytest.mark.parametrize(
    ("family", "field", "nested_period"),
    [
        ("basis", "initial_clean_cost_local", False),
        ("basis", "fees_in_basis_local", False),
        ("basis", "redemption_value_local", False),
        ("yield", "annual_yield", False),
        ("schedule", "year_fraction", True),
        ("schedule", "cash_coupon_local", True),
        ("schedule", "supplied_period_rate", True),
    ],
)
async def test_repository_rejects_noncanonical_decimal_payload_text(
    clean_db,
    authority_schema,
    async_db_session: AsyncSession,
    family: str,
    field: str,
    nested_period: bool,
) -> None:
    await _seed_source_lot(async_db_session)
    repository = SqlAlchemyLotAmortizedCostAuthorityRepository(async_db_session)
    resolved = resolved_fixed_income_book_cost_inputs()
    schedule = resolved.schedule_fact
    if field == "supplied_period_rate":
        schedule = replace(
            schedule,
            periods=(
                replace(schedule.periods[0], supplied_period_rate=Decimal("0.01")),
                *schedule.periods[1:],
            ),
        )
    authorities = {
        "basis": resolved.basis_fact,
        "schedule": schedule,
        "yield": resolved.yield_fact,
    }
    authority = authorities[family]
    assert authority is not None
    await repository.append(authority)
    record = await async_db_session.scalar(
        select(LotAmortizedCostAuthorityRecord).where(
            LotAmortizedCostAuthorityRecord.authority_content_hash == authority.content_hash()
        )
    )
    assert record is not None
    payload = dict(record.authority_payload)
    target = payload
    if nested_period:
        period_payloads = payload["periods"]
        assert isinstance(period_payloads, list)
        assert all(isinstance(period, dict) for period in period_payloads)
        periods = [dict(period) for period in period_payloads]
        target = next(period for period in periods if period[field] is not None)
        payload["periods"] = periods
    original = target[field]
    assert isinstance(original, str)
    target[field] = f"+{original}"
    await async_db_session.execute(
        update(LotAmortizedCostAuthorityRecord)
        .where(LotAmortizedCostAuthorityRecord.id == record.id)
        .values(authority_payload=payload)
    )

    with pytest.raises(
        ConflictingLotAmortizedCostAuthorityError,
        match="must use canonical decimal text",
    ):
        await repository.load(fixed_income_book_cost_scope())


async def test_repository_rejects_normalized_payload_tampering(
    clean_db,
    authority_schema,
    async_db_session: AsyncSession,
) -> None:
    await _seed_source_lot(async_db_session)
    repository = SqlAlchemyLotAmortizedCostAuthorityRepository(async_db_session)
    basis = resolved_fixed_income_book_cost_inputs().basis_fact
    await repository.append(basis)
    record = await async_db_session.scalar(
        select(LotAmortizedCostAuthorityRecord).where(
            LotAmortizedCostAuthorityRecord.authority_content_hash == basis.content_hash()
        )
    )
    assert record is not None
    payload = dict(record.authority_payload)
    payload["currency"] = "sgd"
    await async_db_session.execute(
        update(LotAmortizedCostAuthorityRecord)
        .where(LotAmortizedCostAuthorityRecord.id == record.id)
        .values(authority_payload=payload)
    )

    with pytest.raises(
        ConflictingLotAmortizedCostAuthorityError,
        match="does not use its canonical representation",
    ):
        await repository.load(fixed_income_book_cost_scope())


def _basis_event(basis: LotAmortizedCostBasisFact) -> FixedIncomeBookCostAuthorityEvent:
    return FixedIncomeBookCostAuthorityEvent.model_validate(
        {
            "event_type": "fixed_income.book_cost.authority.received",
            "schema_version": "1.0.0",
            "authority": {
                "authority_type": "CLEAN_COST_BASIS",
                "header": {
                    "scope": {
                        "tenant_id": basis.scope.tenant_id,
                        "legal_book_id": basis.scope.legal_book_id,
                        "portfolio_id": basis.scope.portfolio_id,
                        "security_id": basis.scope.security_id,
                        "lot_id": basis.scope.lot_id,
                    },
                    "source": {
                        "source_system": basis.source.source_system,
                        "source_record_id": basis.source.source_record_id,
                        "source_revision": basis.source.source_revision,
                        "source_version": basis.source.fact_version,
                        "observed_at": basis.source.observed_at.isoformat(),
                    },
                    "status": basis.fact_status.value,
                    "valid_from": basis.valid_from.isoformat(),
                    "valid_to": basis.valid_to.isoformat() if basis.valid_to else None,
                },
                "currency": basis.currency,
                "initial_clean_cost_local": str(basis.initial_clean_cost_local),
                "fees_in_basis_local": str(basis.fees_in_basis_local),
                "redemption_value_local": str(basis.redemption_value_local),
                "discount_origin": basis.discount_origin.value,
            },
        }
    )


async def _seed_source_lot(
    session: AsyncSession,
    *,
    lot_id: str = "AMORT_LOT_001",
) -> None:
    await session.execute(
        text(
            """
            INSERT INTO portfolios (
                portfolio_id, tenant_id, legal_book_id, base_currency, open_date,
                risk_exposure, investment_time_horizon, portfolio_type,
                booking_center_code, client_id, is_leverage_allowed, status
            ) VALUES (
                'AMORT_PORTFOLIO', 'TENANT_SG', 'BOOK_SG_PB', 'SGD',
                DATE '2026-01-01', 'MODERATE', 'LONG_TERM', 'ADVISORY',
                'SG', 'CLIENT_001', FALSE, 'ACTIVE'
            )
            """
        )
    )
    await session.execute(
        text(
            """
            INSERT INTO instruments (security_id, name, isin, currency, product_type)
            VALUES (
                'AMORT_BOND_001', 'Amortization Test Bond',
                'XS000AMORT001', 'SGD', 'BOND'
            )
            """
        )
    )
    await session.execute(
        text(
            """
            INSERT INTO transactions (
                transaction_id, portfolio_id, instrument_id, security_id,
                transaction_type, quantity, price, gross_transaction_amount,
                trade_currency, currency, transaction_date
            ) VALUES (
                'AMORT_BUY_001', 'AMORT_PORTFOLIO', 'AMORT_BOND_001',
                'AMORT_BOND_001', 'BUY', 100, 97, 9700, 'SGD', 'SGD',
                TIMESTAMPTZ '2026-01-01 08:00:00+00'
            )
            """
        )
    )
    await session.execute(
        text(
            """
            INSERT INTO position_lot_state (
                lot_id, source_transaction_id, portfolio_id, instrument_id,
                security_id, acquisition_date, original_quantity, open_quantity,
                lot_cost_local, lot_cost_base, accrued_interest_paid_local
            ) VALUES (
                :lot_id, 'AMORT_BUY_001', 'AMORT_PORTFOLIO',
                'AMORT_BOND_001', 'AMORT_BOND_001', DATE '2026-01-01',
                100, 100, 9700, 9700, 0
            )
            """
        ),
        {"lot_id": lot_id},
    )
