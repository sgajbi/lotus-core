from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from ..dtos.reference_integration_dto import (
    DpmPortfolioUniverseCandidateRequest,
    DpmPortfolioUniverseCandidateResponse,
    DpmPortfolioUniverseCandidateSelectionBasis,
    DpmPortfolioUniverseCandidateSupportability,
    ReferencePageMetadata,
)
from ..dtos.source_data_product_identity import source_data_product_runtime_metadata
from .reference_data_helpers import latest_reference_evidence_timestamp
from .reference_data_mappers import dpm_portfolio_universe_candidate
from .request_fingerprint import request_fingerprint


@dataclass(frozen=True)
class DpmPortfolioUniverseReadScope:
    booking_center_code: str | None
    model_portfolio_ids: list[str]
    request_scope_fingerprint: str


def dpm_portfolio_universe_read_scope(
    request: DpmPortfolioUniverseCandidateRequest,
) -> DpmPortfolioUniverseReadScope:
    booking_center_code = (
        request.booking_center_code.strip() if request.booking_center_code else None
    )
    if booking_center_code == "":
        booking_center_code = None
    model_portfolio_ids = sorted(
        {
            model_portfolio_id.strip()
            for model_portfolio_id in request.model_portfolio_ids
            if model_portfolio_id.strip()
        }
    )
    request_scope_fingerprint = request_fingerprint(
        {
            "product_name": "DpmPortfolioUniverseCandidate",
            "as_of_date": request.as_of_date.isoformat(),
            "booking_center_code": booking_center_code,
            "model_portfolio_ids": model_portfolio_ids,
            "include_inactive_mandates": request.include_inactive_mandates,
            "tenant_id": request.tenant_id,
        }
    )
    return DpmPortfolioUniverseReadScope(
        booking_center_code=booking_center_code,
        model_portfolio_ids=model_portfolio_ids,
        request_scope_fingerprint=request_scope_fingerprint,
    )


def dpm_portfolio_universe_after_sort_key(
    *,
    cursor: dict[str, Any],
    request_scope_fingerprint: str,
) -> tuple[str, str] | None:
    token_scope = cursor.get("scope_fingerprint")
    if token_scope and token_scope != request_scope_fingerprint:
        raise ValueError("DPM portfolio-universe page token does not match request scope.")

    if cursor.get("last_portfolio_id") and cursor.get("last_mandate_id"):
        return (str(cursor["last_portfolio_id"]), str(cursor["last_mandate_id"]))
    return None


def dpm_portfolio_universe_next_page_token_payload(
    *,
    request_scope_fingerprint: str,
    page_rows: list[Any],
    has_more: bool,
) -> dict[str, str] | None:
    if not has_more or not page_rows:
        return None
    last_row = page_rows[-1]
    return {
        "scope_fingerprint": request_scope_fingerprint,
        "last_portfolio_id": str(last_row.portfolio_id),
        "last_mandate_id": str(last_row.mandate_id),
    }


def dpm_portfolio_universe_page_token(
    *,
    request_scope_fingerprint: str,
    page_rows: list[Any],
    has_more: bool,
    encode_page_token: Callable[[dict[str, str]], str],
) -> str | None:
    payload = dpm_portfolio_universe_next_page_token_payload(
        request_scope_fingerprint=request_scope_fingerprint,
        page_rows=page_rows,
        has_more=has_more,
    )
    if payload is None:
        return None
    return encode_page_token(payload)


