from __future__ import annotations

from datetime import date
from typing import Any

from ..dtos.reference_integration_dto import IndexCatalogResponse
from .reference_data_mappers import index_definition_response


def build_index_catalog_response(
    *,
    as_of_date: date,
    rows: list[Any],
) -> IndexCatalogResponse:
    return IndexCatalogResponse(
        as_of_date=as_of_date,
        records=[index_definition_response(row) for row in rows],
    )
