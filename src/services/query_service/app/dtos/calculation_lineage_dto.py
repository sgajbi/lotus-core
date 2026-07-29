"""Reusable Query Service response contract for deterministic calculation lineage."""

from typing import Self

from pydantic import BaseModel, Field, field_validator, model_validator


class NumericOutputPolicyLineageResponse(BaseModel):
    """Expose the exact numeric boundary applied to calculated financial output."""

    name: str = Field(
        ...,
        description="Stable owner-defined numeric-output policy name.",
        examples=["position-valuation-ledger-output"],
    )
    version: str = Field(
        ...,
        description="Exact numeric-output policy version included in calculation identity.",
        examples=["1.0.0"],
    )
    precision: int = Field(
        ...,
        ge=1,
        description="Maximum decimal digits accepted by the output boundary.",
        examples=[18],
    )
    scale: int = Field(
        ...,
        ge=0,
        description="Maximum fractional decimal digits accepted by the output boundary.",
        examples=[10],
    )
    working_precision: int = Field(
        ...,
        ge=1,
        description="Decimal precision used for deterministic intermediate arithmetic.",
        examples=[64],
    )
    rounding: str = Field(
        ...,
        description="Explicit decimal rounding mode applied once at the output boundary.",
        examples=["ROUND_HALF_EVEN"],
    )

    @field_validator("name", "version", "rounding")
    @classmethod
    def require_nonblank_identity(cls, value: str) -> str:
        """Reject lineage that cannot identify one exact calculation policy."""

        if not value.strip():
            raise ValueError("numeric-output policy identity fields must be nonblank")
        return value

    @model_validator(mode="after")
    def validate_numeric_shape(self) -> Self:
        """Keep the public lineage shape consistent with the domain policy contract."""

        if self.scale > self.precision:
            raise ValueError("scale must be between zero and precision")
        if self.working_precision < self.precision:
            raise ValueError("working_precision must be at least precision")
        return self


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
    numeric_output_policy: NumericOutputPolicyLineageResponse | None = Field(
        default=None,
        description=(
            "Exact owner-defined numeric-output boundary included in calculation identity. "
            "Absent when the calculation does not execute a governed output policy."
        ),
    )
