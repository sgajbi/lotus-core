"""Synthetic software-control fixtures; no deployed provider or enrollment authority."""

import json
from dataclasses import asdict, replace
from datetime import UTC, date, datetime
from decimal import Decimal

from portfolio_common.domain.market_data.fx_source import (
    FxSourceCut,
    FxSourceRevision,
    FxSourceScope,
    fx_cut_membership_hash,
)
from portfolio_common.fx_source_admission import FX_SOURCE_SUBMIT_CAPABILITY
from portfolio_common.fx_source_events import FxSourceCutSubmission, FxSourceMember

OBSERVED = datetime(2026, 10, 8, 16, tzinfo=UTC)
SCOPE = FxSourceScope("SYNTHETIC_TENANT", "SYNTHETIC_PROVIDER", "SYNTHETIC_FEED")
PRINCIPAL = "SYNTHETIC_INGEST"
CALENDAR_VERSION = "SYNTHETIC_CALENDAR_V1"


def synthetic_revision(**changes) -> FxSourceRevision:
    member = FxSourceRevision(
        SCOPE,
        "SYNTHETIC_USD_SGD_CLOSE",
        "1",
        "USD",
        "SGD",
        date(2026, 10, 8),
        Decimal("1.35"),
        OBSERVED,
        "CLOSE",
        CALENDAR_VERSION,
    )
    return replace(member, **changes)


def synthetic_cut(*members: FxSourceRevision, version="1", reference="SYNTHETIC_CLOSE"):
    members = members or (synthetic_revision(),)
    return FxSourceCut(
        members[0].scope,
        reference,
        version,
        max(member.source_observed_at for member in members),
        members,
        len(members),
        fx_cut_membership_hash(members),
    )


def submission(cut: FxSourceCut) -> FxSourceCutSubmission:
    return FxSourceCutSubmission(
        contract_version="fx.source-cut.v1",
        provider_id=cut.scope.provider_id,
        source_id=cut.scope.source_id,
        source_cut_reference=cut.source_cut_reference,
        source_cut_revision=cut.source_cut_revision,
        source_observed_cutoff=cut.source_observed_cutoff,
        declared_member_count=cut.declared_member_count,
        declared_membership_hash=cut.declared_membership_hash,
        members=tuple(
            FxSourceMember.model_validate(
                {key: value for key, value in asdict(member).items() if key != "scope"}
            )
            for member in cut.revisions
        ),
    )


def configure_synthetic_fx_source(monkeypatch, *, active=True, scope=SCOPE):
    monkeypatch.setenv(
        "LOTUS_FX_SOURCE_ENROLLMENTS",
        json.dumps(
            [
                {
                    "version": "SYNTHETIC_ENROLLMENT_V1",
                    **scope.content(),
                    "principal": PRINCIPAL,
                    "allowed_pairs": [["USD", "SGD"]],
                    "calendar_version": CALENDAR_VERSION,
                    "valid_from": "2026-01-01T00:00:00Z",
                    "valid_until": "2027-01-01T00:00:00Z",
                    "active": active,
                }
            ]
        ),
    )
    monkeypatch.setenv(
        "LOTUS_FX_SOURCE_CALENDARS",
        json.dumps(
            [
                {
                    "version": CALENDAR_VERSION,
                    "fixing_kind": "CLOSE",
                    "timezone": "UTC",
                    "fixing_time": "16:00:00",
                    "publication_delay_seconds": 60,
                    "business_weekdays": [0, 1, 2, 3, 4],
                    "closed_dates": [],
                }
            ]
        ),
    )
    monkeypatch.setenv(
        "LOTUS_FX_SOURCE_RELAY_KEYS",
        json.dumps(
            [
                {
                    "issuer": "SYNTHETIC_CORE",
                    "key_id": "SYNTHETIC_RELAY_V1",
                    "secret_env": "LOTUS_FX_SOURCE_RELAY_KEY_SYNTHETIC",
                    "signing_enabled": True,
                }
            ]
        ),
    )
    monkeypatch.setenv(
        "LOTUS_FX_SOURCE_RELAY_KEY_SYNTHETIC", "synthetic-relay-proof-secret-32-bytes"
    )
    monkeypatch.setenv("ENTERPRISE_ENFORCE_AUTHZ", "false")
    monkeypatch.setenv("ENTERPRISE_PRIMARY_KEY_ID", "synthetic-http-key")
    monkeypatch.setenv(
        "ENTERPRISE_AUTH_CONTEXT_HMAC_SECRET", "synthetic-http-proof-secret-32-bytes"
    )


def signed_headers(*, capability=FX_SOURCE_SUBMIT_CAPABILITY, tenant=SCOPE.tenant_id):
    from time import time

    from portfolio_common.enterprise_readiness import (
        _enterprise_auth_context_signature,
        _normalize_headers,
    )

    headers = {
        "X-Tenant-Id": tenant,
        "X-Actor-Id": "SYNTHETIC_ACTOR",
        "X-Role": "operations",
        "X-Correlation-Id": "synthetic-fx-proof-correlation",
        "X-Service-Identity": PRINCIPAL,
        "X-Capabilities": capability,
        "X-Enterprise-Auth-Key-Id": "synthetic-http-key",
        "X-Enterprise-Auth-Timestamp": str(int(time())),
        "X-Idempotency-Key": "synthetic-fx-cut-command",
    }
    headers["X-Enterprise-Auth-Signature"] = _enterprise_auth_context_signature(
        _normalize_headers(headers), "synthetic-http-proof-secret-32-bytes"
    )
    return headers


def signed_event(cut=None, *, accepted_at=None):
    from portfolio_common.domain.tenant import TenantContext, TenantId
    from portfolio_common.enterprise_readiness import VerifiedServicePrincipal
    from portfolio_common.fx_cut_authorization import sign_fx_cut_authorization
    from portfolio_common.fx_source_configuration import load_fx_source_policies
    from portfolio_common.fx_source_events import FxSourceCutReceivedEvent

    cut = cut or synthetic_cut()
    policies = load_fx_source_policies()
    token = sign_fx_cut_authorization(
        cut,
        context=TenantContext(
            TenantId(cut.scope.tenant_id), service_identity=PRINCIPAL, identity_verified=True
        ),
        principal=VerifiedServicePrincipal(PRINCIPAL, {FX_SOURCE_SUBMIT_CAPABILITY}),
        admission_policy=policies.admission,
        relay_policy=policies.relay,
        now=accepted_at or datetime.now(UTC),
    )
    return FxSourceCutReceivedEvent(
        tenant_id=cut.scope.tenant_id,
        cut=submission(cut),
        authorization=token,
        correlation_id="synthetic-fx-proof-correlation",
    )
