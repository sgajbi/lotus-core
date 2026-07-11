"""Application policy for paged portfolio tax-lot evidence."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any, Literal, cast

from portfolio_common.reference_data_paging import ReferencePageMetadata
from portfolio_common.request_fingerprints import request_fingerprint

from ...contracts.portfolio_tax_lots import (
    PortfolioTaxLotRecord,
    PortfolioTaxLotWindowRequest,
    PortfolioTaxLotWindowResponse,
    PortfolioTaxLotWindowSupportability,
)
from ...domain.dpm_source_readiness import PortfolioTaxLotEvidence
from ...ports.dpm_source_readiness import (
    DpmPortfolioStateReader,
    DpmTaxLotPageTokenCodec,
)
from .metadata import dpm_source_runtime_metadata

TaxLotSupportabilityState = Literal["READY", "DEGRADED", "INCOMPLETE", "UNAVAILABLE"]

TAX_LOTS_READY = "TAX_LOTS_READY"
TAX_LOTS_EMPTY = "TAX_LOTS_EMPTY"
TAX_LOTS_PAGE_PARTIAL = "TAX_LOTS_PAGE_PARTIAL"
TAX_LOTS_MISSING_FOR_REQUESTED_SECURITIES = "TAX_LOTS_MISSING_FOR_REQUESTED_SECURITIES"
TAX_LOTS_INSTRUMENT_REFERENCE_MISSING = "TAX_LOTS_INSTRUMENT_REFERENCE_MISSING"


@dataclass(frozen=True, slots=True)
class PortfolioTaxLotRequestScope:
    """Request-bound continuation scope and decoded keyset position."""

    fingerprint: str
    after_sort_key: tuple[date, str] | None


@dataclass(slots=True)
class PortfolioTaxLotService:
    """Read one bounded, supportable portfolio tax-lot evidence page."""

    reader: DpmPortfolioStateReader
    page_tokens: DpmTaxLotPageTokenCodec
    clock: Callable[[], datetime] = lambda: datetime.now(UTC)

    async def resolve(
        self,
        *,
        portfolio_id: str,
        request: PortfolioTaxLotWindowRequest,
    ) -> PortfolioTaxLotWindowResponse:
        if not await self.reader.portfolio_exists(portfolio_id):
            raise LookupError(f"Portfolio with id {portfolio_id} not found")
        scope = portfolio_tax_lot_request_scope(
            portfolio_id=portfolio_id,
            request=request,
            cursor=self.page_tokens.decode(request.page.page_token),
        )
        evidence = await self.reader.list_portfolio_tax_lots(
            portfolio_id=portfolio_id,
            as_of_date=request.as_of_date,
            security_ids=request.security_ids,
            include_closed_lots=request.include_closed_lots,
            lot_status_filter=request.lot_status_filter,
            after_sort_key=scope.after_sort_key,
            limit=request.page.page_size + 1,
        )
        has_more = len(evidence) > request.page.page_size
        page_evidence = evidence[: request.page.page_size]
        known_security_ids = await self.reader.list_known_instrument_security_ids(
            _security_ids(page_evidence)
        )
        return build_portfolio_tax_lot_response(
            portfolio_id=portfolio_id,
            request=request,
            scope=scope,
            evidence=page_evidence,
            has_more=has_more,
            next_page_token=_next_page_token(
                scope=scope,
                evidence=page_evidence,
                has_more=has_more,
                page_tokens=self.page_tokens,
            ),
            known_security_ids=known_security_ids,
            generated_at=self.clock(),
        )


def portfolio_tax_lot_request_scope(
    *,
    portfolio_id: str,
    request: PortfolioTaxLotWindowRequest,
    cursor: Mapping[str, Any],
) -> PortfolioTaxLotRequestScope:
    """Bind a continuation token to all filters that influence tax-lot selection."""

    fingerprint = request_fingerprint(
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
    if token_scope and token_scope != fingerprint:
        raise ValueError("Portfolio tax-lot page token does not match request scope.")
    return PortfolioTaxLotRequestScope(
        fingerprint=fingerprint,
        after_sort_key=_after_sort_key(cursor),
    )


def build_portfolio_tax_lot_response(
    *,
    portfolio_id: str,
    request: PortfolioTaxLotWindowRequest,
    scope: PortfolioTaxLotRequestScope,
    evidence: list[PortfolioTaxLotEvidence],
    has_more: bool,
    next_page_token: str | None,
    known_security_ids: set[str],
    generated_at: datetime,
) -> PortfolioTaxLotWindowResponse:
    """Map lot evidence and derive page-level source supportability."""

    lots = [portfolio_tax_lot_record(row) for row in evidence]
    missing_security_ids = _missing_requested_security_ids(
        request=request,
        lots=lots,
        has_more=has_more,
    )
    missing_instrument_ids = [
        security_id
        for security_id in _security_ids(evidence)
        if security_id not in {value.strip() for value in known_security_ids if value.strip()}
    ]
    state, reason = _supportability_state(
        request=request,
        lots=lots,
        has_more=has_more,
        missing_security_ids=missing_security_ids,
        missing_instrument_ids=missing_instrument_ids,
    )
    supportability = PortfolioTaxLotWindowSupportability(
        state=state,
        reason=reason,
        requested_security_count=(
            len(request.security_ids) if request.security_ids is not None else None
        ),
        returned_lot_count=len(lots),
        missing_security_ids=missing_security_ids,
        missing_instrument_security_ids=missing_instrument_ids,
        missing_instrument_reference_count=len(missing_instrument_ids),
        reason_codes=_reason_codes(
            lots=lots,
            has_more=has_more,
            missing_security_ids=missing_security_ids,
            missing_instrument_ids=missing_instrument_ids,
        ),
    )
    page = ReferencePageMetadata(
        page_size=request.page.page_size,
        sort_key="acquisition_date:asc,lot_id:asc",
        returned_component_count=len(lots),
        request_scope_fingerprint=scope.fingerprint,
        next_page_token=next_page_token,
    )
    lineage = {"source_system": "position_lot_state", "contract_version": "rfc_087_v1"}
    content_payload = {
        "portfolio_id": portfolio_id,
        "as_of_date": request.as_of_date,
        "lots": [lot.model_dump(mode="json") for lot in lots],
        "page_scope": {
            "page_size": page.page_size,
            "sort_key": page.sort_key,
            "returned_component_count": page.returned_component_count,
            "request_scope_fingerprint": page.request_scope_fingerprint,
        },
        "supportability": supportability.model_dump(mode="json"),
        "lineage": lineage,
    }
    return PortfolioTaxLotWindowResponse(
        portfolio_id=portfolio_id,
        lots=lots,
        page=page,
        supportability=supportability,
        lineage=lineage,
        **dpm_source_runtime_metadata(
            product_name="PortfolioTaxLotWindow",
            source_key=portfolio_id,
            as_of_date=request.as_of_date,
            generated_at=generated_at,
            tenant_id=request.tenant_id,
            data_quality_status=_data_quality_status(state),
            latest_evidence_timestamp=_latest_evidence_timestamp(evidence),
            content_payload=content_payload,
            lineage=lineage,
        ),
    )


def _after_sort_key(cursor: Mapping[str, Any]) -> tuple[date, str] | None:
    acquisition_date = cursor.get("last_acquisition_date")
    lot_id = cursor.get("last_lot_id")
    if not acquisition_date or not lot_id:
        return None
    return date.fromisoformat(str(acquisition_date)), str(lot_id)


def _next_page_token(
    *,
    scope: PortfolioTaxLotRequestScope,
    evidence: list[PortfolioTaxLotEvidence],
    has_more: bool,
    page_tokens: DpmTaxLotPageTokenCodec,
) -> str | None:
    if not has_more or not evidence:
        return None
    last_lot = evidence[-1]
    return cast(
        str,
        page_tokens.encode(
            {
                "scope_fingerprint": scope.fingerprint,
                "last_acquisition_date": last_lot.acquisition_date.isoformat(),
                "last_lot_id": last_lot.lot_id,
            }
        ),
    )


def portfolio_tax_lot_record(evidence: PortfolioTaxLotEvidence) -> PortfolioTaxLotRecord:
    """Map immutable lot evidence into the public source-product record."""

    return PortfolioTaxLotRecord(
        portfolio_id=evidence.portfolio_id,
        security_id=evidence.security_id.strip(),
        instrument_id=evidence.instrument_id.strip(),
        lot_id=evidence.lot_id,
        open_quantity=evidence.open_quantity,
        original_quantity=evidence.original_quantity,
        acquisition_date=evidence.acquisition_date,
        cost_basis_base=evidence.lot_cost_base,
        cost_basis_local=evidence.lot_cost_local,
        local_currency=evidence.local_currency,
        tax_lot_status="OPEN" if evidence.open_quantity > 0 else "CLOSED",
        source_transaction_id=evidence.source_transaction_id,
        source_lineage={
            "source_system": evidence.source_system or "position_lot_state",
            "source_transaction_id": evidence.source_transaction_id,
            "calculation_policy_id": evidence.calculation_policy_id or "UNKNOWN",
            "calculation_policy_version": evidence.calculation_policy_version or "UNKNOWN",
        },
    )


def _security_ids(evidence: list[PortfolioTaxLotEvidence]) -> list[str]:
    return list(
        dict.fromkeys(row.security_id.strip() for row in evidence if row.security_id.strip())
    )


def _missing_requested_security_ids(
    *,
    request: PortfolioTaxLotWindowRequest,
    lots: list[PortfolioTaxLotRecord],
    has_more: bool,
) -> list[str]:
    if has_more:
        return []
    requested = {security_id.strip() for security_id in request.security_ids or []}
    returned = {lot.security_id for lot in lots}
    return sorted(requested - returned)


def _supportability_state(
    *,
    request: PortfolioTaxLotWindowRequest,
    lots: list[PortfolioTaxLotRecord],
    has_more: bool,
    missing_security_ids: list[str],
    missing_instrument_ids: list[str],
) -> tuple[TaxLotSupportabilityState, str]:
    if not lots and not request.security_ids:
        return "UNAVAILABLE", TAX_LOTS_EMPTY
    if has_more:
        return "DEGRADED", TAX_LOTS_PAGE_PARTIAL
    if request.security_ids and missing_security_ids:
        return "INCOMPLETE", TAX_LOTS_MISSING_FOR_REQUESTED_SECURITIES
    if missing_instrument_ids:
        return "DEGRADED", TAX_LOTS_INSTRUMENT_REFERENCE_MISSING
    return "READY", TAX_LOTS_READY


def _reason_codes(
    *,
    lots: list[PortfolioTaxLotRecord],
    has_more: bool,
    missing_security_ids: list[str],
    missing_instrument_ids: list[str],
) -> list[str]:
    if not lots and not missing_security_ids:
        return [TAX_LOTS_EMPTY]
    reasons: list[str] = []
    if has_more:
        reasons.append(TAX_LOTS_PAGE_PARTIAL)
    if missing_security_ids:
        reasons.append(TAX_LOTS_MISSING_FOR_REQUESTED_SECURITIES)
    if missing_instrument_ids:
        reasons.append(TAX_LOTS_INSTRUMENT_REFERENCE_MISSING)
    return reasons or [TAX_LOTS_READY]


def _data_quality_status(state: TaxLotSupportabilityState) -> str:
    if state == "READY":
        return "COMPLETE"
    if state == "UNAVAILABLE":
        return "MISSING"
    return "PARTIAL"


def _latest_evidence_timestamp(evidence: list[PortfolioTaxLotEvidence]) -> datetime | None:
    timestamps = [row.updated_at for row in evidence if row.updated_at is not None]
    return max(timestamps) if timestamps else None
