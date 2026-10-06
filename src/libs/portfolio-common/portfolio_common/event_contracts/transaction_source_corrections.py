"""One signed source-confirmation command and one bounded committed-fact notice."""

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from portfolio_common.api_contract.async_commands import SourceEvidenceConfirmationInput
from portfolio_common.command_authorization import SignedCommandAuthorization


class TransactionSourceCorrectionRequestedEvent(BaseModel):
    """Metadata describes transport; only the verified attestation grants authority."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    authorization: SignedCommandAuthorization
    body: SourceEvidenceConfirmationInput
    tenant_id: str = Field(min_length=1, max_length=128)
    portfolio_id: str = Field(min_length=1, max_length=256)
    correlation_id: str = Field(min_length=1, max_length=128)
    trace_id: str = Field(min_length=1, max_length=128)
    idempotency_key: str = Field(min_length=1, max_length=128)
    source_system: Literal["ingestion_service"]
    event_type: Literal["TransactionSourceCorrectionRequested"]
    schema_version: Literal["1.0.0"]
    traceparent: str | None = Field(
        default=None, pattern=r"^00-[0-9a-f]{32}-[0-9a-f]{16}-[0-9a-f]{2}$"
    )

    @model_validator(mode="after")
    def require_signed_binding(self) -> Self:
        claims = self.authorization.claims
        if (
            self.tenant_id != claims.tenant_id
            or self.correlation_id != claims.correlation_id
            or self.trace_id != claims.trace_id
            or self.idempotency_key != claims.command_id
            or self.body.expected_head_id != claims.expected_head_id
            or self.body.expected_head_sha256 != claims.expected_head_sha256
            or self.body.canonical_request_sha256(
                target_transaction_id=claims.target_transaction_id
            )
            != claims.canonical_request_sha256
        ):
            raise ValueError("Source command does not match attested authority")
        return self


class TransactionSourceEvidenceChangedEvent(BaseModel):
    """A reload reference, never a financial booking or qualification certificate."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    revision_id: str = Field(min_length=1, max_length=128)
    revision_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    transaction_id: str = Field(min_length=1, max_length=256)
    portfolio_id: str = Field(min_length=1, max_length=256)
    tenant_id: str = Field(min_length=1, max_length=128)
    operation_id: str = Field(min_length=1, max_length=128)
    root_raw_event_id: int = Field(ge=1)
    correlation_id: str = Field(min_length=1, max_length=128)
    trace_id: str = Field(min_length=1, max_length=128)
    idempotency_key: str = Field(min_length=1, max_length=128)
    source_system: Literal["persistence_service"]
    event_type: Literal["TransactionSourceEvidenceChanged"]
    schema_version: Literal["1.0.0"]
    traceparent: str | None = Field(
        default=None, pattern=r"^00-[0-9a-f]{32}-[0-9a-f]{16}-[0-9a-f]{2}$"
    )

    @model_validator(mode="after")
    def require_immutable_identity(self) -> Self:
        if self.idempotency_key != self.revision_id:
            raise ValueError("Source notification does not match committed identity")
        return self
