# tests/unit/services/query_service/services/test_transaction_service.py
from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from portfolio_common.database_models import Cashflow, Transaction
from portfolio_common.reconciliation_quality import COMPLETE, PARTIAL, UNKNOWN
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.query_service.app.repositories.transaction_repository import TransactionRepository
from src.services.query_service.app.services.transaction_service import TransactionService

pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_transaction_repo() -> AsyncMock:
    """Provides a mock TransactionRepository."""
    repo = AsyncMock(spec=TransactionRepository)
    repo.portfolio_exists.return_value = True
    repo.get_transactions.return_value = [
        Transaction(
            transaction_id="T1",
            transaction_date=datetime(2025, 1, 10),
            settlement_date=datetime(2025, 1, 12),
            transaction_type="BUY",
            instrument_id="I1",
            security_id="S1",
            quantity=Decimal(10),
            price=Decimal(100),
            gross_transaction_amount=Decimal(1000),
            gross_cost=Decimal(1000),
            trade_fee=Decimal("12.5"),
            realized_gain_loss=Decimal("250"),
            trade_currency="USD",
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
    repo.get_latest_evidence_timestamp.return_value = datetime(2025, 1, 16, 9, 30, tzinfo=UTC)
    repo.get_latest_business_date.return_value = date(2025, 1, 15)
    repo.get_latest_fx_rate.return_value = Decimal("1.36")
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
            "instrument_id": "I1",
            "security_id": "S1",
            "transaction_type": "FX_FORWARD",
            "component_type": "FX_CONTRACT_OPEN",
            "linked_transaction_group_id": "LTG-FX-001",
            "fx_contract_id": "FXC-001",
            "swap_event_id": "FXSWAP-001",
            "near_leg_group_id": "FXSWAP-001-NEAR",
            "far_leg_group_id": "FXSWAP-001-FAR",
            "start_date": date(2025, 1, 1),
            "end_date": date(2025, 1, 31),
        }

        # ACT
        response_dto = await service.get_transactions(**params)

        # ASSERT
        mock_transaction_repo.get_transactions_count.assert_awaited_once_with(
            portfolio_id=params["portfolio_id"],
            instrument_id=params["instrument_id"],
            security_id=params["security_id"],
            transaction_type=params["transaction_type"],
            component_type=params["component_type"],
            linked_transaction_group_id=params["linked_transaction_group_id"],
            fx_contract_id=params["fx_contract_id"],
            swap_event_id=params["swap_event_id"],
            near_leg_group_id=params["near_leg_group_id"],
            far_leg_group_id=params["far_leg_group_id"],
            start_date=params["start_date"],
            end_date=params["end_date"],
            as_of_date=date(2025, 1, 15),
        )
        mock_transaction_repo.get_transactions.assert_awaited_once_with(
            **params,
            as_of_date=date(2025, 1, 15),
        )
        mock_transaction_repo.get_latest_evidence_timestamp.assert_awaited_once_with(
            portfolio_id=params["portfolio_id"],
            instrument_id=params["instrument_id"],
            security_id=params["security_id"],
            transaction_type=params["transaction_type"],
            component_type=params["component_type"],
            linked_transaction_group_id=params["linked_transaction_group_id"],
            fx_contract_id=params["fx_contract_id"],
            swap_event_id=params["swap_event_id"],
            near_leg_group_id=params["near_leg_group_id"],
            far_leg_group_id=params["far_leg_group_id"],
            start_date=params["start_date"],
            end_date=params["end_date"],
            as_of_date=date(2025, 1, 15),
        )

        assert response_dto.total == 25
        assert response_dto.skip == 5
        assert response_dto.limit == 10
        assert len(response_dto.transactions) == 2
        assert response_dto.transactions[0].transaction_id == "T1"
        assert response_dto.transactions[0].settlement_date == datetime(2025, 1, 12)
        assert response_dto.transactions[0].trade_fee == Decimal("12.5")
        assert response_dto.transactions[0].trade_currency == "USD"
        assert response_dto.transactions[0].cash_entry_mode == "AUTO_GENERATE"
        assert response_dto.transactions[1].settlement_date is None
        assert response_dto.transactions[1].cash_entry_mode == "UPSTREAM_PROVIDED"
        assert response_dto.transactions[1].external_cash_transaction_id == "CASH-ENTRY-2026-0002"
        assert response_dto.transactions[1].interest_direction == "INCOME"
        assert response_dto.transactions[1].withholding_tax_amount == Decimal("10")
        assert response_dto.transactions[1].other_interest_deductions_amount == Decimal("5")
        assert response_dto.transactions[1].net_interest_amount == Decimal("110")
        assert response_dto.product_name == "TransactionLedgerWindow"
        assert response_dto.product_version == "v1"
        assert response_dto.as_of_date == date(2025, 1, 15)
        assert response_dto.reporting_currency is None
        assert response_dto.generated_at.tzinfo is not None
        assert response_dto.restatement_version == "current"
        assert response_dto.reconciliation_status == "UNKNOWN"
        assert response_dto.data_quality_status == PARTIAL
        assert response_dto.latest_evidence_timestamp == datetime(2025, 1, 16, 9, 30, tzinfo=UTC)
        assert response_dto.correlation_id is None


async def test_ledger_data_quality_status_classifies_complete_partial_and_empty_windows() -> None:
    assert (
        TransactionService._ledger_data_quality_status(
            total_count=2,
            returned_count=2,
            skip=0,
        )
        == COMPLETE
    )
    assert (
        TransactionService._ledger_data_quality_status(
            total_count=25,
            returned_count=10,
            skip=0,
        )
        == PARTIAL
    )
    assert (
        TransactionService._ledger_data_quality_status(
            total_count=25,
            returned_count=10,
            skip=10,
        )
        == PARTIAL
    )
    assert (
        TransactionService._ledger_data_quality_status(
            total_count=0,
            returned_count=0,
            skip=0,
        )
        == UNKNOWN
    )


async def test_get_transactions_classifies_complete_window(
    mock_transaction_repo: AsyncMock,
) -> None:
    mock_transaction_repo.get_transactions_count.return_value = 2

    with patch(
        "src.services.query_service.app.services.transaction_service.TransactionRepository",
        return_value=mock_transaction_repo,
    ):
        service = TransactionService(AsyncMock(spec=AsyncSession))

        response_dto = await service.get_transactions(portfolio_id="P1", skip=0, limit=10)

    assert response_dto.data_quality_status == COMPLETE


async def test_get_transactions_classifies_empty_window_as_unknown(
    mock_transaction_repo: AsyncMock,
) -> None:
    mock_transaction_repo.get_transactions.return_value = []
    mock_transaction_repo.get_transactions_count.return_value = 0
    mock_transaction_repo.get_latest_evidence_timestamp.return_value = None

    with patch(
        "src.services.query_service.app.services.transaction_service.TransactionRepository",
        return_value=mock_transaction_repo,
    ):
        service = TransactionService(AsyncMock(spec=AsyncSession))

        response_dto = await service.get_transactions(portfolio_id="P1", skip=0, limit=10)

    assert response_dto.data_quality_status == UNKNOWN
    assert response_dto.latest_evidence_timestamp is None


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
        assert response_dto.as_of_date == date(2025, 1, 15)


async def test_get_transactions_raises_when_portfolio_missing(mock_transaction_repo: AsyncMock):
    with patch(
        "src.services.query_service.app.services.transaction_service.TransactionRepository",
        return_value=mock_transaction_repo,
    ):
        mock_transaction_repo.portfolio_exists.return_value = False
        service = TransactionService(AsyncMock(spec=AsyncSession))

        with pytest.raises(LookupError, match="Portfolio with id P404 not found"):
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
            instrument_id=None,
            security_id=None,
            transaction_type=None,
            component_type=None,
            linked_transaction_group_id=None,
            fx_contract_id=None,
            swap_event_id=None,
            near_leg_group_id=None,
            far_leg_group_id=None,
            start_date=None,
            end_date=None,
            as_of_date=None,
        )
        mock_transaction_repo.get_latest_evidence_timestamp.assert_awaited_once_with(
            portfolio_id="P1",
            instrument_id=None,
            security_id=None,
            transaction_type=None,
            component_type=None,
            linked_transaction_group_id=None,
            fx_contract_id=None,
            swap_event_id=None,
            near_leg_group_id=None,
            far_leg_group_id=None,
            start_date=None,
            end_date=None,
            as_of_date=None,
        )


