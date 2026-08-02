"""Unit contracts for fixed-income source-authority write serialization."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from services.portfolio_transaction_processing_service.app.infrastructure.fixed_income_book_cost import (  # noqa: E501
    source_authority_repository,
)
from tests.test_support.fixed_income_book_cost import resolved_fixed_income_book_cost_inputs

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_authority_append_acquires_profile_fence_before_source_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    session = AsyncMock()
    insert_result = MagicMock()
    insert_result.scalar_one_or_none.return_value = 1
    session.execute.return_value = insert_result
    repository = source_authority_repository.SqlAlchemyLotAmortizedCostAuthorityRepository(session)
    profile_lock = AsyncMock(side_effect=lambda *_args: calls.append("profile"))
    monkeypatch.setattr(
        source_authority_repository,
        "acquire_lot_amortized_cost_profile_lock",
        profile_lock,
    )
    repository._acquire_source_lock = AsyncMock(  # type: ignore[method-assign]
        side_effect=lambda *_args: calls.append("source")
    )
    repository._record_for_identity = AsyncMock(  # type: ignore[method-assign]
        return_value=None
    )
    repository._latest_source_version = AsyncMock(  # type: ignore[method-assign]
        return_value=None
    )
    authority = resolved_fixed_income_book_cost_inputs().basis_fact

    await repository.append(authority)

    assert calls == ["profile", "source"]
    profile_lock.assert_awaited_once_with(session, authority.scope)
