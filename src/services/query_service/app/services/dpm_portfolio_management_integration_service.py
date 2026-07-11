from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ..dtos.reference_integration_dto import (
    CioModelChangeAffectedCohortRequest,
    CioModelChangeAffectedCohortResponse,
    DpmPortfolioUniverseCandidateRequest,
    DpmPortfolioUniverseCandidateResponse,
)
from .cio_model_change_cohort import resolve_cio_model_change_affected_cohort_response
from .dpm_portfolio_universe import (
    resolve_dpm_portfolio_universe_candidate_response,
)


@dataclass(frozen=True)
class DpmPortfolioManagementIntegrationService:
    """Contract-family service for DPM portfolio-management reference products."""

    reference_repository_provider: Callable[[], Any]
    decode_page_token: Callable[[str | None], dict[str, Any]]
    encode_page_token: Callable[[dict[str, str]], str]

    async def resolve_cio_model_change_affected_cohort(
        self,
        model_portfolio_id: str,
        request: CioModelChangeAffectedCohortRequest,
    ) -> CioModelChangeAffectedCohortResponse | None:
        return await resolve_cio_model_change_affected_cohort_response(
            repository=self.reference_repository_provider(),
            model_portfolio_id=model_portfolio_id,
            request=request,
        )

    async def resolve_dpm_portfolio_universe_candidates(
        self,
        request: DpmPortfolioUniverseCandidateRequest,
    ) -> DpmPortfolioUniverseCandidateResponse:
        return await resolve_dpm_portfolio_universe_candidate_response(
            repository=self.reference_repository_provider(),
            request=request,
            decode_page_token=self.decode_page_token,
            encode_page_token=self.encode_page_token,
        )