async def resolve_dpm_portfolio_universe_candidate_response(
    *,
    repository: Any,
    request: DpmPortfolioUniverseCandidateRequest,
    decode_page_token: Callable[[str | None], dict[str, Any]],
    encode_page_token: Callable[[dict[str, str]], str],
) -> DpmPortfolioUniverseCandidateResponse:
    read_scope = dpm_portfolio_universe_read_scope(request)
    after_sort_key = dpm_portfolio_universe_after_sort_key(
        cursor=decode_page_token(request.page.page_token),
        request_scope_fingerprint=read_scope.request_scope_fingerprint,
    )
    rows = await repository.list_dpm_portfolio_universe_candidates(
        as_of_date=request.as_of_date,
        booking_center_code=read_scope.booking_center_code,
        model_portfolio_ids=read_scope.model_portfolio_ids,
        include_inactive_mandates=request.include_inactive_mandates,
        after_sort_key=after_sort_key,
        limit=request.page.page_size + 1,
    )
    has_more = len(rows) > request.page.page_size
    page_rows = rows[: request.page.page_size]
    next_page_token = dpm_portfolio_universe_page_token(
        request_scope_fingerprint=read_scope.request_scope_fingerprint,
        page_rows=page_rows,
        has_more=has_more,
        encode_page_token=encode_page_token,
    )

    return build_dpm_portfolio_universe_response(
        request=request,
        read_scope=read_scope,
        page_rows=page_rows,
        has_more=has_more,
        next_page_token=next_page_token,
    )


def build_dpm_portfolio_universe_response(
    *,
    request: DpmPortfolioUniverseCandidateRequest,
    read_scope: DpmPortfolioUniverseReadScope,
    page_rows: list[Any],
    has_more: bool,
    next_page_token: str | None,
) -> DpmPortfolioUniverseCandidateResponse:
    candidates = [dpm_portfolio_universe_candidate(row) for row in page_rows]

    filters_applied = ["as_of_date"]
    if read_scope.booking_center_code:
        filters_applied.append("booking_center_code")
    if read_scope.model_portfolio_ids:
        filters_applied.append("model_portfolio_ids")
    if not request.include_inactive_mandates:
        filters_applied.append("active_discretionary_authority")

    supportability_state: Literal["READY", "DEGRADED", "INCOMPLETE"] = "READY"
    supportability_reason = "DPM_PORTFOLIO_UNIVERSE_READY"
    data_quality_status = "ACCEPTED"
    if not candidates:
        supportability_state = "INCOMPLETE"
        supportability_reason = "DPM_PORTFOLIO_UNIVERSE_EMPTY"
        data_quality_status = "MISSING"
    elif has_more:
        supportability_state = "DEGRADED"
        supportability_reason = "DPM_PORTFOLIO_UNIVERSE_PAGE_PARTIAL"
        data_quality_status = "PARTIAL"

    return DpmPortfolioUniverseCandidateResponse(
        candidates=candidates,
        page=ReferencePageMetadata(
            page_size=request.page.page_size,
            sort_key="portfolio_id:asc,mandate_id:asc",
            returned_component_count=len(candidates),
            request_scope_fingerprint=read_scope.request_scope_fingerprint,
            next_page_token=next_page_token,
        ),
        supportability=DpmPortfolioUniverseCandidateSupportability(
            state=supportability_state,
            reason=supportability_reason,
            returned_candidate_count=len(candidates),
            filters_applied=filters_applied,
            page_truncated=has_more,
        ),
        selection_basis=DpmPortfolioUniverseCandidateSelectionBasis(
            basis_type="EFFECTIVE_DISCRETIONARY_MANDATE_BINDING",
            source_table="portfolio_mandate_bindings",
            included_when=[
                "mandate_type=discretionary",
                "effective_from<=as_of_date",
                "effective_to is null or effective_to>=as_of_date",
                "active authority unless include_inactive_mandates=true",
            ],
            downstream_boundary=(
                "Candidate membership is not relationship householding, suitability approval, "
                "portfolio-manager ranking, execution readiness, client communication "
                "workflow, or external workflow ownership."
            ),
        ),
        lineage={
            "source_system": "lotus-core",
            "source_table": "portfolio_mandate_bindings",
            "source_filter": "mandate_type=discretionary",
            "contract_version": "rfc_037_dpm_portfolio_universe_candidate_v1",
        },
        **source_data_product_runtime_metadata(
            as_of_date=request.as_of_date,
            tenant_id=request.tenant_id,
            data_quality_status=data_quality_status,
            latest_evidence_timestamp=latest_reference_evidence_timestamp(page_rows),
            source_batch_fingerprint=None,
            snapshot_id=f"dpm_portfolio_universe:{read_scope.request_scope_fingerprint}",
        ),
    )
