"""Application use cases for CIO cohorts and DPM portfolio populations."""

from dataclasses import asdict, dataclass
from datetime import date, datetime
from typing import Any, Literal, cast

from portfolio_common.domain.tenant import TenantContext, bind_tenant_authority
from portfolio_common.logging_utils import normalize_lineage_value
from portfolio_common.reference_data_paging import ReferencePageMetadata
from portfolio_common.request_fingerprints import request_fingerprint
from portfolio_common.runtime_providers import Clock
from portfolio_common.source_data_product_metadata import (
    source_data_product_runtime_metadata,
    stable_content_hash,
)

from ..contracts.dpm_portfolio_population import (
    CioModelChangeAffectedCohortRequest,
    CioModelChangeAffectedCohortResponse,
    CioModelChangeAffectedCohortSupportability,
    CioModelChangeAffectedMandate,
    DpmPortfolioUniverseCandidate,
    DpmPortfolioUniverseCandidateRequest,
    DpmPortfolioUniverseCandidateResponse,
    DpmPortfolioUniverseCandidateSelectionBasis,
    DpmPortfolioUniverseCandidateSupportability,
)
from ..domain.dpm_portfolio_population import (
    ApprovedModelPortfolio,
    DiscretionaryMandatePopulationMember,
)
from ..ports.dpm_portfolio_population import (
    DpmPopulationPageTokenCodec,
    DpmPortfolioPopulationReader,
)


@dataclass(frozen=True, slots=True)
class DpmPortfolioUniverseScope:
    """Normalized universe filters bound to a continuation sequence."""

    tenant_id: str | None
    booking_center_code: str | None
    model_portfolio_ids: tuple[str, ...]
    fingerprint: str


class DpmPortfolioPopulationService:
    """Resolve approved-model cohorts and effective DPM population pages."""

    def __init__(
        self,
        *,
        reader: DpmPortfolioPopulationReader,
        page_tokens: DpmPopulationPageTokenCodec,
        clock: Clock,
    ) -> None:
        self._reader = reader
        self._page_tokens = page_tokens
        self._clock = clock

    async def resolve_cio_model_change_cohort(
        self,
        *,
        tenant_context: TenantContext,
        model_portfolio_id: str,
        request: CioModelChangeAffectedCohortRequest,
    ) -> CioModelChangeAffectedCohortResponse | None:
        tenant_id = bind_tenant_authority(request.tenant_id, tenant_context)
        request = request.model_copy(update={"tenant_id": tenant_id})
        model = await self._reader.resolve_approved_model(
            model_portfolio_id=model_portfolio_id,
            as_of_date=request.as_of_date,
        )
        if model is None:
            return None
        mandates = await self._reader.list_affected_mandates(
            tenant_id=tenant_id,
            model_portfolio_id=model_portfolio_id,
            as_of_date=request.as_of_date,
            booking_center_code=request.booking_center_code,
            include_inactive_mandates=request.include_inactive_mandates,
        )
        return _cio_cohort_response(
            model=model,
            mandates=mandates,
            request=request,
            generated_at=self._clock.utc_now(),
        )

    async def resolve_universe_candidates(
        self,
        *,
        tenant_context: TenantContext,
        request: DpmPortfolioUniverseCandidateRequest,
    ) -> DpmPortfolioUniverseCandidateResponse:
        tenant_id = bind_tenant_authority(request.tenant_id, tenant_context)
        request = request.model_copy(update={"tenant_id": tenant_id})
        scope = _universe_scope(request)
        after_sort_key = _after_sort_key(
            cursor=self._page_tokens.decode(request.page.page_token),
            scope_fingerprint=scope.fingerprint,
        )
        rows = await self._reader.list_universe_candidates(
            tenant_id=tenant_id,
            as_of_date=request.as_of_date,
            booking_center_code=scope.booking_center_code,
            model_portfolio_ids=scope.model_portfolio_ids,
            include_inactive_mandates=request.include_inactive_mandates,
            after_sort_key=after_sort_key,
            limit=request.page.page_size + 1,
        )
        has_more = len(rows) > request.page.page_size
        page_rows = rows[: request.page.page_size]
        return _universe_response(
            request=request,
            scope=scope,
            after_sort_key=after_sort_key,
            rows=page_rows,
            has_more=has_more,
            next_page_token=_next_page_token(
                page_tokens=self._page_tokens,
                scope_fingerprint=scope.fingerprint,
                rows=page_rows,
                has_more=has_more,
            ),
            generated_at=self._clock.utc_now(),
        )


