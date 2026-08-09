"""Persistence boundary for source-owned corporate-action parent manifests."""

from __future__ import annotations

from enum import StrEnum
from typing import Protocol

from ..domain.transaction.corporate_action import CorporateActionParentManifest


class CorporateActionManifestAppendOutcome(StrEnum):
    """Observable outcome of one immutable manifest append."""

    APPENDED = "APPENDED"
    UNCHANGED = "UNCHANGED"


class ConflictingCorporateActionManifestError(ValueError):
    """Raised when an event or source version is reused with different content."""


class CorporateActionBookScopeError(ValueError):
    """Raised when a manifest portfolio lacks complete governed book ownership."""


class CorporateActionEventGraphPort(Protocol):
    """Append and reconstruct source-versioned corporate-action manifests."""

    async def append_manifest(
        self,
        manifest: CorporateActionParentManifest,
    ) -> CorporateActionManifestAppendOutcome: ...

    async def load_current_manifest(
        self,
        *,
        portfolio_id: str,
        corporate_action_event_id: str,
    ) -> CorporateActionParentManifest | None: ...
