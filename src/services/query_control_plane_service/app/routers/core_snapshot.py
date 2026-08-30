"""HTTP-boundary orchestration for the governed Core snapshot contract."""

from __future__ import annotations

from typing import cast

from fastapi import status
from fastapi.encoders import jsonable_encoder
from portfolio_common.domain.tenant import (
    TenantAuthorityMismatchError,
    TenantContext,
    bind_tenant_authority,
)

from ..application.core_snapshot.governance import SnapshotGovernanceContext
from ..application.core_snapshot.service import (
    CoreSnapshotBadRequestError,
    CoreSnapshotConflictError,
    CoreSnapshotNotFoundError,
    CoreSnapshotService,
    CoreSnapshotUnavailableSectionError,
)
from ..application.integration_policy import IntegrationPolicyService
from ..contracts.core_snapshot import (
    CoreSnapshotRequest,
    CoreSnapshotResponse,
    CoreSnapshotSection,
)
from .response_helpers import raise_problem

HTTP_422_UNPROCESSABLE_CONTENT = 422


def bind_core_snapshot_tenant_authority(
    *,
    request: CoreSnapshotRequest,
    tenant_context: TenantContext,
) -> CoreSnapshotRequest:
    """Return the request with canonical admitted tenant authority or fail closed."""

    try:
        admitted_tenant_id = bind_tenant_authority(request.tenant_id, tenant_context)
    except (TenantAuthorityMismatchError, ValueError):
        raise_problem(
            status_code=status.HTTP_403_FORBIDDEN,
            title="Core snapshot tenant scope forbidden",
            detail="Requested tenant does not match admitted tenant authority.",
            error_code="QCP_CORE_SNAPSHOT_TENANT_FORBIDDEN",
            metadata={"source_product": "PortfolioStateSnapshot"},
        )
    return request.model_copy(update={"tenant_id": admitted_tenant_id})


def governed_core_snapshot_request(
    *,
    request: CoreSnapshotRequest,
    integration_service: IntegrationPolicyService,
) -> tuple[CoreSnapshotRequest, SnapshotGovernanceContext]:
    requested_sections = list(request.sections)
    policy = integration_service.get_effective_policy(
        consumer_system=request.consumer_system,
        tenant_id=request.tenant_id,
        include_sections=_policy_section_codes(requested_sections),
    )
    applied_sections, dropped_sections, warnings = _policy_applied_snapshot_sections(
        requested_sections=requested_sections,
        policy=policy,
    )
    _assert_core_snapshot_sections_allowed(
        applied_sections=applied_sections,
        dropped_sections=dropped_sections,
        strict_mode=policy.policy_provenance.strict_mode,
    )
    return (
        request.model_copy(update={"sections": applied_sections}),
        SnapshotGovernanceContext(
            consumer_system=policy.consumer_system,
            tenant_id=policy.tenant_id,
            requested_sections=requested_sections,
            applied_sections=applied_sections,
            dropped_sections=dropped_sections,
            policy_version=policy.policy_provenance.policy_version,
            policy_source=policy.policy_provenance.policy_source,
            matched_rule_id=policy.policy_provenance.matched_rule_id,
            strict_mode=policy.policy_provenance.strict_mode,
            warnings=warnings,
        ),
    )


def lotus_idea_core_snapshot_payload(response: CoreSnapshotResponse | dict) -> dict:
    payload = cast(
        dict,
        jsonable_encoder(
            response.model_dump(mode="json")
            if isinstance(response, CoreSnapshotResponse)
            else response
        ),
    )
    payload["freshness_metadata"] = payload.get("freshness")
    payload["freshness"] = payload.get("freshness_status", "UNAVAILABLE")
    return payload


