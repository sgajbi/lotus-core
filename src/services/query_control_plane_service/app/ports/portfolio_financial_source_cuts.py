"""Immutable custody reads; adapters never reacquire source products."""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import BinaryIO, Protocol

from ..contracts.portfolio_financial_source_cuts import (
    CaptureSegmentEvidence,
    ExactSourceCutQuery,
    FinancialCutEvidence,
    FinancialInputEvidence,
    RegistryCutEvidence,
    RegistryMemberEvidence,
)


@dataclass(frozen=True, slots=True)
class RetainedCut:
    header: RegistryCutEvidence | FinancialCutEvidence
    compatibility_posture: str = "UNAVAILABLE"


class RetainedSourceCutReader(Protocol):
    async def cut(
        self, tenant_id: str, product: str, query: ExactSourceCutQuery
    ) -> RetainedCut: ...

    def members(
        self, tenant_id: str, query: ExactSourceCutQuery
    ) -> AsyncIterator[RegistryMemberEvidence]: ...

    async def selected_input(
        self, tenant_id: str, query: ExactSourceCutQuery, cut: RetainedCut
    ) -> FinancialInputEvidence: ...

    def captures(
        self,
        tenant_id: str,
        query: ExactSourceCutQuery,
        cut: RetainedCut,
        selected: FinancialInputEvidence | None = None,
    ) -> AsyncIterator[CaptureSegmentEvidence]: ...


class RetainedCaptureVerifier(Protocol):
    """Owner-supplied frozen serializer catalog; unsupported tags must refuse."""

    def verify(
        self,
        artifact: CaptureSegmentEvidence,
        raw: BinaryIO,
        *,
        identity,
        financial_input: FinancialInputEvidence | None = None,
    ) -> None: ...
