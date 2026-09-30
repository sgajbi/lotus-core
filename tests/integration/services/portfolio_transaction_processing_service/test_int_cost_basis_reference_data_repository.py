"""Verify cost-basis reference data is loaded atomically in one SQL round trip."""

from __future__ import annotations

import asyncio
from datetime import date

import pytest
from portfolio_common.database_models import CashAccountMaster
from portfolio_common.domain.cost_basis_method import CostBasisMethod
from sqlalchemy import event as sqlalchemy_event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.services.ingestion_service.app.services.reference_data_ingestion_service import (
    ReferenceDataIngestionService,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.cost_basis import (
    SqlAlchemyCostBasisReferenceDataRepository,
)
from src.services.portfolio_transaction_processing_service.app.ports import (
    CostBasisInstrumentReference,
    CostBasisPortfolioReference,
    CostBasisReferenceData,
)
from tests.test_support.tenant import TEST_LEGAL_BOOK_ID, TEST_TENANT_ID
from tests.test_support.transaction_processing import instrument_record, portfolio_record

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.integration_db,
    pytest.mark.db_direct,
    pytest.mark.regression,
]


async def test_reference_bundle_uses_one_statement_and_maps_both_owners(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    async_db_session.add_all(
        [
            portfolio_record(
                "PORT-REF-BUNDLE-01",
                base_currency="SGD",
                cost_basis_method="AVCO",
                legal_book_id=TEST_LEGAL_BOOK_ID,
            ),
            instrument_record(
                "SEC-REF-BUNDLE-01",
                name="Reference Bundle Equity",
                isin="SG0000000001",
                currency="SGD",
            ),
        ]
    )
    await async_db_session.commit()
    statements: list[str] = []

    def capture_statement(
        _conn,
        _cursor,
        statement,
        _parameters,
        _context,
        _executemany,
    ) -> None:
        statements.append(" ".join(statement.split()))

    sync_engine = async_db_session.bind.sync_engine
    sqlalchemy_event.listen(sync_engine, "before_cursor_execute", capture_statement)
    try:
        reference_data = await SqlAlchemyCostBasisReferenceDataRepository(
            async_db_session
        ).get_cost_basis_reference_data(
            portfolio_id="PORT-REF-BUNDLE-01",
            security_id=" SEC-REF-BUNDLE-01 ",
        )
    finally:
        sqlalchemy_event.remove(sync_engine, "before_cursor_execute", capture_statement)

    assert reference_data == CostBasisReferenceData(
        portfolio=CostBasisPortfolioReference(
            portfolio_id="PORT-REF-BUNDLE-01",
            base_currency="SGD",
            cost_basis_method=CostBasisMethod.AVCO,
            tenant_id=TEST_TENANT_ID,
            legal_book_id=TEST_LEGAL_BOOK_ID,
        ),
        instrument=CostBasisInstrumentReference(
            security_id="SEC-REF-BUNDLE-01",
            product_type="EQUITY",
            asset_class="Equity",
            currency="SGD",
        ),
    )
    assert len(statements) == 1
    assert "LEFT OUTER JOIN instruments" in statements[0]


async def test_reference_bundle_keeps_portfolio_when_instrument_is_absent(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    async_db_session.add(portfolio_record("PORT-REF-BUNDLE-02", legal_book_id=TEST_LEGAL_BOOK_ID))
    await async_db_session.commit()

    reference_data = await SqlAlchemyCostBasisReferenceDataRepository(
        async_db_session
    ).get_cost_basis_reference_data(
        portfolio_id="PORT-REF-BUNDLE-02",
        security_id="MISSING",
    )

    assert reference_data is not None
    assert reference_data.portfolio.portfolio_id == "PORT-REF-BUNDLE-02"
    assert reference_data.instrument is None


async def test_settlement_cash_account_lookup_enforces_scope_and_effective_window(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    portfolio_id = "PORT-CASH-ACCOUNT-AUTHORITY-01"
    as_of_date = date(2026, 4, 9)
    async_db_session.add(portfolio_record(portfolio_id, legal_book_id=TEST_LEGAL_BOOK_ID))
    await async_db_session.flush()
    account_definitions = (
        ("CASH-OPEN-BOUNDARY", "ACTIVE", as_of_date, None),
        ("CASH-CLOSE-BOUNDARY", "ACTIVE", date(2026, 1, 1), as_of_date),
        ("CASH-NULL-WINDOW", "ACTIVE", None, None),
        ("CASH-FUTURE", "ACTIVE", date(2026, 4, 10), None),
        ("CASH-EXPIRED", "ACTIVE", date(2026, 1, 1), date(2026, 4, 8)),
        ("CASH-INACTIVE", "CLOSED", date(2026, 1, 1), None),
    )
    async_db_session.add_all(
        [
            CashAccountMaster(
                cash_account_id=cash_account_id,
                portfolio_id=portfolio_id,
                security_id=f"SEC-{cash_account_id}",
                display_name=cash_account_id,
                account_currency="USD",
                lifecycle_status=lifecycle_status,
                opened_on=opened_on,
                closed_on=closed_on,
            )
            for cash_account_id, lifecycle_status, opened_on, closed_on in account_definitions
        ]
        + [
            instrument_record(
                f"SEC-{cash_account_id}",
                name=f"{cash_account_id} instrument",
                isin=f"US{index:010d}",
                currency="USD",
                product_type="CASH",
                asset_class="Cash",
            )
            for index, (cash_account_id, *_rest) in enumerate(account_definitions, start=1)
        ]
    )
    await async_db_session.commit()
    repository = SqlAlchemyCostBasisReferenceDataRepository(async_db_session)

    for cash_account_id in (
        "CASH-OPEN-BOUNDARY",
        "CASH-CLOSE-BOUNDARY",
        "CASH-NULL-WINDOW",
    ):
        reference = await repository.get_settlement_cash_account_reference(
            portfolio_id=portfolio_id,
            tenant_id=TEST_TENANT_ID,
            cash_account_id=cash_account_id,
            as_of_date=as_of_date,
        )
        assert reference is not None
        assert reference.cash_account_id == cash_account_id
        assert reference.security_id == f"SEC-{cash_account_id}"
        assert reference.account_currency == "USD"
        assert reference.instrument_product_type == "CASH"
        assert reference.instrument_currency == "USD"

    for cash_account_id in ("CASH-FUTURE", "CASH-EXPIRED", "CASH-INACTIVE"):
        assert (
            await repository.get_settlement_cash_account_reference(
                portfolio_id=portfolio_id,
                tenant_id=TEST_TENANT_ID,
                cash_account_id=cash_account_id,
                as_of_date=as_of_date,
            )
            is None
        )

    assert (
        await repository.get_settlement_cash_account_reference(
            portfolio_id=portfolio_id,
            tenant_id="tenant-not-admitted",
            cash_account_id="CASH-OPEN-BOUNDARY",
            as_of_date=as_of_date,
        )
        is None
    )


async def test_settlement_authority_lock_fences_supported_cash_account_update(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    """A generated-child UoW cannot commit behind a concurrently changed mapping."""

    portfolio_id = "PORT-CASH-AUTHORITY-LOCK-01"
    cash_account_id = "CASH-AUTHORITY-LOCK-01"
    security_id = "CASH-USD-AUTHORITY-LOCK-01"
    async_db_session.add_all(
        [
            portfolio_record(portfolio_id, legal_book_id=TEST_LEGAL_BOOK_ID),
            instrument_record(
                security_id,
                name="USD authority lock cash",
                isin="US0000000099",
                currency="USD",
                product_type="CASH",
                asset_class="Cash",
            ),
        ]
    )
    await async_db_session.flush()
    async_db_session.add(
        CashAccountMaster(
            cash_account_id=cash_account_id,
            portfolio_id=portfolio_id,
            security_id=security_id,
            display_name="USD authority lock cash account",
            account_currency="USD",
            account_role="SETTLEMENT",
            lifecycle_status="ACTIVE",
            opened_on=date(2026, 1, 1),
            source_system="test",
            source_record_id="cash-authority-lock-01",
        )
    )
    await async_db_session.commit()

    locked_reference = await SqlAlchemyCostBasisReferenceDataRepository(
        async_db_session
    ).get_settlement_cash_account_reference(
        portfolio_id=portfolio_id,
        tenant_id=TEST_TENANT_ID,
        cash_account_id=cash_account_id,
        as_of_date=date(2026, 4, 9),
    )
    assert locked_reference is not None
    assert locked_reference.security_id == security_id

    session_factory = async_sessionmaker(
        bind=async_db_session.bind,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async def supported_update() -> None:
        async with session_factory() as writer_session:
            await ReferenceDataIngestionService(writer_session).upsert_cash_account_masters(
                [
                    {
                        "cash_account_id": cash_account_id,
                        "portfolio_id": portfolio_id,
                        "security_id": security_id,
                        "display_name": "USD authority lock cash account updated",
                        "account_currency": "USD",
                        "account_role": "SETTLEMENT",
                        "lifecycle_status": "ACTIVE",
                        "opened_on": date(2026, 1, 1),
                        "closed_on": None,
                        "source_system": "test-update",
                        "source_record_id": "cash-authority-lock-02",
                    }
                ]
            )

    update_task = asyncio.create_task(supported_update())
    done, _pending = await asyncio.wait({update_task}, timeout=0.2)
    assert not done, "supported mapping update bypassed the processing transaction's row lock"

    await async_db_session.commit()
    await asyncio.wait_for(update_task, timeout=5)

    refreshed = await SqlAlchemyCostBasisReferenceDataRepository(
        async_db_session
    ).get_settlement_cash_account_reference(
        portfolio_id=portfolio_id,
        tenant_id=TEST_TENANT_ID,
        cash_account_id=cash_account_id,
        as_of_date=date(2026, 4, 9),
    )
    assert refreshed is not None
    assert refreshed.security_id == security_id
