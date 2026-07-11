"""SQL adapter tests for effective index definitions."""

from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.query_control_plane_service.app.infrastructure.index_definition_sources import (
    SqlAlchemyIndexDefinitionReader,
)


@pytest.mark.asyncio
async def test_catalog_query_normalizes_scope_and_ranks_one_current_row_per_index() -> None:
    row = SimpleNamespace(
        index_id="IDX_MSCI_WORLD_TR",
        index_name="MSCI World Total Return",
        index_currency="USD",
        index_type="equity_index",
        index_status="active",
        index_provider="MSCI",
        index_market="global_developed",
        classification_set_id="taxonomy_1",
        classification_labels={"asset_class": "equity"},
        effective_from=date(2026, 1, 1),
        effective_to=None,
        quality_status="accepted",
        source_timestamp=datetime(2026, 4, 10, 9, tzinfo=UTC),
        source_vendor="MSCI",
        source_record_id="index:world:2026",
        created_at=datetime(2026, 4, 10, 8, tzinfo=UTC),
        updated_at=datetime(2026, 4, 10, 10, tzinfo=UTC),
    )
    result = MagicMock()
    result.scalars.return_value.all.return_value = [row]
    session = MagicMock()
    session.execute = AsyncMock(return_value=result)

    records = await SqlAlchemyIndexDefinitionReader(session).list_definitions(
        as_of_date=date(2026, 4, 10),
        index_ids=[" IDX_MSCI_WORLD_TR ", "IDX_MSCI_WORLD_TR", " "],
        index_currency=" usd ",
        index_type=" Equity_Index ",
        index_status=" ACTIVE ",
    )

    assert records[0].classification_labels == {"asset_class": "equity"}
    sql = str(session.execute.await_args.args[0])
    assert "row_number() OVER" in sql
    assert "index_definitions.index_id IN" in sql
    assert "index_definitions.index_currency" in sql
    assert "index_definitions.index_type" in sql
    assert "index_definitions.index_status" in sql
    assert "index_definitions.source_timestamp DESC NULLS LAST" in sql
    assert "index_definitions.id DESC" in sql
    assert "ORDER BY index_definitions.index_id ASC" in sql
