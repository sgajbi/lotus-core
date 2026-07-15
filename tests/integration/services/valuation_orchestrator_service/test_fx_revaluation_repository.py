"""PostgreSQL integration tests for direct-pair FX correction revaluation."""

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from portfolio_common.database_models import (
    Instrument,
    Portfolio,
    PositionHistory,
    PositionState,
    ReprocessingJob,
    Transaction,
)
from portfolio_common.position_state_repository import PositionStateRepository
from portfolio_common.reprocessing_job_repository import ReprocessingJobRepository
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.valuation_orchestrator_service.app.core.fx_revaluation_job_processor import (
    FxRevaluationJobProcessor,
)
from src.services.valuation_orchestrator_service.app.domain.fx_revaluation import (
    DirectCurrencyPair,
    FxRateCorrection,
)
from src.services.valuation_orchestrator_service.app.infrastructure.repositories import (
    fx_revaluation_repository,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.integration_db, pytest.mark.db_direct]


def _portfolio(portfolio_id: str, base_currency: str) -> Portfolio:
    return Portfolio(
        portfolio_id=portfolio_id,
        base_currency=base_currency,
        open_date=date(2026, 1, 1),
        risk_exposure="balanced",
        investment_time_horizon="long_term",
        portfolio_type="discretionary",
        booking_center_code="SG",
        client_id=f"CLIENT-{portfolio_id}",
        status="ACTIVE",
    )


def _instrument(security_id: str, currency: str) -> Instrument:
    return Instrument(
        security_id=security_id,
        name=f"{security_id} instrument",
        isin=f"ISIN-{security_id}",
        currency=currency,
        product_type="BOND",
        asset_class="FIXED_INCOME",
    )


def _transaction(transaction_id: str, portfolio_id: str, security_id: str) -> Transaction:
    return Transaction(
        transaction_id=transaction_id,
        portfolio_id=portfolio_id,
        instrument_id=security_id,
        security_id=security_id,
        transaction_date=date(2026, 4, 1),
        transaction_type="BUY",
        quantity=Decimal("10"),
        price=Decimal("100"),
        gross_transaction_amount=Decimal("1000"),
        trade_currency="USD",
        currency="USD",
    )


async def _seed_position(
    session: AsyncSession,
    *,
    portfolio_id: str,
    security_id: str,
    transaction_id: str,
    quantity: Decimal,
) -> None:
    session.add(
        PositionState(
            portfolio_id=portfolio_id,
            security_id=security_id,
            epoch=0,
            watermark_date=date(2026, 4, 1),
            status="CURRENT",
        )
    )
    session.add(
        PositionHistory(
            portfolio_id=portfolio_id,
            security_id=security_id,
            transaction_id=transaction_id,
            position_date=date(2026, 4, 1),
            epoch=0,
            quantity=quantity,
            cost_basis=Decimal("1000") if quantity > 0 else Decimal("0"),
            cost_basis_local=Decimal("1000") if quantity > 0 else Decimal("0"),
        )
    )


