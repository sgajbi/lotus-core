"""Reusable Query Service response contract for deterministic calculation lineage."""

from pydantic import BaseModel, Field


class CalculationLineageResponse(BaseModel):
    """Bind normalized inputs, calculation policy, and returned outputs."""

    algorithm_id: str = Field(
        ...,
        description="Stable financial calculation identity.",
        examples=["PORTFOLIO_CONTRACTUAL_MATURITY_SUMMARY"],
    )
    algorithm_version: int = Field(
        ...,
        ge=1,
        description="Exact calculation algorithm version.",
        examples=[1],
    )
    intermediate_precision: int = Field(
        ...,
        ge=1,
        description="Precision applied to intermediate calculation values.",
        examples=[28],
    )
    input_content_hash: str = Field(
        ...,
        pattern="^[0-9a-f]{64}$",
        description="SHA-256 of the normalized source and request inputs.",
        examples=["a" * 64],
    )
    calculation_content_hash: str = Field(
        ...,
        pattern="^[0-9a-f]{64}$",
        description="SHA-256 binding the algorithm, version, precision, and input hash.",
        examples=["b" * 64],
    )
    output_content_hash: str = Field(
        ...,
        pattern="^[0-9a-f]{64}$",
        description="SHA-256 binding the returned outputs to the calculation hash.",
        examples=["c" * 64],
    )