async def test_get_transactions_applies_reporting_currency_restated_fields(
    mock_transaction_repo: AsyncMock,
) -> None:
    with patch(
        "src.services.query_service.app.services.transaction_service.TransactionRepository",
        return_value=mock_transaction_repo,
    ):
        service = TransactionService(AsyncMock(spec=AsyncSession))

        response_dto = await service.get_transactions(
            portfolio_id="P1",
            skip=0,
            limit=10,
            reporting_currency="SGD",
        )

    first_transaction = response_dto.transactions[0]
    income_transaction = response_dto.transactions[1]

    assert response_dto.reporting_currency == "SGD"
    assert first_transaction.gross_transaction_amount_reporting_currency == Decimal("1360.00")
    assert first_transaction.gross_cost_reporting_currency == Decimal("1360.00")
    assert first_transaction.trade_fee_reporting_currency == Decimal("17.000")
    assert first_transaction.realized_gain_loss_reporting_currency == Decimal("340.00")
    assert income_transaction.gross_transaction_amount_reporting_currency == Decimal("170.00")
    assert income_transaction.withholding_tax_amount_reporting_currency == Decimal("13.60")
    assert income_transaction.other_interest_deductions_amount_reporting_currency == Decimal("6.80")
    assert income_transaction.net_interest_amount_reporting_currency == Decimal("149.60")
    assert mock_transaction_repo.get_latest_fx_rate.await_count == 1


async def test_get_transactions_raises_when_reporting_currency_rate_missing(
    mock_transaction_repo: AsyncMock,
) -> None:
    mock_transaction_repo.get_latest_fx_rate.return_value = None

    with patch(
        "src.services.query_service.app.services.transaction_service.TransactionRepository",
        return_value=mock_transaction_repo,
    ):
        service = TransactionService(AsyncMock(spec=AsyncSession))

        with pytest.raises(ValueError, match="FX rate not found for USD/SGD as of 2025-01-15"):
            await service.get_transactions(
                portfolio_id="P1",
                skip=0,
                limit=10,
                reporting_currency="SGD",
            )
