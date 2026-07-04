from __future__ import annotations

from ..dtos.reference_integration_dto import (
    PerformanceComponentEconomicsRequest,
    PerformanceComponentEconomicsResponse,
    PerformanceComponentEconomicsRow,
    PerformanceComponentEconomicsSupportability,
    ReferencePageMetadata,
)
from ..read_models import PerformanceEconomicsTransactionReadRecord
from .performance_component_economics_policy import (
    build_performance_component_economics_totals,
    latest_performance_evidence_timestamp,
    missing_performance_component_families,
    observed_performance_component_families,
    performance_component_economics_data_quality_status,
    performance_component_economics_source_lineage,
    performance_component_economics_supportability_reason,
    performance_component_economics_supportability_state,
)
from .request_fingerprint import request_fingerprint as build_request_fingerprint
from .source_data_runtime import source_product_runtime_metadata_without_as_of_date


def build_performance_component_economics_response(
    *,
    portfolio_id: str,
    request: PerformanceComponentEconomicsRequest,
    rows: list[PerformanceComponentEconomicsRow],
    transactions: list[PerformanceEconomicsTransactionReadRecord],
    portfolio_base_currency: str,
    request_scope_fingerprint: str | None = None,
    has_more: bool = False,
    next_page_token: str | None = None,
) -> PerformanceComponentEconomicsResponse:
    observed_component_families = observed_performance_component_families(rows)
    state = performance_component_economics_supportability_state(rows=rows, has_more=has_more)
    reason = performance_component_economics_supportability_reason(
        rows=rows,
        has_more=has_more,
    )
    fingerprint = request_scope_fingerprint or performance_component_economics_request_fingerprint(
        portfolio_id=portfolio_id, request=request
    )

    return PerformanceComponentEconomicsResponse(
        portfolio_id=portfolio_id,
        as_of_date=request.as_of_date,
        window=request.window,
        request_fingerprint=fingerprint,
        rows=rows,
        component_totals=build_performance_component_economics_totals(
            rows,
            portfolio_base_currency=portfolio_base_currency,
        ),
        page=ReferencePageMetadata(
            page_size=request.page.page_size,
            sort_key="security_id:asc,transaction_date:asc,transaction_id:asc",
            returned_component_count=len(rows),
            request_scope_fingerprint=fingerprint,
            next_page_token=next_page_token,
        ),
        supportability=PerformanceComponentEconomicsSupportability(
            state=state,
            reason=reason,
            source_row_count=len(rows),
            observed_component_families=observed_component_families,
            missing_component_families=missing_performance_component_families(
                observed_component_families
            ),
        ),
        lineage=performance_component_economics_source_lineage(),
        **source_product_runtime_metadata_without_as_of_date(
            request.as_of_date,
            tenant_id=request.tenant_id,
            data_quality_status=performance_component_economics_data_quality_status(
                rows=rows,
                has_more=has_more,
            ),
            latest_evidence_timestamp=latest_performance_evidence_timestamp(transactions),
        ),
    )


def performance_component_economics_request_fingerprint(
    *,
    portfolio_id: str,
    request: PerformanceComponentEconomicsRequest,
) -> str:
    return build_request_fingerprint(
        {
            "portfolio_id": portfolio_id,
            "as_of_date": request.as_of_date.isoformat(),
            "window": {
                "start_date": request.window.start_date.isoformat(),
                "end_date": request.window.end_date.isoformat(),
            },
            "security_ids": sorted(request.security_ids or []),
            "transaction_types": sorted(request.transaction_types or []),
            "tenant_id": request.tenant_id,
        }
    )
