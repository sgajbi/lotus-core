"""DB-time fenced capture work; repository transactions end before acquisition."""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol

from .financial_source_captures import CapturedSourcePage, SourceCaptureRequest


class StaleSourceCutClaim(ValueError):
    """Expired or superseded workers cannot append captures or complete a receipt."""


class SourceManifestRejected(ValueError):
    """Immutable declarations did not reconcile; retry cannot manufacture completeness."""


@dataclass(frozen=True, slots=True)
class SourceCutClaim:
    work_id: str
    tenant_id: str
    command_hash: str
    lease_token: str
    lease_expires_at: datetime
    checkpoint_hash: str
    scope_hash: str = ""


@dataclass(frozen=True, slots=True)
class SourceCutProgress:
    stage: Literal[
        "VERIFY_CHUNKS", "VERIFY_MEMBERS", "VERIFY_INPUTS", "SPAWN_CAPTURES", "WAIT_CAPTURES"
    ]


class FinancialSourceCutWork(Protocol):
    async def claim(self) -> SourceCutClaim | None: ...

    async def next_capture(
        self, claim: SourceCutClaim
    ) -> SourceCaptureRequest | SourceCutProgress | None: ...

    async def advance(self, claim: SourceCutClaim, progress: SourceCutProgress) -> None: ...

    async def cached_capture(self, request: SourceCaptureRequest) -> CapturedSourcePage | None: ...

    async def save_capture(self, claim: SourceCutClaim, page: CapturedSourcePage) -> None: ...

    async def complete(self, claim: SourceCutClaim) -> None: ...

    async def defer(self, claim: SourceCutClaim, error_code: str) -> None: ...

    async def reject(self, claim: SourceCutClaim) -> None: ...
