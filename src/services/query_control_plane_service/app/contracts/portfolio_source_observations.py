"""Independent pinned observations, never a composite eligibility or authority result."""

from datetime import date, datetime
from decimal import Decimal
from typing import Literal, Self

from portfolio_common.domain.calculation_lineage import require_sha256_digest
from portfolio_common.domain.portfolio_source_observations import require_observation_identity
from portfolio_common.source_data_product_metadata import (
    SourceDataProductRuntimeMetadata,
    product_name_field,
    product_version_field,
)
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, model_validator


class ObservationSelector(BaseModel):
    model_config = ConfigDict(extra="forbid")
    producer_id: str = Field(description="Exact source producer identity, not a submission grant.")
    source_record_id: str = Field(description="Exact producer record identity.")
    latest_restated: StrictBool = Field(
        False, description="Explicitly opt into the current corrected head."
    )
    observation_id: str | None = Field(
        None, description="Immutable original or corrected observation pin."
    )
    content_hash: str | None = Field(None, description="Expected exact pinned fact hash.")
    source_cut_id: str | None = Field(None, description="Expected independent source cut pin.")
    source_version: StrictInt | None = Field(
        None, ge=1, description="Expected producer revision pin."
    )

    @model_validator(mode="after")
    def require_explicit_selection(self) -> Self:
        require_observation_identity(self.producer_id, "producer_id")
        require_observation_identity(self.source_record_id, "source_record_id")
        pins = (self.observation_id, self.content_hash, self.source_cut_id, self.source_version)
        if self.latest_restated:
            if any(pin is not None for pin in pins):
                raise ValueError("latest-restated selection cannot mix immutable pins")
        elif any(pin is None for pin in pins):
            raise ValueError("all four immutable source pins are required")
        else:
            for name in ("observation_id", "content_hash"):
                value = getattr(self, name)
                if value is not None:
                    require_sha256_digest(value, name)
            if self.source_cut_id is not None:
                require_observation_identity(self.source_cut_id, "source_cut_id")
        return self


class PortfolioSourceObservationsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    as_of_date: date = Field(
        description="Business date, independent of observation and receipt time."
    )
    cash: ObservationSelector | None = Field(
        None, description="Independent cash selection; absent is unavailable."
    )
    funding_investment: ObservationSelector | None = Field(
        None, description="Independent assertion selection."
    )


class SourceObservationEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    observation_id: str = Field(description="Immutable observation identity.")
    content_hash: str = Field(description="Recomputed typed fact hash.")
    source_system: str = Field(description="Attributed producer, not approved bank authority.")
    source_record_id: str = Field(description="Original producer record identity.")
    source_version: int = Field(description="Contiguous immutable source revision.")
    source_cut_id: str = Field(
        description="Independent source cut; date equality does not establish compatibility."
    )
    definition_version: str = Field(description="Producer definition version.")
    effective_from: date = Field(description="Inclusive business-date start.")
    effective_to: date | None = Field(description="Exclusive business-date end.")
    observed_at: datetime = Field(description="Source observation time.")
    generated_at: datetime = Field(description="Source generation time.")
    received_at: datetime = Field(description="Server receipt time.")
    receipt_job_id: str = Field(description="Atomic synchronous ingestion receipt identity.")
    coverage: Literal["complete", "partial", "missing"] = Field(
        description="Coverage is not qualification."
    )
    coverage_scope: str = Field(description="Independent producer-declared coverage boundary.")
    qualification: Literal["unqualified"] = Field(
        "unqualified", description="No provider qualification granted."
    )
    latest_restated: bool = Field(
        description="Whether explicit current-head selection was requested."
    )


class CashObservationEvidence(SourceObservationEvidence):
    currency: str = Field(description="Producer-declared currency.")
    settled_amount: Decimal | None = Field(
        description="Independent settled observation, no derived formula."
    )
    encumbered_amount: Decimal | None = Field(description="Independent encumbered observation.")
    available_amount: Decimal | None = Field(
        description="Independent available observation; zero is not missing."
    )


class FundingInvestmentEvidence(SourceObservationEvidence):
    funded: bool | None = Field(
        description="Independent producer assertion, not lifecycle-derived."
    )
    invested: bool | None = Field(
        description="Independent producer assertion, not valuation-derived."
    )


class PortfolioSourceObservationsResponse(SourceDataProductRuntimeMetadata):
    product_name: Literal["PortfolioFinancialSourceObservations"] = product_name_field(
        "PortfolioFinancialSourceObservations"
    )
    product_version: Literal["v1"] = product_version_field()
    portfolio_id: str = Field(description="Authenticated tenant-scoped portfolio.")
    authoritative_state: Literal["UNAVAILABLE"] = Field(
        "UNAVAILABLE", description="No qualified producer/cut compatibility is established."
    )
    compatibility: Literal["UNAVAILABLE"] = Field(
        "UNAVAILABLE", description="No joined valuation or other product cut contract is claimed."
    )
    cash: CashObservationEvidence | None = Field(
        description="Diagnostic independent fact, or unavailable."
    )
    funding_investment: FundingInvestmentEvidence | None = Field(
        description="Diagnostic independent assertions, or unavailable."
    )
    reason_codes: list[str] = Field(
        description="Bounded unavailability reasons; never caller approval."
    )
