"""Application policy tests for DPM model portfolio targets."""

from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from portfolio_common.domain.tenant import (
    TenantAuthorityMismatchError,
    TenantContext,
    TenantId,
)

from src.services.query_control_plane_service.app.application.dpm_source_readiness import (
    model_portfolio_targets,
)
from src.services.query_control_plane_service.app.contracts.model_portfolio_targets import (
    ModelPortfolioTargetRequest,
)
from src.services.query_control_plane_service.app.domain.dpm_source_readiness import (
    ModelPortfolioDefinitionEvidence,
    ModelPortfolioTargetEvidence,
)
from src.services.query_control_plane_service.app.ports.dpm_source_readiness import (
    ModelPortfolioTargetReadResult,
)

GENERATED_AT = datetime(2026, 4, 10, 12, tzinfo=UTC)
EVIDENCE_AT = datetime(2026, 4, 10, 10, tzinfo=UTC)
TENANT_CONTEXT = TenantContext(tenant_id=TenantId("tenant-1"), actor_id="test-actor")


def _definition() -> ModelPortfolioDefinitionEvidence:
    return ModelPortfolioDefinitionEvidence(
        model_portfolio_id="MODEL_1",
        model_portfolio_version="2026.04",
        display_name="Balanced DPM",
        base_currency="SGD",
        risk_profile="balanced",
        mandate_type="discretionary",
        rebalance_frequency="monthly",
        approval_status="approved",
        approved_at=EVIDENCE_AT,
        effective_from=date(2026, 4, 1),
        effective_to=None,
        source_system="model_office",
        source_record_id="model:1",
        observed_at=EVIDENCE_AT,
        quality_status="accepted",
        created_at=EVIDENCE_AT,
        updated_at=EVIDENCE_AT,
    )


def _target(instrument_id: str, weight: str) -> ModelPortfolioTargetEvidence:
    return ModelPortfolioTargetEvidence(
        instrument_id=instrument_id,
        target_weight=Decimal(weight),
        min_weight=None,
        max_weight=None,
        target_status="active",
        effective_from=date(2026, 4, 1),
        effective_to=None,
        source_system="model_office",
        source_record_id=f"target:{instrument_id}",
        observed_at=EVIDENCE_AT,
        quality_status="accepted",
        created_at=EVIDENCE_AT,
        updated_at=EVIDENCE_AT,
    )


def _reader(*targets: ModelPortfolioTargetEvidence) -> AsyncMock:
    reader = AsyncMock()
    reader.resolve_model_portfolio_definition.return_value = _definition()
    reader.list_model_portfolio_targets.return_value = ModelPortfolioTargetReadResult(
        records=tuple(targets)
    )
    return reader


@pytest.mark.asyncio
async def test_model_targets_are_ready_with_current_deterministic_source_proof() -> None:
    reader = _reader(_target("BOND_1", "0.6000000000"), _target("EQ_1", "0.4000000000"))
    service = model_portfolio_targets.ModelPortfolioTargetService(
        reader=reader, clock=lambda: GENERATED_AT
    )
    request = ModelPortfolioTargetRequest(as_of_date=date(2026, 4, 10), tenant_id="tenant-1")

    first = await service.resolve(
        tenant_context=TENANT_CONTEXT, model_portfolio_id="MODEL_1", request=request
    )
    second = await service.resolve(
        tenant_context=TENANT_CONTEXT, model_portfolio_id="MODEL_1", request=request
    )

    assert first is not None and second is not None
    assert first.supportability.state == "READY"
    assert first.data_quality_status == "COMPLETE"
    assert first.source_evidence_current is True
    assert first.freshness_status == "CURRENT"
    assert first.content_hash.startswith("sha256:")
    assert first.tenant_id == "tenant-1"
    assert first.source_batch_fingerprint is None
    assert first.source_digest == first.content_hash
    assert first.content_hash == second.content_hash
    assert first.source_refs == ["lotus-core://source/DpmModelPortfolioTarget/MODEL_1/2026-04-10"]
    assert first.targets[0].source_system == "model_office"
    assert first.targets[0].observed_at == EVIDENCE_AT
    assert first.targets[0].quality_status == "accepted"


@pytest.mark.asyncio
async def test_model_target_hash_excludes_response_generation_time() -> None:
    reader = _reader(_target("EQ_1", "1.0000000000"))
    first = await model_portfolio_targets.ModelPortfolioTargetService(
        reader=reader,
        clock=lambda: GENERATED_AT,
    ).resolve(
        tenant_context=TENANT_CONTEXT,
        model_portfolio_id="MODEL_1",
        request=ModelPortfolioTargetRequest(as_of_date=date(2026, 4, 10)),
    )
    second = await model_portfolio_targets.ModelPortfolioTargetService(
        reader=reader,
        clock=lambda: datetime(2026, 4, 10, 13, tzinfo=UTC),
    ).resolve(
        tenant_context=TENANT_CONTEXT,
        model_portfolio_id="MODEL_1",
        request=ModelPortfolioTargetRequest(as_of_date=date(2026, 4, 10)),
    )

    assert first is not None and second is not None
    assert first.generated_at != second.generated_at
    assert first.content_hash == second.content_hash


