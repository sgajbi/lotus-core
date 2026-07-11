"""Stable paging contracts shared by Core reference-data APIs."""

from pydantic import BaseModel, ConfigDict, Field


class ReferencePageRequest(BaseModel):
    """Bounded continuation request for a reference-data product."""

    page_size: int = Field(
        250,
        ge=1,
        le=1000,
        description="Maximum number of component series records to return per page.",
        examples=[250],
    )
    page_token: str | None = Field(
        None,
        description="Opaque continuation token from a previous benchmark market-series page.",
        examples=["eyJwIjp7Imxhc3RfaW5kZXhfaWQiOiJJRFhfTVNDSSJ9LCJzIjoiLi4uIn0="],
    )

    model_config = ConfigDict()


class ReferencePageMetadata(BaseModel):
    """Deterministic paging evidence returned by a reference-data product."""

    page_size: int = Field(
        ...,
        description="Effective component page size used for this response.",
        examples=[250],
    )
    sort_key: str = Field(
        ...,
        description="Deterministic ordering applied to the paged component series.",
        examples=["index_id:asc"],
    )
    returned_component_count: int = Field(
        ...,
        description="Number of component series records returned in the current page.",
        examples=[250],
    )
    request_scope_fingerprint: str = Field(
        ...,
        description="Deterministic fingerprint of the request scope bound to this page sequence.",
        examples=["a6b8f6456a6d89cfcc1ce572f2cfcedb"],
    )
    next_page_token: str | None = Field(
        None,
        description=(
            "Opaque continuation token for the next page, null when no additional pages remain."
        ),
        examples=["eyJwIjp7Imxhc3RfaW5kZXhfaWQiOiJJRFhfTVNDSSJ9LCJzIjoiLi4uIn0="],
    )

    model_config = ConfigDict()