async def test_direct_pair_query_excludes_inverse_unrelated_and_closed_positions(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    async_db_session.add_all(
        [
            _portfolio("P-SGD", "SGD"),
            _portfolio("P-USD", "USD"),
            _instrument("USD-BOND", "USD"),
            _instrument("SGD-BOND", "SGD"),
            _transaction("TX-MATCH", "P-SGD", "USD-BOND"),
            _transaction("TX-BASE-SAME", "P-USD", "USD-BOND"),
            _transaction("TX-INVERSE", "P-USD", "SGD-BOND"),
            _transaction("TX-CLOSED", "P-SGD", "USD-BOND"),
        ]
    )
    await async_db_session.flush()
    await _seed_position(
        async_db_session,
        portfolio_id="P-SGD",
        security_id="USD-BOND",
        transaction_id="TX-MATCH",
        quantity=Decimal("10"),
    )
    await _seed_position(
        async_db_session,
        portfolio_id="P-USD",
        security_id="USD-BOND",
        transaction_id="TX-BASE-SAME",
        quantity=Decimal("10"),
    )
    await _seed_position(
        async_db_session,
        portfolio_id="P-USD",
        security_id="SGD-BOND",
        transaction_id="TX-INVERSE",
        quantity=Decimal("10"),
    )
    await async_db_session.flush()
    async_db_session.add(
        PositionHistory(
            portfolio_id="P-SGD",
            security_id="USD-BOND",
            transaction_id="TX-CLOSED",
            position_date=date(2026, 4, 9),
            epoch=0,
            quantity=Decimal("0"),
            cost_basis=Decimal("0"),
            cost_basis_local=Decimal("0"),
        )
    )
    await async_db_session.flush()
    repository = fx_revaluation_repository.SqlAlchemyFxRevaluationRepository(async_db_session)

    keys = await repository.find_open_position_keys(
        pair=DirectCurrencyPair("USD", "SGD"),
        effective_date=date(2026, 4, 10),
    )

    assert keys == []


async def test_direct_pair_query_returns_open_matching_position_epoch(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    async_db_session.add_all(
        [
            _portfolio("P-SGD", "SGD"),
            _instrument("USD-BOND", "USD"),
            _transaction("TX-MATCH", "P-SGD", "USD-BOND"),
        ]
    )
    await async_db_session.flush()
    await _seed_position(
        async_db_session,
        portfolio_id="P-SGD",
        security_id="USD-BOND",
        transaction_id="TX-MATCH",
        quantity=Decimal("10"),
    )
    await async_db_session.flush()
    repository = fx_revaluation_repository.SqlAlchemyFxRevaluationRepository(async_db_session)

    keys = await repository.find_open_position_keys(
        pair=DirectCurrencyPair("USD", "SGD"),
        effective_date=date(2026, 4, 10),
    )

    assert [(key.portfolio_id, key.security_id, key.epoch) for key in keys] == [
        ("P-SGD", "USD-BOND", 0)
    ]


async def test_replay_impact_includes_position_first_opened_after_correction(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    async_db_session.add_all(
        [
            _portfolio("P-SGD", "SGD"),
            _instrument("USD-BOND", "USD"),
            _transaction("TX-LATER", "P-SGD", "USD-BOND"),
        ]
    )
    await async_db_session.flush()
    async_db_session.add(
        PositionState(
            portfolio_id="P-SGD",
            security_id="USD-BOND",
            epoch=0,
            watermark_date=date(2026, 4, 12),
            status="CURRENT",
        )
    )
    async_db_session.add(
        PositionHistory(
            portfolio_id="P-SGD",
            security_id="USD-BOND",
            transaction_id="TX-LATER",
            position_date=date(2026, 4, 12),
            epoch=0,
            quantity=Decimal("10"),
            cost_basis=Decimal("1000"),
            cost_basis_local=Decimal("1000"),
        )
    )
    await async_db_session.flush()
    repository = fx_revaluation_repository.SqlAlchemyFxRevaluationRepository(async_db_session)

    keys = await repository.find_affected_position_keys(
        pair=DirectCurrencyPair("USD", "SGD"),
        earliest_impacted_date=date(2026, 4, 10),
    )

    assert [(key.portfolio_id, key.security_id, key.epoch) for key in keys] == [
        ("P-SGD", "USD-BOND", 0)
    ]


async def test_durable_replay_coalesces_pair_to_earliest_date_and_latest_lineage(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    repository = fx_revaluation_repository.SqlAlchemyFxRevaluationRepository(async_db_session)
    pair = DirectCurrencyPair("USD", "SGD")
    await repository.stage_durable_replay(
        correction=FxRateCorrection(
            pair=pair,
            effective_date=date(2026, 4, 10),
            content_hash="sha256:" + ("a" * 64),
            generated_at=datetime(2026, 4, 10, 8, tzinfo=timezone.utc),
        ),
        correlation_id="corr-later-date",
    )
    await repository.stage_durable_replay(
        correction=FxRateCorrection(
            pair=pair,
            effective_date=date(2026, 4, 8),
            content_hash="sha256:" + ("b" * 64),
            generated_at=datetime(2026, 4, 10, 9, tzinfo=timezone.utc),
        ),
        correlation_id="corr-latest-correction",
    )
    await async_db_session.commit()

    jobs = (
        (
            await async_db_session.execute(
                select(ReprocessingJob).where(
                    ReprocessingJob.job_type == "RESET_FX_WATERMARKS",
                    ReprocessingJob.status == "PENDING",
                )
            )
        )
        .scalars()
        .all()
    )

    assert len(jobs) == 1
    assert jobs[0].payload == {
        "from_currency": "USD",
        "to_currency": "SGD",
        "earliest_impacted_date": "2026-04-08",
        "content_hash": "sha256:" + ("b" * 64),
        "generated_at": "2026-04-10T09:00:00+00:00",
    }
    assert jobs[0].correlation_id == "corr-latest-correction"


async def test_claimed_fx_job_resets_exact_affected_watermark_and_completes(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    async_db_session.add_all(
        [
            _portfolio("P-SGD", "SGD"),
            _instrument("USD-BOND", "USD"),
            _transaction("TX-MATCH", "P-SGD", "USD-BOND"),
        ]
    )
    await async_db_session.flush()
    await _seed_position(
        async_db_session,
        portfolio_id="P-SGD",
        security_id="USD-BOND",
        transaction_id="TX-MATCH",
        quantity=Decimal("10"),
    )
    state = await async_db_session.get(PositionState, ("P-SGD", "USD-BOND"))
    assert state is not None
    state.watermark_date = date(2026, 4, 15)
    claimed_job = ReprocessingJob(
        job_type="RESET_FX_WATERMARKS",
        payload={
            "from_currency": "USD",
            "to_currency": "SGD",
            "earliest_impacted_date": "2026-04-10",
            "content_hash": "sha256:" + ("a" * 64),
            "generated_at": "2026-04-10T08:00:00+00:00",
        },
        status="PROCESSING",
        correlation_id="corr-fx-worker",
    )
    async_db_session.add(claimed_job)
    await async_db_session.flush()

    await FxRevaluationJobProcessor().process(
        job=claimed_job,
        jobs=ReprocessingJobRepository(async_db_session),
        watermarks=PositionStateRepository(async_db_session),
        revaluation=fx_revaluation_repository.SqlAlchemyFxRevaluationRepository(
            async_db_session
        ),
    )
    await async_db_session.commit()

    refreshed_state = await async_db_session.get(PositionState, ("P-SGD", "USD-BOND"))
    refreshed_job = await async_db_session.get(ReprocessingJob, claimed_job.id)
    assert refreshed_state is not None
    assert refreshed_state.watermark_date == date(2026, 4, 9)
    assert refreshed_state.status == "REPROCESSING"
    assert refreshed_job is not None
    assert refreshed_job.status == "COMPLETE"
