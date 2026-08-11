"""Strict transport contract for source-owned corporate-action manifests."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Literal, cast

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, field_validator

from portfolio_common.domain.calculation_lineage import canonical_content_hash
from portfolio_common.domain.eventing import portfolio_transaction_group_partition_key

CORPORATE_ACTION_MANIFEST_RECEIVED_EVENT_TYPE = "corporate_action.manifest.received"
CORPORATE_ACTION_MANIFEST_RECEIVED_SCHEMA_VERSION = "1.0.0"

_STRICT_MODEL_CONFIG = ConfigDict(
    extra="forbid",
    frozen=True,
    str_strip_whitespace=True,
    allow_inf_nan=False,
)
_PositiveStrictVersion = Annotated[int, Field(strict=True, ge=1)]
_NonNegativeStrictSequence = Annotated[int, Field(strict=True, ge=0)]
_Sha256Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


def _parse_iso_datetime(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("datetime input must be an ISO 8601 string")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("datetime input must be an ISO 8601 timestamp") from exc


_IsoDatetime = Annotated[datetime, BeforeValidator(_parse_iso_datetime)]


class CorporateActionManifestSourceContract(BaseModel):
    """Bind a manifest to immutable upstream source evidence."""

    source_system: str = Field(min_length=1, max_length=160)
    source_record_id: str = Field(min_length=1, max_length=200)
    source_revision: str = Field(min_length=1, max_length=200)
    source_content_hash: _Sha256Digest
    observed_at: _IsoDatetime

    @field_validator("observed_at")
    @classmethod
    def require_aware_observation(cls, value: datetime) -> datetime:
        if value.utcoffset() is None:
            raise ValueError("observed_at must include a timezone offset")
        return value.astimezone(UTC)

    model_config = _STRICT_MODEL_CONFIG


class CorporateActionManifestChildContract(BaseModel):
    """Declare one expected child and its deterministic dependency edges."""

    transaction_id: str = Field(min_length=1, max_length=200)
    transaction_type: str = Field(min_length=1, max_length=100)
    child_role: str = Field(min_length=1, max_length=100)
    dependency_transaction_ids: tuple[str, ...] = Field(default=(), max_length=1000)
    child_sequence_hint: _NonNegativeStrictSequence | None = None
    instrument_id: str | None = Field(default=None, min_length=1, max_length=200)
    source_instrument_id: str | None = Field(default=None, min_length=1, max_length=200)
    target_instrument_id: str | None = Field(default=None, min_length=1, max_length=200)

    @field_validator("transaction_type", "child_role")
    @classmethod
    def normalize_classification(cls, value: str) -> str:
        return value.upper()

    @field_validator("dependency_transaction_ids")
    @classmethod
    def normalize_dependencies(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(value.strip() for value in values)
        if any(not value for value in normalized):
            raise ValueError("dependency_transaction_ids must contain nonblank identifiers")
        return normalized

    def canonical_payload(self) -> dict[str, object]:
        """Return order-neutral child authority for event hashing."""

        payload = self.model_dump(mode="python")
        payload["dependency_transaction_ids"] = sorted(self.dependency_transaction_ids)
        return cast(dict[str, object], payload)

    model_config = _STRICT_MODEL_CONFIG


class CorporateActionManifestReceivedEvent(BaseModel):
    """Versioned source fact accepted by the transaction-processing owner."""

    event_type: Literal["corporate_action.manifest.received"] = (
        "corporate_action.manifest.received"
    )
    schema_version: Literal["1.0.0"] = "1.0.0"
    corporate_action_event_id: str = Field(min_length=1, max_length=200)
    portfolio_id: str = Field(min_length=1, max_length=200)
    linked_transaction_group_id: str = Field(min_length=1, max_length=200)
    parent_event_reference: str = Field(min_length=1, max_length=200)
    corporate_action_type: str = Field(min_length=1, max_length=100)
    version: _PositiveStrictVersion
    completion_declared: bool = Field(strict=True)
    expected_children: tuple[CorporateActionManifestChildContract, ...] = Field(max_length=1000)
    source: CorporateActionManifestSourceContract

    @field_validator("corporate_action_type")
    @classmethod
    def normalize_corporate_action_type(cls, value: str) -> str:
        return value.upper()

    @property
    def partition_key(self) -> str:
        """Order a manifest with every child in its portfolio-owned group."""

        return cast(
            str,
            portfolio_transaction_group_partition_key(
                self.portfolio_id,
                self.linked_transaction_group_id,
            ).value,
        )

    def content_hash(self) -> str:
        """Bind normalized source authority without depending on array order."""

        payload = self.model_dump(mode="python", exclude={"expected_children"})
        payload["expected_children"] = [
            child.canonical_payload()
            for child in sorted(self.expected_children, key=lambda child: child.transaction_id)
        ]
        return cast(str, canonical_content_hash(payload))

    model_config = _STRICT_MODEL_CONFIG
