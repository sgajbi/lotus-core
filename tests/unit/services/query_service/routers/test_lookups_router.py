from __future__ import annotations

from src.services.query_service.app.application.lookup_catalog import (
    LookupCatalogItem,
    LookupCatalogResult,
)
from src.services.query_service.app.routers.lookups import lookup_response_from_result


def test_lookup_response_from_result_preserves_api_contract() -> None:
    response = lookup_response_from_result(
        LookupCatalogResult(
            items=[
                LookupCatalogItem(id="PF_1", label="PF_1"),
                LookupCatalogItem(id="PF_2", label="PF_2"),
            ]
        )
    )

    assert response.model_dump() == {
        "items": [
            {"id": "PF_1", "label": "PF_1"},
            {"id": "PF_2", "label": "PF_2"},
        ]
    }
