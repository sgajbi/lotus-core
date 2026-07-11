"""Contract tests for shared reference-data paging models."""

import pytest
from portfolio_common.reference_data_paging import ReferencePageMetadata, ReferencePageRequest
from pydantic import ValidationError


def test_reference_page_request_preserves_bounded_defaults() -> None:
    request = ReferencePageRequest()

    assert request.page_size == 250
    assert request.page_token is None

    with pytest.raises(ValidationError):
        ReferencePageRequest(page_size=1001)


def test_reference_page_metadata_exposes_deterministic_continuation_evidence() -> None:
    metadata = ReferencePageMetadata(
        page_size=250,
        sort_key="portfolio_id:asc,mandate_id:asc",
        returned_component_count=2,
        request_scope_fingerprint="sha256:scope",
        next_page_token="opaque-token",
    )

    assert metadata.model_dump() == {
        "page_size": 250,
        "sort_key": "portfolio_id:asc,mandate_id:asc",
        "returned_component_count": 2,
        "request_scope_fingerprint": "sha256:scope",
        "next_page_token": "opaque-token",
    }
