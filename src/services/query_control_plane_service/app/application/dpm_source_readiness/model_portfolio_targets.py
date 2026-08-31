"""Application policy for approved DPM model portfolio targets."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from portfolio_common.domain.tenant import TenantContext, bind_tenant_authority
from portfolio_common.market_reference_quality import (
    MarketReferenceCoverageSignal,
    classify_market_reference_coverage,
    count_market_reference_quality_statuses,
)

from ...contracts.model_portfolio_targets import (
    ModelPortfolioSupportability,
    ModelPortfolioTargetRequest,
    ModelPortfolioTargetResponse,
    ModelPortfolioTargetRow,
)
from ...domain.dpm_source_readiness import (
    ModelPortfolioDefinitionEvidence,
    ModelPortfolioTargetEvidence,
)
from ...ports.dpm_source_readiness import DpmReferenceDataReader
from .metadata import dpm_source_runtime_metadata

MODEL_TARGET_LIMIT_EXCEEDED = "MODEL_TARGET_LIMIT_EXCEEDED"


@dataclass(slots=True)
class ModelPortfolioTargetService:
    """Resolve an approved model and assess its effective instrument targets."""

    reader: DpmReferenceDataReader
    clock: Callable[[], datetime] = lambda: datetime.now(UTC)

    async def resolve(
        self,
        *,
        tenant_context: TenantContext,
        model_portfolio_id: str,
        request: ModelPortfolioTargetRequest,
    ) -> ModelPortfolioTargetResponse | None:
        request = request.model_copy(
            update={"tenant_id": bind_tenant_authority(request.tenant_id, tenant_context)}
        )
        definition = await self.reader.resolve_model_portfolio_definition(
            model_portfolio_id=model_portfolio_id,
            as_of_date=request.as_of_date,
        )
        if definition is None:
            return None
        read_result = await self.reader.list_model_portfolio_targets(
            model_portfolio_id=model_portfolio_id,
            model_portfolio_version=definition.model_portfolio_version,
            as_of_date=request.as_of_date,
            include_inactive_targets=request.include_inactive_targets,
        )
        return build_model_portfolio_target_response(
            definition=definition,
            request=request,
            evidence=list(read_result.records),
            source_limit_exceeded=read_result.limit_exceeded,
            generated_at=self.clock(),
        )


def build_model_portfolio_target_response(
    *,
    definition: ModelPortfolioDefinitionEvidence,
    request: ModelPortfolioTargetRequest,
    evidence: list[ModelPortfolioTargetEvidence],
    source_limit_exceeded: bool = False,
    generated_at: datetime,
) -> ModelPortfolioTargetResponse:
    """Map source evidence and derive target-weight supportability."""

    targets = [_target_row(row) for row in evidence]
    total_weight = sum((target.target_weight for target in targets), Decimal("0"))
    data_quality_status = _data_quality_status(
        definition=definition,
        evidence=evidence,
    )
    supportability = _supportability(
        target_count=len(targets),
        total_weight=total_weight,
        data_quality_status=data_quality_status,
        source_limit_exceeded=source_limit_exceeded,
    )
    lineage = {
        "source_system": definition.source_system or "unknown",
        "source_record_id": definition.source_record_id or "unknown",
        "contract_version": "rfc_087_v1",
    }
    content_payload = {
        "model_portfolio_id": definition.model_portfolio_id,
        "model_portfolio_version": definition.model_portfolio_version,
        "display_name": definition.display_name,
        "base_currency": definition.base_currency,
        "risk_profile": definition.risk_profile,
        "mandate_type": definition.mandate_type,
        "rebalance_frequency": definition.rebalance_frequency,
        "approval_status": definition.approval_status,
        "approved_at": definition.approved_at,
        "effective_from": definition.effective_from,
        "effective_to": definition.effective_to,
        "targets": [target.model_dump(mode="json") for target in targets],
        "supportability": supportability.model_dump(mode="json"),
        "lineage": lineage,
    }
    return ModelPortfolioTargetResponse(
        **content_payload,
        **dpm_source_runtime_metadata(
            product_name="DpmModelPortfolioTarget",
            source_key=definition.model_portfolio_id,
            as_of_date=request.as_of_date,
            generated_at=generated_at,
            tenant_id=request.tenant_id,
            data_quality_status=data_quality_status,
            latest_evidence_timestamp=_latest_evidence_timestamp(definition, *evidence),
            content_payload={"tenant_id": request.tenant_id, **content_payload},
            lineage=lineage,
        ),
    )


def _target_row(evidence: ModelPortfolioTargetEvidence) -> ModelPortfolioTargetRow:
    return ModelPortfolioTargetRow(
        instrument_id=evidence.instrument_id,
        target_weight=evidence.target_weight,
        min_weight=evidence.min_weight,
        max_weight=evidence.max_weight,
        target_status=evidence.target_status,
        source_system=evidence.source_system,
        quality_status=evidence.quality_status,
        source_record_id=evidence.source_record_id,
        observed_at=evidence.observed_at,
    )


def _supportability(
    *,
    target_count: int,
    total_weight: Decimal,
    data_quality_status: str,
    source_limit_exceeded: bool = False,
) -> ModelPortfolioSupportability:
    if source_limit_exceeded:
        state, reason = "UNAVAILABLE", MODEL_TARGET_LIMIT_EXCEEDED
    elif target_count == 0:
        state, reason = "INCOMPLETE", "MODEL_TARGETS_EMPTY"
    elif total_weight != Decimal("1.0000000000"):
        state, reason = "DEGRADED", "MODEL_TARGET_WEIGHTS_NOT_ONE"
    elif data_quality_status != "COMPLETE":
        state, reason = "DEGRADED", "MODEL_TARGET_QUALITY_NOT_COMPLETE"
    else:
        state, reason = "READY", "MODEL_TARGETS_READY"
    return ModelPortfolioSupportability(
        state=state,
        reason=reason,
        target_count=target_count,
        total_target_weight=total_weight,
    )


def _data_quality_status(
    *,
    definition: ModelPortfolioDefinitionEvidence,
    evidence: list[ModelPortfolioTargetEvidence],
) -> str:
    if not evidence:
        return "UNKNOWN"
    quality_counts = count_market_reference_quality_statuses(
        [definition.quality_status, *(row.quality_status for row in evidence)]
    )
    return str(
        classify_market_reference_coverage(
            MarketReferenceCoverageSignal(
                required_count=len(evidence) + 1,
                observed_count=len(evidence) + 1,
                stale_count=quality_counts.stale_count,
                estimated_count=quality_counts.estimated_count,
                blocking_count=quality_counts.blocking_count,
                unknown_count=quality_counts.unknown_count,
            )
        )
    )


def _latest_evidence_timestamp(
    definition: ModelPortfolioDefinitionEvidence,
    *targets: ModelPortfolioTargetEvidence,
) -> datetime | None:
    timestamps = [
        timestamp
        for row in (definition, *targets)
        for timestamp in (row.observed_at, row.updated_at, row.created_at)
        if timestamp is not None
    ]
    return max(timestamps) if timestamps else None
