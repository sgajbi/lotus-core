# tests/unit/services/query_service/services/test_transaction_service.py
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from portfolio_common.database_models import Cashflow, Transaction
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.query_service.app.repositories.transaction_repository import TransactionRepository
from src.services.query_service.app.services.transaction_service import TransactionService

pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_transaction_repo() -> AsyncMock:
    """Provides a mock TransactionRepository."""
    repo = AsyncMock(spec=TransactionRepository)
    repo.portfolio_exists.return_value = True
    # FIX: Provide full, valid data for the mock objects
    repo.get_transactions.return_value = [
        Transaction(
            transaction_id="T1",
            transaction_date=datetime(2025, 1, 10),
            transaction_type="BUY",
            instrument_id="I1",
            security_id="S1",
            quantity=Decimal(10),
            price=Decimal(100),
            gross_transaction_amount=Decimal(1000),
            currency="USD",
            cash_entry_mode="AUTO_GENERATE",
        ),
        Transaction(
            transaction_id="T2",
            transaction_date=datetime(2025, 1, 11),
            transaction_type="INTEREST",
            instrument_id="I2",
            security_id="S2",
            quantity=Decimal(0),
            price=Decimal(0),
            gross_transaction_amount=Decimal(125),
            currency="USD",
            cash_entry_mode="UPSTREAM_PROVIDED",
            external_cash_transaction_id="CASH-ENTRY-2026-0002",
            interest_direction="INCOME",
            withholding_tax_amount=Decimal("10"),
            other_interest_deductions_amount=Decimal("5"),
            net_interest_amount=Decimal("110"),
        ),
    ]
    repo.get_transactions_count.return_value = 25
    repo.get_latest_business_date.return_value = date(2025, 1, 15)
    return repo


async def test_get_transactions(mock_transaction_repo: AsyncMock):
    """
    GIVEN filters and pagination
    WHEN the transaction service is called
    THEN it should call the repository correctly and map the results to the response DTO.
    """
    # ARRANGE
    with patch(
        "src.services.query_service.app.services.transaction_service.TransactionRepository",
        return_value=mock_transaction_repo,
    ):
        service = TransactionService(AsyncMock(spec=AsyncSession))
        params = {
            "portfolio_id": "P1",
            "skip": 5,
            "limit": 10,
            "sort_by": "price",
            "sort_order": "asc",
            "security_id": "S1",
            "start_date": date(2025, 1, 1),
            "end_date": date(2025, 1, 31),
        }

        # ACT
        response_dto = await service.get_transactions(**params)

        # ASSERT
        mock_transaction_repo.get_transactions_count.assert_awaited_once_with(
            portfolio_id=params["portfolio_id"],
            security_id=params["security_id"],
            start_date=params["start_date"],
            end_date=params["end_date"],
            as_of_date=date(2025, 1, 15),
        )
        mock_transaction_repo.get_transactions.assert_awaited_once_with(
            **params,
            as_of_date=date(2025, 1, 15),
        )

        assert response_dto.total == 25
        assert response_dto.skip == 5
        assert response_dto.limit == 10
        assert len(response_dto.transactions) == 2
        assert response_dto.transactions[0].transaction_id == "T1"
        assert response_dto.transactions[0].cash_entry_mode == "AUTO_GENERATE"
        assert response_dto.transactions[1].cash_entry_mode == "UPSTREAM_PROVIDED"
        assert (
            response_dto.transactions[1].external_cash_transaction_id
            == "CASH-ENTRY-2026-0002"
        )
        assert response_dto.transactions[1].interest_direction == "INCOME"
        assert response_dto.transactions[1].withholding_tax_amount == Decimal("10")
        assert response_dto.transactions[1].other_interest_deductions_amount == Decimal("5")
        assert response_dto.transactions[1].net_interest_amount == Decimal("110")


async def test_get_transactions_maps_cashflow_dto_correctly(mock_transaction_repo: AsyncMock):
    """
    GIVEN a transaction with a related cashflow from the repository
    WHEN the transaction service processes it
    THEN it should correctly map the Cashflow model to the CashflowRecord DTO without errors.
    This test specifically prevents regressions of the bug found in the E2E workflow.
    """
    # ARRANGE
    # 1. Create a mock DB Transaction that has a related Cashflow object
    mock_db_transaction = Transaction(
        transaction_id="T_WITH_CASHFLOW",
        transaction_date=datetime(2025, 1, 10),
        transaction_type="DEPOSIT",
        instrument_id="CASH",
        security_id="CASH",
        quantity=1,
        price=1,
        gross_transaction_amount=1,
        currency="USD",
        # This is the critical part: attach a related cashflow object
        cashflow=Cashflow(
            amount=Decimal("5000"),
            currency="USD",
            classification="CASHFLOW_IN",
            timing="BOD",
            calculation_type="NET",
            is_position_flow=True,
            is_portfolio_flow=True,  # No 'level' field
        ),
    )
    mock_transaction_repo.get_transactions.return_value = [mock_db_transaction]
    mock_transaction_repo.get_transactions_count.return_value = 1

    with patch(
        "src.services.query_service.app.services.transaction_service.TransactionRepository",
        return_value=mock_transaction_repo,
    ):
        service = TransactionService(AsyncMock(spec=AsyncSession))

        # ACT
        # This call would have raised a 500 error before our DTO fix
        response_dto = await service.get_transactions(portfolio_id="P1", skip=0, limit=1)

        # ASSERT
        # 1. The primary assertion is that the call did not raise an exception.
        # 2. We also verify the DTO was populated correctly.
        assert len(response_dto.transactions) == 1
        retrieved_cashflow = response_dto.transactions[0].cashflow

        assert retrieved_cashflow is not None
        assert retrieved_cashflow.is_position_flow is True
        assert retrieved_cashflow.is_portfolio_flow is True
        assert hasattr(retrieved_cashflow, "level") is False


async def test_get_transactions_raises_when_portfolio_missing(mock_transaction_repo: AsyncMock):
    with patch(
        "src.services.query_service.app.services.transaction_service.TransactionRepository",
        return_value=mock_transaction_repo,
    ):
        mock_transaction_repo.portfolio_exists.return_value = False
        service = TransactionService(AsyncMock(spec=AsyncSession))

        with pytest.raises(ValueError, match="Portfolio with id P404 not found"):
            await service.get_transactions(portfolio_id="P404", skip=0, limit=10)


async def test_get_transactions_include_projected_skips_business_date_default(
    mock_transaction_repo: AsyncMock,
):
    with patch(
        "src.services.query_service.app.services.transaction_service.TransactionRepository",
        return_value=mock_transaction_repo,
    ):
        service = TransactionService(AsyncMock(spec=AsyncSession))

        await service.get_transactions(
            portfolio_id="P1",
            skip=0,
            limit=10,
            include_projected=True,
        )

        mock_transaction_repo.get_latest_business_date.assert_not_awaited()
        mock_transaction_repo.get_transactions_count.assert_awaited_once_with(
            portfolio_id="P1",
            security_id=None,
            start_date=None,
            end_date=None,
            as_of_date=None,
        )

