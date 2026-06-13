from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal, Mapping

from ..dtos.reference_integration_dto import (
    PortfolioTaxLotWindowRequest,
    PortfolioTaxLotWindowResponse,
    PortfolioTaxLotWindowSupportability,
    ReferencePageMetadata,
)
from ..repositories.identifier_normalization import normalize_security_id
from .reference_data_helpers import latest_reference_evidence_timestamp
from .reference_data_mappers import portfolio_tax_lot_record
from .request_fingerprint import request_fingerprint as build_request_fingerprint
from .source_data_runtime import source_product_runtime_metadata_without_as_of_date


@dataclass(frozen=True)
class PortfolioTaxLotWindowRequestScope:
    request_fingerprint: str
    after_sort_key: tuple[date, str] | None


_TaxLotSupportabilityState = Literal["READY", "DEGRADED", "INCOMPLETE", "UNAVAILABLE"]


@dataclass(frozen=True)
class _PortfolioTaxLotSupportabilityContext:
    supportability: PortfolioTaxLotWindowSupportability
    data_quality_status: str


def portfolio_tax_lot_after_sort_key(cursor: Mapping[str, Any]) -> tuple[date, str] | None:
    if not (cursor.get("last_acquisition_date") and cursor.get("last_lot_id")):
        return None
    return (
        date.fromisoformat(str(cursor["last_acquisition_date"])),
        str(cursor["last_lot_id"]),
    )


def portfolio_tax_lot_window_request_scope(
    *,
    portfolio_id: str,
    request: PortfolioTaxLotWindowRequest,
    cursor: Mapping[str, Any],
) -> PortfolioTaxLotWindowRequestScope:
    request_fingerprint = build_request_fingerprint(
        {
            "portfolio_id": portfolio_id,
            "as_of_date": request.as_of_date.isoformat(),
            "security_ids": sorted(request.security_ids or []),
            "lot_status_filter": request.lot_status_filter,
            "include_closed_lots": request.include_closed_lots,
            "tenant_id": request.tenant_id,
        }
    )
    token_scope = cursor.get("scope_fingerprint")
    if token_scope and token_scope != request_fingerprint:
        raise ValueError("Portfolio tax-lot page token does not match request scope.")

    return PortfolioTaxLotWindowRequestScope(
        request_fingerprint=request_fingerprint,
        after_sort_key=portfolio_tax_lot_after_sort_key(cursor),
    )


def portfolio_tax_lot_next_page_token_payload(
    *,
    request_scope: PortfolioTaxLotWindowRequestScope,
    has_more: bool,
    page_rows: list[tuple[Any, str | None]],
) -> dict[str, str] | None:
    if not has_more or not page_rows:
        return None
    last_lot = page_rows[-1][0]
    return {
        "scope_fingerprint": request_scope.request_fingerprint,
        "last_acquisition_date": last_lot.acquisition_date.isoformat(),
        "last_lot_id": last_lot.lot_id,
    }


def portfolio_tax_lot_page_token(
    *,
    request_scope: PortfolioTaxLotWindowRequestScope,
    has_more: bool,
    page_rows: list[tuple[Any, str | None]],
    encode_page_token: Callable[[dict[str, str]], str],
) -> str | None:
    payload = portfolio_tax_lot_next_page_token_payload(
        request_scope=request_scope,
        has_more=has_more,
        page_rows=page_rows,
    )
    if payload is None:
        return None
    return encode_page_token(payload)


