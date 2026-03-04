# services/persistence_service/tests/integration/test_repositories.py
import pytest
from datetime import date, datetime
from decimal import Decimal
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from portfolio_common.database_models import Instrument as DBInstrument, Transaction as DBTransaction, Portfolio
from portfolio_common.events import InstrumentEvent, TransactionEvent, PortfolioEvent

from src.services.persistence_service.app.repositories.instrument_repository import InstrumentRepository
from src.services.persistence_service.app.repositories.transaction_db_repo import TransactionDBRepository
from src.services.persistence_service.app.repositories.portfolio_repository import PortfolioRepository

# Mark all tests in this file as async
pytestmark = pytest.mark.asyncio


# --- Fixtures for reusable data ---
@pytest.fixture
def instrument_event_buy():
    return InstrumentEvent(
        security_id="SEC_AAPL_001",
        name="Apple Inc. (Test)",
        isin="US0378331005",
        currency="USD",
        product_type="Equity"
    )

@pytest.fixture
def instrument_event_update():
    return InstrumentEvent(
        security_id="SEC_AAPL_001",
        name="Apple Inc. (Updated)", # Name changed
        isin="US0378331005_NEW", # ISIN changed
        currency="USD",
        product_type="Equity_Updated" # Product type changed
    )

# --- Integration Tests for InstrumentRepository (Now Async) ---

async def test_instrument_repository_create_new_instrument(clean_db, async_db_session: AsyncSession):
    """
    Tests that a new instrument can be successfully created.
    """
    repo = InstrumentRepository(async_db_session)
    
    event = InstrumentEvent(
        security_id="TEST_SEC_NEW",
        name="Test New Instrument",
        isin="TESTISIN123",
        currency="SGD",
        product_type="Bond"
    )
    
    await repo.create_or_update_instrument(event)
    await async_db_session.commit()
    
    stmt = select(DBInstrument).where(DBInstrument.security_id == "TEST_SEC_NEW")
    result = await async_db_session.execute(stmt)
    fetched_instrument = result.scalar_one_or_none()

    assert fetched_instrument is not None
    assert fetched_instrument.name == "Test New Instrument"


async def test_instrument_repository_upsert_update_existing_instrument(clean_db, async_db_session: AsyncSession, instrument_event_buy, instrument_event_update):
    """
    Tests that an existing instrument is updated when an UPSERT event with the same security_id occurs.
    """
    repo = InstrumentRepository(async_db_session)

    await repo.create_or_update_instrument(instrument_event_buy)
    await async_db_session.commit()

    await repo.create_or_update_instrument(instrument_event_update)
    await async_db_session.commit()

    stmt = select(DBInstrument).where(DBInstrument.security_id == "SEC_AAPL_001")
    result = await async_db_session.execute(stmt)
    fetched_instrument = result.scalar_one()

    assert fetched_instrument.name == "Apple Inc. (Updated)"
    assert fetched_instrument.product_type == "Equity_Updated"
    assert fetched_instrument.isin == "US0378331005_NEW"


async def test_instrument_repository_upsert_no_change_on_identical_event(clean_db, async_db_session: AsyncSession, instrument_event_buy):
    """
    Tests that an UPSERT event with identical data results in no effective change.
    """
    repo = InstrumentRepository(async_db_session)

    await repo.create_or_update_instrument(instrument_event_buy)
    await async_db_session.commit()
    
    await repo.create_or_update_instrument(instrument_event_buy)
    await async_db_session.commit()
    
    stmt = select(func.count()).select_from(select(DBInstrument).where(DBInstrument.security_id == "SEC_AAPL_001").subquery())
    result = await async_db_session.execute(stmt)
    count_in_db = result.scalar()
    assert count_in_db == 1

# --- NEW TEST (RFC 016) ---
async def test_instrument_repository_upserts_with_new_issuer_fields(clean_db, async_db_session: AsyncSession):
    """
    GIVEN an InstrumentEvent populated with the new issuer fields
    WHEN the create_or_update_instrument method is called
    THEN it should correctly persist all the new fields in the database.
    """
    # ARRANGE
    repo = InstrumentRepository(async_db_session)
    event_with_new_fields = InstrumentEvent(
        security_id="SEC_TEST_ISSUER",
        name="Issuer Test Instrument",
        isin="XS_ISSUER_TEST",
        currency="USD",
        product_type="Note",
        issuer_id="ISSUER_ABC",
        ultimate_parent_issuer_id="ULTIMATE_XYZ"
    )

    # ACT
    await repo.create_or_update_instrument(event_with_new_fields)
    await async_db_session.commit()

    # ASSERT
    stmt = select(DBInstrument).where(DBInstrument.security_id == "SEC_TEST_ISSUER")
    result = await async_db_session.execute(stmt)
    persisted_instrument = result.scalar_one_or_none()

    assert persisted_instrument is not None
    assert persisted_instrument.issuer_id == "ISSUER_ABC"
    assert persisted_instrument.ultimate_parent_issuer_id == "ULTIMATE_XYZ"

