from __future__ import annotations

from datetime import date
from typing import Any, Mapping

from ..dtos.reference_integration_dto import (
    PortfolioTaxLotWindowRequest,
    PortfolioTaxLotWindowResponse,
    PortfolioTaxLotWindowSupportability,
    ReferencePageMetadata,
)
from ..repositories.identifier_normalization import normalize_security_id
from .reference_data_helpers import latest_reference_evidence_timestamp
from .reference_data_mappers import portfolio_tax_lot_record
from .source_data_runtime import source_product_runtime_metadata_without_as_of_date


def portfolio_tax_lot_after_sort_key(cursor: Mapping[str, Any]) -> tuple[date, str] | None:
    if not (cursor.get("last_acquisition_date") and cursor.get("last_lot_id")):
        return None
    return (
        date.fromisoformat(str(cursor["last_acquisition_date"])),
        str(cursor["last_lot_id"]),
    )


def build_portfolio_tax_lot_window_response(
    *,
    portfolio_id: str,
    request: PortfolioTaxLotWindowRequest,
    request_scope_fingerprint: str,
    page_rows: list[tuple[Any, str | None]],
    has_more: bool,
    next_page_token: str | None,
) -> PortfolioTaxLotWindowResponse:
    lots = [
        portfolio_tax_lot_record(lot, local_currency=local_currency)
        for lot, local_currency in page_rows
    ]

    requested_security_ids = {
        normalize_security_id(security_id) for security_id in request.security_ids or []
    }
    returned_security_ids = {normalize_security_id(lot.security_id) for lot in lots}
    missing_security_ids = (
        [] if has_more else sorted(requested_security_ids - returned_security_ids)
    )

    supportability_state = "READY"
    supportability_reason = "TAX_LOTS_READY"
    if not lots and not request.security_ids:
        supportability_state = "UNAVAILABLE"
        supportability_reason = "TAX_LOTS_EMPTY"
    elif has_more:
        supportability_state = "DEGRADED"
        supportability_reason = "TAX_LOTS_PAGE_PARTIAL"
    elif request.security_ids and missing_security_ids:
        supportability_state = "INCOMPLETE"
        supportability_reason = "TAX_LOTS_MISSING_FOR_REQUESTED_SECURITIES"

    data_quality_status = (
        "COMPLETE"
        if supportability_state == "READY"
        else "MISSING"
        if supportability_state == "UNAVAILABLE"
        else "PARTIAL"
    )

    return PortfolioTaxLotWindowResponse(
        portfolio_id=portfolio_id,
        as_of_date=request.as_of_date,
        lots=lots,
        page=ReferencePageMetadata(
            page_size=request.page.page_size,
            sort_key="acquisition_date:asc,lot_id:asc",
            returned_component_count=len(lots),
            request_scope_fingerprint=request_scope_fingerprint,
            next_page_token=next_page_token,
        ),
        supportability=PortfolioTaxLotWindowSupportability(
            state=supportability_state,
            reason=supportability_reason,
            requested_security_count=(
                len(request.security_ids) if request.security_ids is not None else None
            ),
            returned_lot_count=len(lots),
            missing_security_ids=missing_security_ids,
        ),
        lineage={
            "source_system": "position_lot_state",
            "contract_version": "rfc_087_v1",
        },
        **source_product_runtime_metadata_without_as_of_date(
            request.as_of_date,
            data_quality_status=data_quality_status,
            latest_evidence_timestamp=latest_reference_evidence_timestamp(
                [lot for lot, _ in page_rows]
            ),
        ),
    )
