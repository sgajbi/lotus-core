"""Public contracts for governed classification taxonomy evidence."""

from datetime import date
from typing import Literal

from portfolio_common.api_contract.classification_history import (
    CLASSIFICATION_SELECTION_EXAMPLE,
    ClassificationHistoryEvidence,
    ClassificationHistorySelection,
)
from portfolio_common.source_data_product_metadata import (
    SourceDataProductRuntimeMetadata,
    product_name_field,
    product_version_field,
)
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .common import SourceObservationEvidence


class ClassificationTaxonomyRequest(BaseModel):
    """Request effective taxonomy labels at one business date."""

    as_of_date: date = Field(
        ..., description="As-of date for taxonomy resolution.", examples=["2026-01-31"]
    )
    taxonomy_scope: str | None = Field(
        None,
        description=(
            "Optional taxonomy scope filter such as `index`, `instrument`, or other "
            "governed source scopes. Omitting the field returns all effective scopes."
        ),
        examples=["index"],
    )

    history_selection: ClassificationHistorySelection | None = Field(
        None,
        exclude_if=lambda value: value is None,
        description="Exact historical instrument assignment pins; no current-label fallback.",
        examples=[CLASSIFICATION_SELECTION_EXAMPLE],
    )

    @model_validator(mode="after")
    def historical_scope(self):
        if self.history_selection is not None and (
            self.as_of_date != self.history_selection.period_end
            or self.taxonomy_scope not in (None, "instrument")
        ):
            raise ValueError("Historical instrument scope must match its explicit period end")
        return self

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "as_of_date": "2026-01-31",
                    "taxonomy_scope": "instrument",
                    "history_selection": CLASSIFICATION_SELECTION_EXAMPLE,
                }
            ]
        },
    )


class ClassificationTaxonomyEntry(SourceObservationEvidence):
    """One governed classification label effective on the requested date."""

    classification_set_id: str = Field(
        ...,
        description="Classification taxonomy set identifier.",
        examples=["wm_global_taxonomy_v1"],
    )
    taxonomy_scope: str = Field(..., description="Taxonomy scope.", examples=["index"])
    dimension_name: str = Field(
        ..., description="Classification dimension name.", examples=["sector"]
    )
    dimension_value: str = Field(
        ..., description="Classification dimension value.", examples=["technology"]
    )
    dimension_description: str | None = Field(
        None,
        description="Human-readable dimension description.",
        examples=["Technology sector classification"],
    )
    effective_from: date = Field(..., description="Effective start date.", examples=["2025-01-01"])
    effective_to: date | None = Field(
        None,
        description="Effective end date.",
        examples=["2026-12-31"],
    )
    model_config = ConfigDict()


class ClassificationTaxonomyResponse(SourceDataProductRuntimeMetadata):
    """Governed taxonomy records with source-owned supportability evidence."""

    product_name: Literal["InstrumentReferenceBundle"] = product_name_field(
        "InstrumentReferenceBundle"
    )
    product_version: Literal["v1"] = product_version_field()
    as_of_date: date = Field(
        ...,
        description="As-of date used for taxonomy response.",
        examples=["2026-01-31"],
    )
    records: list[ClassificationTaxonomyEntry] = Field(
        default_factory=list,
        description="Classification taxonomy entries effective on the requested date.",
        examples=[[{"classification_set_id": "wm_global_taxonomy_v1", "dimension_name": "sector"}]],
    )
    taxonomy_version: str = Field(
        "rfc_062_v1",
        description="Taxonomy contract version exposed by query service.",
        examples=["rfc_062_v1"],
    )
    history: ClassificationHistoryEvidence | None = Field(
        None,
        exclude_if=lambda value: value is None,
        description="Retained custody; provider and financial authority remain unavailable.",
    )
    request_fingerprint: str = Field(
        ...,
        description="Deterministic request fingerprint for the taxonomy response scope.",
        examples=["d87368035df24ff9a42cb6e586e17ac7"],
    )
    model_config = ConfigDict()
