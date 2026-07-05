from __future__ import annotations

from ..application.lookup_catalog import LookupCatalogResult
from ..dtos.lookup_dto import LookupItem, LookupResponse


def lookup_response_from_result(result: LookupCatalogResult) -> LookupResponse:
    return LookupResponse(items=[LookupItem(id=item.id, label=item.label) for item in result.items])