async def core_snapshot_response_or_http_error(
    *,
    service: CoreSnapshotService,
    portfolio_id: str,
    request: CoreSnapshotRequest,
    governance: SnapshotGovernanceContext,
) -> CoreSnapshotResponse:
    try:
        response = await service.get_core_snapshot(
            portfolio_id=portfolio_id,
            request=request,
            governance=governance,
        )
        return cast(CoreSnapshotResponse, response)
    except CoreSnapshotBadRequestError as exc:
        raise_problem(
            status_code=status.HTTP_400_BAD_REQUEST,
            title="Core snapshot request is invalid",
            detail="Core snapshot request is invalid.",
            error_code="QCP_CORE_SNAPSHOT_INVALID_REQUEST",
            metadata={"source_product": "PortfolioStateSnapshot", "reason": exc.__class__.__name__},
        )
    except CoreSnapshotNotFoundError as exc:
        raise_problem(
            status_code=status.HTTP_404_NOT_FOUND,
            title="Core snapshot not found",
            detail="Portfolio or simulation session was not found.",
            error_code="QCP_CORE_SNAPSHOT_NOT_FOUND",
            metadata={"source_product": "PortfolioStateSnapshot", "reason": exc.__class__.__name__},
        )
    except CoreSnapshotConflictError as exc:
        raise_problem(
            status_code=status.HTTP_409_CONFLICT,
            title="Core snapshot conflict",
            detail=(
                "Core snapshot request conflicts with the current portfolio or simulation state."
            ),
            error_code="QCP_CORE_SNAPSHOT_CONFLICT",
            metadata={"source_product": "PortfolioStateSnapshot", "reason": exc.__class__.__name__},
        )
    except CoreSnapshotUnavailableSectionError as exc:
        raise_problem(
            status_code=HTTP_422_UNPROCESSABLE_CONTENT,
            title="Core snapshot section unavailable",
            detail=(
                "Requested core snapshot section cannot be fulfilled from available source data."
            ),
            error_code="QCP_CORE_SNAPSHOT_UNAVAILABLE_SECTION",
            metadata={"source_product": "PortfolioStateSnapshot", "reason": exc.__class__.__name__},
        )
    raise AssertionError("problem response helper returned unexpectedly")


def _policy_section_codes(sections: list[CoreSnapshotSection]) -> list[str]:
    return [section.value.upper() for section in sections]


def _policy_applied_snapshot_sections(
    *,
    requested_sections: list[CoreSnapshotSection],
    policy,
) -> tuple[list[CoreSnapshotSection], list[CoreSnapshotSection], list[str]]:
    if "NO_ALLOWED_SECTION_RESTRICTION" in policy.warnings:
        return requested_sections, [], list(policy.warnings)

    allowed_policy_sections = set(policy.allowed_sections)
    applied_sections = [
        section
        for section in requested_sections
        if _snapshot_section_allowed_by_policy(section, allowed_policy_sections)
    ]
    dropped_sections = [
        section
        for section in requested_sections
        if not _snapshot_section_allowed_by_policy(section, allowed_policy_sections)
    ]
    warnings = list(policy.warnings)
    if dropped_sections and not policy.policy_provenance.strict_mode:
        warnings.append("SECTIONS_DROPPED_NON_STRICT_MODE")
    return applied_sections, dropped_sections, warnings


def _snapshot_section_allowed_by_policy(
    section: CoreSnapshotSection, allowed_policy_sections: set[str]
) -> bool:
    if section.value.upper() in allowed_policy_sections:
        return True
    return (
        section == CoreSnapshotSection.PORTFOLIO_STATE
        and CoreSnapshotSection.POSITIONS_BASELINE.value.upper() in allowed_policy_sections
    )


def _assert_core_snapshot_sections_allowed(
    *,
    applied_sections: list[CoreSnapshotSection],
    dropped_sections: list[CoreSnapshotSection],
    strict_mode: bool,
) -> None:
    if dropped_sections and strict_mode:
        raise_problem(
            status_code=status.HTTP_403_FORBIDDEN,
            title="Core snapshot sections blocked by policy",
            detail="Requested snapshot sections are blocked by strict integration policy.",
            error_code="QCP_CORE_SNAPSHOT_POLICY_BLOCKED",
            metadata={
                "source_product": "PortfolioStateSnapshot",
                "blocked_sections": [section.value for section in dropped_sections],
            },
        )

    if not applied_sections:
        raise_problem(
            status_code=status.HTTP_400_BAD_REQUEST,
            title="Core snapshot request is invalid",
            detail="No core snapshot sections remain after policy evaluation.",
            error_code="QCP_CORE_SNAPSHOT_INVALID_REQUEST",
            metadata={"source_product": "PortfolioStateSnapshot"},
        )