@pytest.mark.asyncio
async def test_model_target_hash_includes_admitted_tenant_authority() -> None:
    reader = _reader(_target("EQ_1", "1.0000000000"))
    service = model_portfolio_targets.ModelPortfolioTargetService(
        reader=reader,
        clock=lambda: GENERATED_AT,
    )
    first = await service.resolve(
        tenant_context=TENANT_CONTEXT,
        model_portfolio_id="MODEL_1",
        request=ModelPortfolioTargetRequest(as_of_date=date(2026, 4, 10)),
    )
    second = await service.resolve(
        tenant_context=TenantContext(tenant_id=TenantId("tenant-other"), actor_id="test-actor"),
        model_portfolio_id="MODEL_1",
        request=ModelPortfolioTargetRequest(as_of_date=date(2026, 4, 10)),
    )

    assert first is not None and second is not None
    assert first.tenant_id != second.tenant_id
    assert first.content_hash != second.content_hash


@pytest.mark.asyncio
async def test_model_target_weight_mismatch_is_degraded() -> None:
    response = await model_portfolio_targets.ModelPortfolioTargetService(
        reader=_reader(_target("EQ_1", "0.9000000000")),
        clock=lambda: GENERATED_AT,
    ).resolve(
        tenant_context=TENANT_CONTEXT,
        model_portfolio_id="MODEL_1",
        request=ModelPortfolioTargetRequest(as_of_date=date(2026, 4, 10)),
    )

    assert response is not None
    assert response.supportability.state == "DEGRADED"
    assert response.supportability.reason == "MODEL_TARGET_WEIGHTS_NOT_ONE"


@pytest.mark.asyncio
async def test_unrecognized_model_target_quality_is_not_ready() -> None:
    target = replace(
        _target("EQ_1", "1.0000000000"),
        quality_status="vendor_verified",
    )
    response = await model_portfolio_targets.ModelPortfolioTargetService(
        reader=_reader(target),
        clock=lambda: GENERATED_AT,
    ).resolve(
        tenant_context=TENANT_CONTEXT,
        model_portfolio_id="MODEL_1",
        request=ModelPortfolioTargetRequest(as_of_date=date(2026, 4, 10)),
    )

    assert response is not None
    assert response.data_quality_status == "UNKNOWN"
    assert response.supportability.state == "DEGRADED"
    assert response.supportability.reason == "MODEL_TARGET_QUALITY_NOT_COMPLETE"


@pytest.mark.asyncio
@pytest.mark.parametrize("quality_status", ["vendor_verified", "BLOCKED", " "])
async def test_non_complete_model_definition_quality_is_not_ready(
    quality_status: str,
) -> None:
    reader = _reader(_target("EQ_1", "1.0000000000"))
    reader.resolve_model_portfolio_definition.return_value = replace(
        _definition(),
        quality_status=quality_status,
    )

    response = await model_portfolio_targets.ModelPortfolioTargetService(
        reader=reader,
        clock=lambda: GENERATED_AT,
    ).resolve(
        tenant_context=TENANT_CONTEXT,
        model_portfolio_id="MODEL_1",
        request=ModelPortfolioTargetRequest(as_of_date=date(2026, 4, 10)),
    )

    assert response is not None
    assert response.data_quality_status in {"UNKNOWN", "BLOCKED"}
    assert response.supportability.state == "DEGRADED"
    assert response.supportability.reason == "MODEL_TARGET_QUALITY_NOT_COMPLETE"


@pytest.mark.asyncio
async def test_missing_model_definition_returns_not_found_without_target_query() -> None:
    reader = AsyncMock()
    reader.resolve_model_portfolio_definition.return_value = None

    response = await model_portfolio_targets.ModelPortfolioTargetService(
        reader=reader,
        clock=lambda: GENERATED_AT,
    ).resolve(
        tenant_context=TENANT_CONTEXT,
        model_portfolio_id="MODEL_1",
        request=ModelPortfolioTargetRequest(as_of_date=date(2026, 4, 10)),
    )

    assert response is None
    reader.list_model_portfolio_targets.assert_not_awaited()


@pytest.mark.asyncio
async def test_source_target_overflow_is_unavailable_without_truncated_authority() -> None:
    reader = _reader()
    reader.list_model_portfolio_targets.return_value = ModelPortfolioTargetReadResult(
        records=(),
        limit_exceeded=True,
    )

    response = await model_portfolio_targets.ModelPortfolioTargetService(
        reader=reader,
        clock=lambda: GENERATED_AT,
    ).resolve(
        tenant_context=TENANT_CONTEXT,
        model_portfolio_id="MODEL_1",
        request=ModelPortfolioTargetRequest(as_of_date=date(2026, 4, 10)),
    )

    assert response is not None
    assert response.targets == []
    assert response.supportability.state == "UNAVAILABLE"
    assert response.supportability.reason == "MODEL_TARGET_LIMIT_EXCEEDED"
    assert response.supportability.target_count == 0
    assert response.source_evidence_current is False


@pytest.mark.asyncio
async def test_model_targets_reject_conflicting_tenant_before_source_reads() -> None:
    reader = _reader(_target("EQ_1", "1.0000000000"))
    service = model_portfolio_targets.ModelPortfolioTargetService(
        reader=reader,
        clock=lambda: GENERATED_AT,
    )

    with pytest.raises(TenantAuthorityMismatchError):
        await service.resolve(
            tenant_context=TENANT_CONTEXT,
            model_portfolio_id="MODEL_1",
            request=ModelPortfolioTargetRequest(
                as_of_date=date(2026, 4, 10), tenant_id="tenant-other"
            ),
        )

    reader.resolve_model_portfolio_definition.assert_not_awaited()
