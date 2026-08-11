"""API request contract for source-owned corporate-action manifests."""

from __future__ import annotations

from portfolio_common.event_contracts import CorporateActionManifestReceivedEvent
from pydantic import BaseModel, ConfigDict, Field, model_validator


class CorporateActionManifestIngestionRequest(BaseModel):
    """Bounded manifest batch published in monotonic parent-version order."""

    manifests: list[CorporateActionManifestReceivedEvent] = Field(
        min_length=1,
        max_length=1000,
        description=(
            "Source-owned corporate-action parent manifests. Envelope event type and schema "
            "version are fixed by Core; each manifest carries immutable upstream source evidence."
        ),
    )

    @model_validator(mode="after")
    def reject_duplicate_parent_versions(self) -> CorporateActionManifestIngestionRequest:
        identities = [
            (
                manifest.portfolio_id,
                manifest.corporate_action_event_id,
                manifest.version,
            )
            for manifest in self.manifests
        ]
        if len(identities) != len(set(identities)):
            raise ValueError("manifests contains duplicate parent-event versions")
        return self

    model_config = ConfigDict(extra="forbid")