def _universe_scope(request: DpmPortfolioUniverseCandidateRequest) -> DpmPortfolioUniverseScope:
    tenant_id = normalize_lineage_value(request.tenant_id)
    booking_center_code = (
        request.booking_center_code.strip() if request.booking_center_code else None
    )
    booking_center_code = booking_center_code or None
    model_ids = tuple(
        sorted({value.strip() for value in request.model_portfolio_ids if value.strip()})
    )
    fingerprint = request_fingerprint(
        {
            "product_name": "DpmPortfolioUniverseCandidate",
            "as_of_date": request.as_of_date.isoformat(),
            "booking_center_code": booking_center_code,
            "model_portfolio_ids": model_ids,
            "include_inactive_mandates": request.include_inactive_mandates,
            "tenant_id": tenant_id,
        }
    )
    return DpmPortfolioUniverseScope(tenant_id, booking_center_code, model_ids, fingerprint)


def _after_sort_key(*, cursor: dict[str, Any], scope_fingerprint: str) -> tuple[str, str] | None:
    token_scope = cursor.get("scope_fingerprint")
    if token_scope and token_scope != scope_fingerprint:
        raise ValueError("DPM portfolio-universe page token does not match request scope.")
    if cursor.get("last_portfolio_id") and cursor.get("last_mandate_id"):
        return str(cursor["last_portfolio_id"]), str(cursor["last_mandate_id"])
    return None


def _next_page_token(
    *,
    page_tokens: DpmPopulationPageTokenCodec,
    scope_fingerprint: str,
    rows: list[DiscretionaryMandatePopulationMember],
    has_more: bool,
) -> str | None:
    if not has_more or not rows:
        return None
    last = rows[-1]
    return cast(
        str,
        page_tokens.encode(
            {
                "scope_fingerprint": scope_fingerprint,
                "last_portfolio_id": last.portfolio_id,
                "last_mandate_id": last.mandate_id,
            }
        ),
    )


