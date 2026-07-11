"""Application policy for approved DPM model portfolio targets."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from portfolio_common.market_reference_quality import (
    BLOCKING_QUALITY_STATUSES,
    PARTIAL_QUALITY_STATUSES,
    STALE_QUALITY_STATUSES,
    MarketReferenceCoverageSignal,
    classify_market_reference_coverage,
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


@dataclass(slots=True)
class ModelPortfolioTargetService:
    """Resolve an approved model and assess its effective instrument targets."""

    reader: DpmReferenceDataReader
    clock: Callable[[], datetime] = lambda: datetime.now(UTC)

    async def resolve(
        self,
        *,
        model_portfolio_id: str,
        request: ModelPortfolioTargetRequest,
    ) -> ModelPortfolioTargetResponse | None:
        definition = await self.reader.resolve_model_portfolio_definition(
            model_portfolio_id=model_portfolio_id,
            as_of_date=request.as_of_date,
        )
        if definition is None:
            return None
        evidence = await self.reader.list_model_portfolio_targets(
            model_portfolio_id=model_portfolio_id,
            model_portfolio_version=definition.model_portfolio_version,
            as_of_date=request.as_of_date,
            include_inactive_targets=request.include_inactive_targets,
        )
        return build_model_portfolio_target_response(
            definition=definition,
            request=request,
            evidence=evidence,
            generated_at=self.clock(),
        )


def build_model_portfolio_target_response(
    *,
    definition: ModelPortfolioDefinitionEvidence,
    request: ModelPortfolioTargetRequest,
    evidence: list[ModelPortfolioTargetEvidence],
    generated_at: datetime,
) -> ModelPortfolioTargetResponse:
    """Map source evidence and derive target-weight supportability."""

    targets = [_target_row(row) for row in evidence]
    total_weight = sum((target.target_weight for target in targets), Decimal("0"))
    supportability = _supportability(target_count=len(targets), total_weight=total_weight)
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
            data_quality_status=_data_quality_status(evidence, required_count=len(targets)),
            latest_evidence_timestamp=_latest_evidence_timestamp(definition, *evidence),
            content_payload=content_payload,
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
        quality_status=evidence.quality_status,
        source_record_id=evidence.source_record_id,
    )


def _supportability(*, target_count: int, total_weight: Decimal) -> ModelPortfolioSupportability:
    if target_count == 0:
        state, reason = "INCOMPLETE", "MODEL_TARGETS_EMPTY"
    elif total_weight != Decimal("1.0000000000"):
        state, reason = "DEGRADED", "MODEL_TARGET_WEIGHTS_NOT_ONE"
    else:
        state, reason = "READY", "MODEL_TARGETS_READY"
    return ModelPortfolioSupportability(
        state=state,
        reason=reason,
        target_count=target_count,
        total_target_weight=total_weight,
    )


def _data_quality_status(
    evidence: list[ModelPortfolioTargetEvidence], *, required_count: int
) -> str:
    if required_count <= 0:
        return "UNKNOWN"
    statuses = [row.quality_status.strip().upper() for row in evidence]
    return str(
        classify_market_reference_coverage(
            MarketReferenceCoverageSignal(
                required_count=required_count,
                observed_count=len(statuses),
                stale_count=sum(status in STALE_QUALITY_STATUSES for status in statuses),
                estimated_count=sum(status in PARTIAL_QUALITY_STATUSES for status in statuses),
                blocking_count=sum(status in BLOCKING_QUALITY_STATUSES for status in statuses),
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
