from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from ..dtos.reference_integration_dto import (
    PerformanceComponentEconomicsRequest,
    PerformanceComponentEconomicsResponse,
    PerformanceComponentEconomicsRow,
)
from ..repositories.currency_codes import normalize_currency_code
from . import performance_component_economics_policy as _policy
from .performance_component_economics_response import (
    build_performance_component_economics_response,
    performance_component_economics_request_fingerprint,
)
from .performance_component_economics_rows import (
    build_performance_component_economics_rows as build_performance_component_economics_rows,
)

SOURCE_CONTRACT_VERSION = _policy.SOURCE_CONTRACT_VERSION
build_performance_component_economics_totals = _policy.build_performance_component_economics_totals
latest_performance_evidence_timestamp = _policy.latest_performance_evidence_timestamp
missing_performance_component_families = _policy.missing_performance_component_families
observed_performance_component_families = _policy.observed_performance_component_families
performance_component_economics_data_quality_status = (
    _policy.performance_component_economics_data_quality_status
)
performance_component_economics_source_lineage = (
    _policy.performance_component_economics_source_lineage
)
performance_component_economics_supportability_reason = (
    _policy.performance_component_economics_supportability_reason
)
performance_component_economics_supportability_state = (
    _policy.performance_component_economics_supportability_state
)

_PerformanceEconomicsCursor = tuple[str, str, str] | tuple[()]


@dataclass(frozen=True)
class PerformanceComponentEconomicsPageScope:
    request_fingerprint: str
    after_key: _PerformanceEconomicsCursor


def performance_component_economics_page_scope(
    *,
    portfolio_id: str,
    request: PerformanceComponentEconomicsRequest,
    cursor: dict[str, Any],
) -> PerformanceComponentEconomicsPageScope:
    request_fingerprint = performance_component_economics_request_fingerprint(
        portfolio_id=portfolio_id, request=request
    )
    token_scope = cursor.get("scope_fingerprint")
    if token_scope and token_scope != request_fingerprint:
        raise ValueError("Performance component economics page token does not match request scope.")
    last_row_key = tuple(cursor.get("last_row_key") or ())
    if len(last_row_key) not in (0, 3):
        raise ValueError("Performance component economics page token has an invalid row key.")
    return PerformanceComponentEconomicsPageScope(
        request_fingerprint=request_fingerprint,
        after_key=last_row_key,
    )


def performance_component_economics_next_page_token_payload(
    *,
    page_scope: PerformanceComponentEconomicsPageScope,
    rows: list[PerformanceComponentEconomicsRow],
    has_more: bool,
) -> dict[str, Any] | None:
    if not has_more or not rows:
        return None
    last_row = rows[-1]
    return {
        "scope_fingerprint": page_scope.request_fingerprint,
        "last_row_key": [
            last_row.security_id,
            last_row.transaction_date.isoformat(),
            last_row.transaction_id,
        ],
    }


def performance_component_economics_page_token(
    *,
    page_scope: PerformanceComponentEconomicsPageScope,
    rows: list[PerformanceComponentEconomicsRow],
    has_more: bool,
    encode_page_token: Callable[[dict[str, Any]], str],
) -> str | None:
    payload = performance_component_economics_next_page_token_payload(
        page_scope=page_scope,
        rows=rows,
        has_more=has_more,
    )
    if payload is None:
        return None
    return encode_page_token(payload)


async def resolve_performance_component_economics_response(
    *,
    repository: Any,
    portfolio_id: str,
    request: PerformanceComponentEconomicsRequest,
    decode_page_token: Callable[[str | None], dict[str, Any]],
    encode_page_token: Callable[[dict[str, Any]], str],
) -> PerformanceComponentEconomicsResponse:
    if not await repository.portfolio_exists(portfolio_id):
        raise LookupError(f"Portfolio with id {portfolio_id} not found")

    portfolio_base_currency = await repository.get_portfolio_base_currency(portfolio_id)
    if portfolio_base_currency is None:
        raise LookupError(f"Portfolio with id {portfolio_id} not found")
    normalized_portfolio_base_currency = normalize_currency_code(portfolio_base_currency)
    page_scope = performance_component_economics_page_scope(
        portfolio_id=portfolio_id,
        request=request,
        cursor=decode_page_token(request.page.page_token),
    )
    transactions = await repository.list_performance_component_economics_evidence(
        portfolio_id=portfolio_id,
        start_date=request.window.start_date,
        end_date=request.window.end_date,
        as_of_date=request.as_of_date,
        security_ids=request.security_ids,
        transaction_types=request.transaction_types,
        after_key=page_scope.after_key,
        limit=request.page.page_size + 1,
    )
    has_more = len(transactions) > request.page.page_size
    page_transactions = transactions[: request.page.page_size]
    rows = build_performance_component_economics_rows(page_transactions)
    next_page_token = performance_component_economics_page_token(
        page_scope=page_scope,
        rows=rows,
        has_more=has_more,
        encode_page_token=encode_page_token,
    )
    return build_performance_component_economics_response(
        portfolio_id=portfolio_id,
        request=request,
        rows=rows,
        transactions=page_transactions,
        portfolio_base_currency=normalized_portfolio_base_currency,
        request_scope_fingerprint=page_scope.request_fingerprint,
        has_more=has_more,
        next_page_token=next_page_token,
    )
