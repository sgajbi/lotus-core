"""Reference-only custody completion transport."""

from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator

from .domain.calculation_lineage import require_sha256_digest
from .domain.portfolio_source_observations import require_observation_identity


class PortfolioFinancialSourceCutCompletedEvent(BaseModel):
    """Reference-only custody fact; never an approval, balance or financial result."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    event_type: Literal["PortfolioFinancialSourceCutCompleted"] = (
        "PortfolioFinancialSourceCutCompleted"
    )
    schema_version: Literal["1.0.0"] = "1.0.0"
    tenant_id: str
    product_name: Literal["PortfolioHistoricalRegistry", "PortfolioFinancialSourceCut"]
    source_system: str
    registry_scope_id: str
    source_cut_id: str
    revision: StrictInt = Field(ge=1)
    content_hash: str
    predecessor_hash: str | None
    receipt_job_id: str
    completed_at: datetime
    qualification: Literal["UNQUALIFIED"] = "UNQUALIFIED"
    population_verification: Literal["UNVERIFIED"] = "UNVERIFIED"
    compatibility_posture: Literal["DECLARED_UNVERIFIED", "UNAVAILABLE"]
    correlation_id: str | None = None
    traceparent: str | None = None

    @model_validator(mode="after")
    def exact_reference_fact(self) -> Self:
        for name in (
            "tenant_id",
            "source_system",
            "registry_scope_id",
            "source_cut_id",
            "receipt_job_id",
        ):
            require_observation_identity(getattr(self, name), name)
        require_sha256_digest(self.content_hash, "completed source root")
        if self.predecessor_hash is not None:
            require_sha256_digest(self.predecessor_hash, "completed predecessor")
        if (self.revision == 1) != (self.predecessor_hash is None):
            raise ValueError("completed fact must retain exact revision/predecessor posture")
        if self.completed_at.utcoffset() is None:
            raise ValueError("aware native completion time required")
        return self