async def resolve_portfolio_tax_lot_window_response(
    *,
    repository: Any,
    portfolio_id: str,
    request: PortfolioTaxLotWindowRequest,
    decode_page_token: Callable[[str | None], dict[str, Any]],
    encode_page_token: Callable[[dict[str, str]], str],
) -> PortfolioTaxLotWindowResponse:
    if not await repository.portfolio_exists(portfolio_id):
        raise LookupError(f"Portfolio with id {portfolio_id} not found")

    request_scope = portfolio_tax_lot_window_request_scope(
        portfolio_id=portfolio_id,
        request=request,
        cursor=decode_page_token(request.page.page_token),
    )
    rows = await repository.list_portfolio_tax_lots(
        portfolio_id=portfolio_id,
        as_of_date=request.as_of_date,
        security_ids=request.security_ids,
        include_closed_lots=request.include_closed_lots,
        lot_status_filter=request.lot_status_filter,
        after_sort_key=request_scope.after_sort_key,
        limit=request.page.page_size + 1,
    )
    has_more = len(rows) > request.page.page_size
    page_rows = rows[: request.page.page_size]
    next_page_token = portfolio_tax_lot_page_token(
        request_scope=request_scope,
        has_more=has_more,
        page_rows=page_rows,
        encode_page_token=encode_page_token,
    )

    return build_portfolio_tax_lot_window_response(
        portfolio_id=portfolio_id,
        request=request,
        request_scope_fingerprint=request_scope.request_fingerprint,
        page_rows=page_rows,
        has_more=has_more,
        next_page_token=next_page_token,
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
    lots = _portfolio_tax_lot_records(page_rows)
    supportability_context = _portfolio_tax_lot_supportability_context(
        request=request,
        lots=lots,
        has_more=has_more,
    )

    return PortfolioTaxLotWindowResponse(
        portfolio_id=portfolio_id,
        as_of_date=request.as_of_date,
        lots=lots,
        page=_portfolio_tax_lot_page_metadata(
            request=request,
            lots=lots,
            request_scope_fingerprint=request_scope_fingerprint,
            next_page_token=next_page_token,
        ),
        supportability=supportability_context.supportability,
        lineage=_portfolio_tax_lot_lineage(),
        **source_product_runtime_metadata_without_as_of_date(
            request.as_of_date,
            data_quality_status=supportability_context.data_quality_status,
            latest_evidence_timestamp=latest_reference_evidence_timestamp(
                [lot for lot, _ in page_rows]
            ),
        ),
    )


def _portfolio_tax_lot_records(page_rows: list[tuple[Any, str | None]]) -> list[Any]:
    return [
        portfolio_tax_lot_record(lot, local_currency=local_currency)
        for lot, local_currency in page_rows
    ]


def _portfolio_tax_lot_supportability_context(
    *,
    request: PortfolioTaxLotWindowRequest,
    lots: list[Any],
    has_more: bool,
) -> _PortfolioTaxLotSupportabilityContext:
    missing_security_ids = _missing_tax_lot_security_ids(
        request=request,
        lots=lots,
        has_more=has_more,
    )
    state, reason = _portfolio_tax_lot_supportability_state(
        request=request,
        lots=lots,
        has_more=has_more,
        missing_security_ids=missing_security_ids,
    )
    return _PortfolioTaxLotSupportabilityContext(
        supportability=PortfolioTaxLotWindowSupportability(
            state=state,
            reason=reason,
            requested_security_count=_requested_tax_lot_security_count(request),
            returned_lot_count=len(lots),
            missing_security_ids=missing_security_ids,
        ),
        data_quality_status=_portfolio_tax_lot_data_quality_status(state),
    )


def _missing_tax_lot_security_ids(
    *,
    request: PortfolioTaxLotWindowRequest,
    lots: list[Any],
    has_more: bool,
) -> list[str]:
    if has_more:
        return []
    requested_security_ids = {
        normalize_security_id(security_id) for security_id in request.security_ids or []
    }
    returned_security_ids = {normalize_security_id(lot.security_id) for lot in lots}
    return sorted(requested_security_ids - returned_security_ids)


def _portfolio_tax_lot_supportability_state(
    *,
    request: PortfolioTaxLotWindowRequest,
    lots: list[Any],
    has_more: bool,
    missing_security_ids: list[str],
) -> tuple[_TaxLotSupportabilityState, str]:
    if not lots and not request.security_ids:
        return "UNAVAILABLE", "TAX_LOTS_EMPTY"
    if has_more:
        return "DEGRADED", "TAX_LOTS_PAGE_PARTIAL"
    if request.security_ids and missing_security_ids:
        return "INCOMPLETE", "TAX_LOTS_MISSING_FOR_REQUESTED_SECURITIES"
    return "READY", "TAX_LOTS_READY"


def _requested_tax_lot_security_count(
    request: PortfolioTaxLotWindowRequest,
) -> int | None:
    if request.security_ids is None:
        return None
    return len(request.security_ids)


def _portfolio_tax_lot_data_quality_status(
    state: _TaxLotSupportabilityState,
) -> str:
    if state == "READY":
        return "COMPLETE"
    if state == "UNAVAILABLE":
        return "MISSING"
    return "PARTIAL"


def _portfolio_tax_lot_page_metadata(
    *,
    request: PortfolioTaxLotWindowRequest,
    lots: list[Any],
    request_scope_fingerprint: str,
    next_page_token: str | None,
) -> ReferencePageMetadata:
    return ReferencePageMetadata(
        page_size=request.page.page_size,
        sort_key="acquisition_date:asc,lot_id:asc",
        returned_component_count=len(lots),
        request_scope_fingerprint=request_scope_fingerprint,
        next_page_token=next_page_token,
    )


def _portfolio_tax_lot_lineage() -> dict[str, str]:
    return {
        "source_system": "position_lot_state",
        "contract_version": "rfc_087_v1",
    }
