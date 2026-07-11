"""Tests for the QCP classification taxonomy SQL adapter."""

from __future__ import annotations

from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.query_control_plane_service.app.infrastructure import (
    classification_taxonomy_sources,
)


class _Result:
    def __init__(self, rows: list[object]) -> None:
        self._rows = rows

    def scalars(self) -> _Result:
        return self

    def all(self) -> list[object]:
        return self._rows


@pytest.mark.asyncio
async def test_reader_applies_effective_scope_and_maps_domain_evidence() -> None:
    source_timestamp = datetime(2026, 4, 10, 9, tzinfo=UTC)
    row = SimpleNamespace(
        classification_set_id="wm_global_taxonomy_v1",
        taxonomy_scope="instrument",
        dimension_name="asset_class",
        dimension_value="equity",
        dimension_description="Listed equity",
        effective_from=date(2026, 1, 1),
        effective_to=None,
        quality_status="accepted",
        source_timestamp=source_timestamp,
        source_vendor="lotus-reference",
        source_record_id="taxonomy-1",
        created_at=source_timestamp,
        updated_at=source_timestamp,
    )
    session = AsyncMock(spec=AsyncSession)
    session.execute.return_value = _Result([row])
    reader = classification_taxonomy_sources.SqlAlchemyClassificationTaxonomyReader(session)

    evidence = await reader.list_effective(
        as_of_date=date(2026, 4, 10),
        taxonomy_scope="instrument",
    )

    assert evidence[0].dimension_value == "equity"
    assert evidence[0].observed_at == source_timestamp
    statement = session.execute.await_args.args[0]
    sql = str(statement.compile(compile_kwargs={"literal_binds": True}))
    assert "classification_taxonomy.effective_from <= '2026-04-10'" in sql
    assert "classification_taxonomy.effective_to IS NULL" in sql
    assert "classification_taxonomy.effective_to >= '2026-04-10'" in sql
    assert "classification_taxonomy.taxonomy_scope = 'instrument'" in sql
    assert "classification_taxonomy.dimension_value ASC" in sql
