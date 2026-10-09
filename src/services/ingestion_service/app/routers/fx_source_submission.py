"""HTTP mapping after explicit existing principal verification; no application I/O."""

from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import HTTPException, Request
from portfolio_common.domain.tenant import TenantContext
from portfolio_common.enterprise_readiness import (
    load_default_enterprise_settings,
    verify_service_principal,
)
from portfolio_common.enterprise_tenant_admission import (
    TenantContextAdmissionError,
    resolve_enterprise_tenant_context,
)
from portfolio_common.fx_cut_authorization import sign_fx_cut_authorization
from portfolio_common.fx_source_admission import FxSourceAdmissionRejected
from portfolio_common.fx_source_configuration import (
    FxSourceConfigurationRejected,
    load_fx_source_policies,
)
from portfolio_common.fx_source_events import FxSourceCutReceivedEvent, FxSourceCutSubmission
from portfolio_common.logging_utils import normalize_traceparent


@dataclass(frozen=True)
class AdmittedFxCutSubmission:
    context: TenantContext
    event: FxSourceCutReceivedEvent


def admit_fx_source_submission(
    body: FxSourceCutSubmission, request: Request
) -> AdmittedFxCutSubmission:
    headers = dict(request.headers)
    principal = verify_service_principal(
        headers, load_default_enterprise_settings(service_name="ingestion_service")
    )
    if isinstance(principal, str):
        raise HTTPException(403, detail={"code": "FX_SOURCE_VERIFIED_PRINCIPAL_REQUIRED"})
    try:
        context = resolve_enterprise_tenant_context(
            tenant_id=headers.get("x-tenant-id"),
            actor_id=headers.get("x-actor-id"),
            role=headers.get("x-role"),
            service_identity=principal.service_identity,
            correlation_id=headers.get("x-correlation-id"),
            identity_verified=True,
        )
    except TenantContextAdmissionError:
        raise HTTPException(403, detail={"code": "FX_SOURCE_VERIFIED_PRINCIPAL_REQUIRED"}) from None
    try:
        policies = load_fx_source_policies()
    except FxSourceConfigurationRejected:
        raise HTTPException(503, detail={"code": "FX_SOURCE_CONFIGURATION_UNAVAILABLE"}) from None
    try:
        cut = body.to_cut(context.tenant_id_text)
    except ValueError:
        raise HTTPException(422, detail={"code": "FX_SOURCE_CUT_INVALID"}) from None
    try:
        authorization = sign_fx_cut_authorization(
            cut,
            context=context,
            principal=principal,
            admission_policy=policies.admission,
            relay_policy=policies.relay,
            now=datetime.now(UTC),
        )
    except FxSourceAdmissionRejected as exc:
        raise HTTPException(403, detail={"code": str(exc)}) from None
    event = FxSourceCutReceivedEvent(
        tenant_id=context.tenant_id_text,
        cut=body,
        authorization=authorization,
        correlation_id=context.correlation_id,
        traceparent=normalize_traceparent(headers.get("traceparent")),
    )
    try:
        event.bounded_payload()
    except ValueError:
        raise HTTPException(413, detail={"code": "FX_SOURCE_CUT_ENCODED_SIZE_EXCEEDED"}) from None
    return AdmittedFxCutSubmission(context, event)