def _cio_cohort_response(
    *,
    model: ApprovedModelPortfolio,
    mandates: list[DiscretionaryMandatePopulationMember],
    request: CioModelChangeAffectedCohortRequest,
    generated_at: datetime,
) -> CioModelChangeAffectedCohortResponse:
    affected = [_affected_mandate(row) for row in mandates]
    state: Literal["READY", "INCOMPLETE"] = "READY" if affected else "INCOMPLETE"
    reason = "CIO_MODEL_CHANGE_COHORT_READY" if affected else "CIO_MODEL_CHANGE_COHORT_EMPTY"
    filters = ["admitted_tenant_ownership", "model_portfolio_id", "as_of_date"]
    if request.booking_center_code:
        filters.append("booking_center_code")
    if not request.include_inactive_mandates:
        filters.append("active_discretionary_authority")
    fingerprint = request_fingerprint(
        {
            "product_name": "CioModelChangeAffectedCohort",
            "model_portfolio_id": model.model_portfolio_id,
            "model_portfolio_version": model.model_portfolio_version,
            "tenant_id": request.tenant_id,
            "as_of_date": request.as_of_date.isoformat(),
            "booking_center_code": request.booking_center_code,
            "include_inactive_mandates": request.include_inactive_mandates,
            "mandate_ids": [row.mandate_id for row in affected],
            "portfolio_ids": [row.portfolio_id for row in affected],
        }
    )
    return CioModelChangeAffectedCohortResponse(
        model_portfolio_id=model.model_portfolio_id,
        model_portfolio_version=model.model_portfolio_version,
        model_change_event_id=(
            f"cio_model_change:{model.model_portfolio_id}:{model.model_portfolio_version}:"
            f"{request.as_of_date.isoformat()}:{fingerprint}"
        ),
        approval_state=model.approval_status,
        approved_at=model.approved_at,
        effective_from=model.effective_from,
        effective_to=model.effective_to,
        affected_mandates=affected,
        supportability=CioModelChangeAffectedCohortSupportability(
            state=state,
            reason=reason,
            returned_mandate_count=len(affected),
            filters_applied=filters,
        ),
        lineage={
            "source_system": model.source_system or "lotus-core",
            "model_definition_source_record_id": model.source_record_id or "unknown",
            "mandate_binding_table": "portfolio_mandate_bindings",
            "contract_version": "rfc_041_cio_model_change_cohort_v1",
        },
        **_metadata(
            as_of_date=request.as_of_date,
            generated_at=generated_at,
            tenant_id=request.tenant_id,
            quality="ACCEPTED" if affected else "MISSING",
            evidence=[model, *mandates],
            snapshot_id=f"cio_model_change_cohort:{fingerprint}",
        ),
    )


def _universe_response(
    *,
    request: DpmPortfolioUniverseCandidateRequest,
    scope: DpmPortfolioUniverseScope,
    after_sort_key: tuple[str, str] | None,
    rows: list[DiscretionaryMandatePopulationMember],
    has_more: bool,
    next_page_token: str | None,
    generated_at: datetime,
) -> DpmPortfolioUniverseCandidateResponse:
    candidates = [_universe_candidate(row) for row in rows]
    filters = ["admitted_tenant_ownership", "as_of_date"]
    if scope.booking_center_code:
        filters.append("booking_center_code")
    if scope.model_portfolio_ids:
        filters.append("model_portfolio_ids")
    if not request.include_inactive_mandates:
        filters.append("active_discretionary_authority")
    state: Literal["READY", "DEGRADED", "INCOMPLETE"] = "READY"
    reason = "DPM_PORTFOLIO_UNIVERSE_READY"
    quality = "COMPLETE"
    if not candidates:
        state, reason, quality = "INCOMPLETE", "DPM_PORTFOLIO_UNIVERSE_EMPTY", "MISSING"
    elif has_more:
        state, reason, quality = "DEGRADED", "DPM_PORTFOLIO_UNIVERSE_PAGE_PARTIAL", "PARTIAL"
    elif any(_latest_evidence_timestamp(row) is None for row in rows):
        state = "DEGRADED"
        reason = "DPM_PORTFOLIO_UNIVERSE_EVIDENCE_TIME_UNAVAILABLE"
        quality = "PARTIAL"
    content_hash = (
        _ready_universe_content_hash(
            request=request,
            scope=scope,
            after_sort_key=after_sort_key,
            rows=rows,
        )
        if state == "READY"
        else None
    )
    return DpmPortfolioUniverseCandidateResponse(
        candidates=candidates,
        page=ReferencePageMetadata(
            page_size=request.page.page_size,
            sort_key="portfolio_id:asc,mandate_id:asc",
            returned_component_count=len(candidates),
            request_scope_fingerprint=scope.fingerprint,
            next_page_token=next_page_token,
        ),
        supportability=DpmPortfolioUniverseCandidateSupportability(
            state=state,
            reason=reason,
            returned_candidate_count=len(candidates),
            filters_applied=filters,
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
                "manager assignment, trading authorization, client notification authority, or "
                "external process ownership."
            ),
        ),
        lineage={
            "source_system": "lotus-core",
            "source_table": "portfolio_mandate_bindings",
            "source_filter": "mandate_type=discretionary",
            "contract_version": "rfc_037_dpm_portfolio_universe_candidate_v1",
        },
        **_metadata(
            as_of_date=request.as_of_date,
            generated_at=generated_at,
            tenant_id=scope.tenant_id,
            quality=quality,
            evidence=rows,
            snapshot_id=f"dpm_portfolio_universe:{scope.fingerprint}",
            content_hash=content_hash,
        ),
    )