# --- NEW TEST (RFC 021) ---
async def test_portfolio_repository_persists_cost_basis_method(clean_db, async_db_session: AsyncSession):
    """
    GIVEN a PortfolioEvent with the new cost_basis_method field set to AVCO
    WHEN the create_or_update_portfolio method is called
    THEN it should correctly persist the new field in the database.
    """
    # ARRANGE
    repo = PortfolioRepository(async_db_session)
    event = PortfolioEvent(
        portfolio_id="PORT_AVCO_TEST_01",
        base_currency="USD",
        open_date=date(2025, 1, 1),
        client_id="CIF_AVCO_1",
        status="ACTIVE",
        risk_exposure="High",
        investment_time_horizon="Long",
        portfolio_type="Discretionary",
        booking_center_code="SG",
        cost_basis_method="AVCO"  # Explicitly set the new field
    )

    # ACT
    await repo.create_or_update_portfolio(event)
    await async_db_session.commit()

    # ASSERT
    stmt = select(Portfolio).where(Portfolio.portfolio_id == "PORT_AVCO_TEST_01")
    result = await async_db_session.execute(stmt)
    persisted_portfolio = result.scalar_one_or_none()

    assert persisted_portfolio is not None
    assert persisted_portfolio.cost_basis_method == "AVCO"

# --- Test for TransactionDBRepository (Now Async) ---
async def test_transaction_repository_is_idempotent(clean_db, async_db_session: AsyncSession):
    """
    Tests that creating the same transaction twice does not result in duplicates.
    """
    repo = TransactionDBRepository(async_db_session)

    test_portfolio = Portfolio(
        portfolio_id="PORT_T1", base_currency="USD", open_date=date(2024, 1, 1),
        risk_exposure="High", investment_time_horizon="Long", portfolio_type="Discretionary",
        booking_center_code="SG", client_id="CIF_123", status="ACTIVE"
    )
    async_db_session.add(test_portfolio)
    await async_db_session.commit()

    event = TransactionEvent(
        transaction_id="IDEMPOTENCY_TEST_01", portfolio_id="PORT_T1",
        instrument_id="INST_T1", security_id="SEC_T1",
        transaction_date=datetime(2025, 7, 31, 10, 0, 0), transaction_type="BUY",
        quantity=Decimal("100"), price=Decimal("10"), gross_transaction_amount=Decimal("1000"),
        trade_currency="USD", currency="USD",
    )

    # 1. Create the transaction for the first time
    await repo.create_or_update_transaction(event)
    await async_db_session.commit()

    stmt1 = select(func.count()).select_from(select(DBTransaction).where(DBTransaction.transaction_id == event.transaction_id).subquery())
    count1 = (await async_db_session.execute(stmt1)).scalar()
    assert count1 == 1

    # 2. Create the exact same transaction again
    await repo.create_or_update_transaction(event)
    await async_db_session.commit()

    stmt2 = select(func.count()).select_from(select(DBTransaction).where(DBTransaction.transaction_id == event.transaction_id).subquery())
    count2 = (await async_db_session.execute(stmt2)).scalar()
    assert count2 == 1


async def test_transaction_repository_persists_linkage_and_policy_metadata(
    clean_db, async_db_session: AsyncSession
):
    """
    BUY metadata required by RFC-059 Slice 2 must persist and remain updateable via UPSERT.
    """
    repo = TransactionDBRepository(async_db_session)

    async_db_session.add(
        Portfolio(
            portfolio_id="PORT_META_01",
            base_currency="USD",
            open_date=date(2024, 1, 1),
            risk_exposure="High",
            investment_time_horizon="Long",
            portfolio_type="Discretionary",
            booking_center_code="SG",
            client_id="CIF_META_01",
            status="ACTIVE",
        )
    )
    await async_db_session.commit()

    event = TransactionEvent(
        transaction_id="META_TEST_01",
        portfolio_id="PORT_META_01",
        instrument_id="INST_META_01",
        security_id="SEC_META_01",
        transaction_date=datetime(2026, 2, 28, 10, 0, 0),
        transaction_type="BUY",
        quantity=Decimal("100"),
        price=Decimal("10"),
        gross_transaction_amount=Decimal("1000"),
        trade_currency="USD",
        currency="USD",
        economic_event_id="EVT-2026-1001",
        linked_transaction_group_id="LTG-2026-2001",
        calculation_policy_id="BUY_DEFAULT_POLICY",
        calculation_policy_version="1.0.0",
        source_system="OMS_PRIMARY",
    )

    await repo.create_or_update_transaction(event)
    await async_db_session.commit()

    stmt = select(DBTransaction).where(DBTransaction.transaction_id == "META_TEST_01")
    persisted = (await async_db_session.execute(stmt)).scalar_one()
    assert persisted.economic_event_id == "EVT-2026-1001"
    assert persisted.linked_transaction_group_id == "LTG-2026-2001"
    assert persisted.calculation_policy_id == "BUY_DEFAULT_POLICY"
    assert persisted.calculation_policy_version == "1.0.0"
    assert persisted.source_system == "OMS_PRIMARY"

    updated = event.model_copy(
        update={
            "calculation_policy_version": "1.0.1",
            "source_system": "OMS_FALLBACK",
        }
    )
    await repo.create_or_update_transaction(updated)
    await async_db_session.commit()
    async_db_session.expire_all()

    persisted_after_upsert = (await async_db_session.execute(stmt)).scalar_one()
    assert persisted_after_upsert.calculation_policy_version == "1.0.1"
    assert persisted_after_upsert.source_system == "OMS_FALLBACK"
