from __future__ import annotations

from datetime import date
from typing import Any

from ..dtos.reference_integration_dto import IndexCatalogResponse
from .reference_data_mappers import index_definition_response


async def resolve_index_catalog_response(
    *,
    repository: Any,
    as_of_date: date,
    index_ids: list[str],
    index_currency: str | None,
    index_type: str | None,
    index_status: str | None,
) -> IndexCatalogResponse:
    rows = await repository.list_index_definitions(
        as_of_date=as_of_date,
        index_ids=index_ids,
        index_currency=index_currency,
        index_type=index_type,
        index_status=index_status,
    )
    return build_index_catalog_response(
        as_of_date=as_of_date,
        rows=rows,
    )


def build_index_catalog_response(
    *,
    as_of_date: date,
    rows: list[Any],
) -> IndexCatalogResponse:
    return IndexCatalogResponse(
        as_of_date=as_of_date,
        records=[index_definition_response(row) for row in rows],
    )
