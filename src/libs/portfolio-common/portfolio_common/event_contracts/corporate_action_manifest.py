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

    source_system: str = Field(
        min_length=1,
        max_length=160,
        description="Authoritative upstream corporate-action source system.",
        examples=["corporate-actions-master"],
    )
    source_record_id: str = Field(
        min_length=1,
        max_length=200,
        description="Immutable upstream corporate-action record identifier.",
        examples=["CA-EVENT-2026-0001"],
    )
    source_revision: str = Field(
        min_length=1,
        max_length=200,
        description="Upstream revision identity for this parent manifest.",
        examples=["revision-1"],
    )
    source_content_hash: _Sha256Digest = Field(
        description="Lowercase SHA-256 digest of the authoritative upstream source record.",
        examples=["a" * 64],
    )
    observed_at: _IsoDatetime = Field(
        description="Timezone-qualified time at which Core observed the source revision.",
        examples=["2026-08-11T02:15:00Z"],
    )

    @field_validator("observed_at")
    @classmethod
    def require_aware_observation(cls, value: datetime) -> datetime:
        if value.utcoffset() is None:
            raise ValueError("observed_at must include a timezone offset")
        return value.astimezone(UTC)

    model_config = _STRICT_MODEL_CONFIG


class CorporateActionManifestChildContract(BaseModel):
    """Declare one expected child and its deterministic dependency edges."""

    transaction_id: str = Field(
        min_length=1,
        max_length=200,
        description="Expected persisted child transaction identifier.",
        examples=["TX-CA-SOURCE-001"],
    )
    transaction_type: str = Field(
        min_length=1,
        max_length=100,
        description="Canonical transaction type of the expected child.",
        examples=["SPIN_OFF"],
    )
    child_role: str = Field(
        min_length=1,
        max_length=100,
        description="Corporate-action economic role of the expected child.",
        examples=["SOURCE_POSITION_REDUCE"],
    )
    dependency_transaction_ids: tuple[str, ...] = Field(
        default=(),
        max_length=1000,
        description="Predecessor child transaction identifiers that must execute first.",
        examples=[["TX-CA-SOURCE-001"]],
    )
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

    event_type: Literal["corporate_action.manifest.received"] = Field(
        default="corporate_action.manifest.received",
        description="Core-owned corporate-action parent-manifest event family.",
        examples=["corporate_action.manifest.received"],
    )
    schema_version: Literal["1.0.0"] = Field(
        default="1.0.0",
        description="Corporate-action parent-manifest event schema version.",
        examples=["1.0.0"],
    )
    corporate_action_event_id: str = Field(
        min_length=1,
        max_length=200,
        description="Stable Core identity for one corporate-action parent event.",
        examples=["CA-EVENT-2026-0001"],
    )
    tenant_id: str = Field(
        min_length=1,
        max_length=160,
        description="Tenant that owns the governed portfolio book.",
        examples=["TENANT_SG"],
    )
    legal_book_id: str = Field(
        min_length=1,
        max_length=160,
        description="Legal book that owns the governed portfolio.",
        examples=["BOOK_SG_PB"],
    )
    portfolio_id: str = Field(
        min_length=1,
        max_length=200,
        description="Portfolio whose corporate-action children will be processed.",
        examples=["PB_SG_GLOBAL_BAL_001"],
    )
    linked_transaction_group_id: str = Field(
        min_length=1,
        max_length=200,
        description="Group identity shared by every expected child transaction.",
        examples=["CA-GROUP-2026-0001"],
    )
    parent_event_reference: str = Field(
        min_length=1,
        max_length=200,
        description="Authoritative upstream parent-event reference.",
        examples=["UPSTREAM-CA-2026-0001"],
    )
    corporate_action_type: str = Field(
        min_length=1,
        max_length=100,
        description="Canonical corporate-action family governing child-shape policy.",
        examples=["SPIN_OFF"],
    )
    version: _PositiveStrictVersion = Field(
        description="Monotonic source-owned version of this parent manifest.",
        examples=[1],
    )
    completion_declared: bool = Field(
        strict=True,
        description="Whether the source declares the expected child set complete.",
        examples=[True],
    )
    expected_children: tuple[CorporateActionManifestChildContract, ...] = Field(
        max_length=1000,
        description="Complete expected child membership and dependency declarations.",
    )
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
