"""Read port for effective index definitions."""

from datetime import date
from typing import Protocol

from ..domain.index_definition import IndexDefinitionEvidence


class IndexDefinitionReader(Protocol):
    """Read effective index masters without exposing persistence models."""

    async def list_definitions(
        self,
        *,
        as_of_date: date,
        index_ids: list[str],
        index_currency: str | None,
        index_type: str | None,
        index_status: str | None,
    ) -> list[IndexDefinitionEvidence]: ...