def _ready_universe_content_hash(
    *,
    request: DpmPortfolioUniverseCandidateRequest,
    scope: DpmPortfolioUniverseScope,
    after_sort_key: tuple[str, str] | None,
    rows: list[DiscretionaryMandatePopulationMember],
) -> str:
    """Bind a complete candidate page to its normalized scope and source evidence."""

    return cast(
        str,
        stable_content_hash(
            {
                "product_name": "DpmPortfolioUniverseCandidate",
                "product_version": "v1",
                "tenant_id": scope.tenant_id,
                "as_of_date": request.as_of_date,
                "booking_center_code": scope.booking_center_code,
                "model_portfolio_ids": scope.model_portfolio_ids,
                "include_inactive_mandates": request.include_inactive_mandates,
                "page_size": request.page.page_size,
                "after_sort_key": after_sort_key,
                "source_rows": [asdict(row) for row in rows],
            }
        ),
    )


def _latest_evidence_timestamp(row: Any) -> datetime | None:
    return max(
        (value for value in (row.observed_at, row.updated_at, row.created_at) if value is not None),
        default=None,
    )


def _affected_mandate(row: DiscretionaryMandatePopulationMember) -> CioModelChangeAffectedMandate:
    return CioModelChangeAffectedMandate(
        portfolio_id=row.portfolio_id,
        mandate_id=row.mandate_id,
        client_id=row.client_id,
        booking_center_code=row.booking_center_code,
        jurisdiction_code=row.jurisdiction_code,
        discretionary_authority_status=row.discretionary_authority_status,
        model_portfolio_id=row.model_portfolio_id,
        policy_pack_id=row.policy_pack_id,
        risk_profile=row.risk_profile,
        effective_from=row.effective_from,
        effective_to=row.effective_to,
        binding_version=row.binding_version,
        source_record_id=row.source_record_id,
    )


def _universe_candidate(row: DiscretionaryMandatePopulationMember) -> DpmPortfolioUniverseCandidate:
    return DpmPortfolioUniverseCandidate(
        portfolio_id=row.portfolio_id,
        mandate_id=row.mandate_id,
        client_id=row.client_id,
        booking_center_code=row.booking_center_code,
        jurisdiction_code=row.jurisdiction_code,
        discretionary_authority_status=row.discretionary_authority_status,
        model_portfolio_id=row.model_portfolio_id,
        policy_pack_id=row.policy_pack_id,
        mandate_objective=row.mandate_objective,
        risk_profile=row.risk_profile,
        investment_horizon=row.investment_horizon,
        effective_from=row.effective_from,
        effective_to=row.effective_to,
        binding_version=row.binding_version,
        source_record_id=row.source_record_id,
    )


def _metadata(
    *,
    as_of_date: date,
    generated_at: datetime,
    tenant_id: str | None,
    quality: str,
    evidence: list[Any],
    snapshot_id: str,
    content_hash: str | None = None,
) -> dict[str, object]:
    timestamps = [timestamp for row in evidence if (timestamp := _latest_evidence_timestamp(row))]
    return cast(
        dict[str, object],
        source_data_product_runtime_metadata(
            as_of_date=as_of_date,
            generated_at=generated_at,
            tenant_id=tenant_id,
            data_quality_status=quality,
            latest_evidence_timestamp=max(timestamps, default=None),
            source_batch_fingerprint=None,
            snapshot_id=snapshot_id,
            content_hash=content_hash,
        ),
    )
