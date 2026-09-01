from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.services.ingestion_service.app.application import (
    validate_transaction_portfolio_ownership as subject,
)
from tests.test_support.tenant import TEST_TENANT_CONTEXT, TEST_TENANT_ID

pytestmark = pytest.mark.asyncio


async def test_validator_accepts_only_portfolios_owned_by_admitted_tenant() -> None:
    reader = SimpleNamespace(
        read_owned_portfolio_ids=AsyncMock(return_value=frozenset({"PORT-1", "PORT-2"}))
    )

    await subject.ValidateTransactionPortfolioOwnership(reader).execute(
        tenant_context=TEST_TENANT_CONTEXT,
        portfolio_ids=["PORT-1", "PORT-2", "PORT-1"],
    )

    reader.read_owned_portfolio_ids.assert_awaited_once_with(
        tenant_id=TEST_TENANT_ID,
        portfolio_ids=("PORT-1", "PORT-2"),
    )


async def test_validator_rejects_cross_tenant_or_missing_portfolios_before_publish() -> None:
    reader = SimpleNamespace(read_owned_portfolio_ids=AsyncMock(return_value=frozenset({"PORT-1"})))

    with pytest.raises(subject.TransactionPortfolioOwnershipRejected) as exc_info:
        await subject.ValidateTransactionPortfolioOwnership(reader).execute(
            tenant_context=TEST_TENANT_CONTEXT,
            portfolio_ids=["PORT-1", "PORT-OTHER-TENANT", "PORT-MISSING"],
        )

    assert exc_info.value.portfolio_ids == ("PORT-OTHER-TENANT", "PORT-MISSING")
