"""Purpose-bound relay of verified FX admission to the existing persistence owner."""

import hashlib
import hmac
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from .domain.market_data.fx_source import FxSourceCut
from .domain.tenant import TenantContext, TenantId
from .enterprise_readiness import VerifiedServicePrincipal
from .fx_source_admission import (
    FX_SOURCE_SUBMIT_CAPABILITY,
    FxSourceAdmission,
    FxSourceAdmissionPolicy,
    FxSourceAdmissionRejected,
)
from .fx_source_events import FxCutAuthorizationClaims, SignedFxCutAuthorization


@dataclass(frozen=True)
class FxCutRelayKey:
    issuer: str
    key_id: str
    secret: str = field(repr=False)
    signing_enabled: bool = False

    def __post_init__(self) -> None:
        if not self.issuer or not self.key_id or len(self.secret.encode("utf-8")) < 32:
            raise ValueError("FX_SOURCE_RELAY_CONFIGURATION_INVALID")


@dataclass(frozen=True)
class FxCutRelayPolicy:
    keys: tuple[FxCutRelayKey, ...] = ()
    ttl_seconds: int = 300

    def __post_init__(self) -> None:
        if (
            type(self.keys) is not tuple
            or type(self.ttl_seconds) is not int
            or not 1 <= self.ttl_seconds <= 300
            or len({(key.issuer, key.key_id) for key in self.keys}) != len(self.keys)
            or sum(key.signing_enabled for key in self.keys) > 1
        ):
            raise ValueError("FX_SOURCE_RELAY_CONFIGURATION_INVALID")


@dataclass(frozen=True)
class CommittedFxCutVerification:
    """Only the owning retained row may supply this exact replay reference."""

    cut_id: str
    content_hash: str
    attestation_sha256: str


@dataclass(frozen=True)
class VerifiedFxCutAuthorization:
    admission: FxSourceAdmission
    attestation_sha256: str
    durable_replay: bool


def _claims_bytes(claims: FxCutAuthorizationClaims) -> bytes:
    return json.dumps(
        claims.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _attestation_hash(token: SignedFxCutAuthorization) -> str:
    return hashlib.sha256(_claims_bytes(token.claims) + token.signature.encode("ascii")).hexdigest()


def sign_fx_cut_authorization(
    cut: FxSourceCut,
    *,
    context: TenantContext,
    principal: VerifiedServicePrincipal | None,
    admission_policy: FxSourceAdmissionPolicy,
    relay_policy: FxCutRelayPolicy,
    now: datetime,
) -> SignedFxCutAuthorization:
    admitted = admission_policy.admit(cut, context=context, principal=principal, now=now)
    signer = next((key for key in relay_policy.keys if key.signing_enabled), None)
    if signer is None:
        raise FxSourceAdmissionRejected("FX_SOURCE_RELAY_SIGNER_REQUIRED")
    claims = FxCutAuthorizationClaims(
        issuer=signer.issuer,
        key_id=signer.key_id,
        principal=admitted.principal,
        tenant_id=cut.scope.tenant_id,
        provider_id=cut.scope.provider_id,
        source_id=cut.scope.source_id,
        enrollment_version=admitted.enrollment_version,
        calendar_version=admitted.calendar_version,
        cut_id=cut.cut_id,
        content_hash=cut.content_hash,
        accepted_at=now,
        expires_at=now + timedelta(seconds=relay_policy.ttl_seconds),
    )
    signature = hmac.new(
        signer.secret.encode("utf-8"), _claims_bytes(claims), hashlib.sha256
    ).hexdigest()
    return SignedFxCutAuthorization(claims=claims, signature=signature)


def authenticate_fx_cut_authorization(
    token: SignedFxCutAuthorization,
    cut: FxSourceCut,
    *,
    relay_policy: FxCutRelayPolicy,
) -> tuple[SignedFxCutAuthorization, str]:
    """Authenticity/content only, not fresh admission or durable replay permission."""
    # Frozen model type is not validation: reject unsafe model_construct/model_copy input.
    token = SignedFxCutAuthorization.model_validate(token.model_dump(mode="python"))
    claims = token.claims
    key = next(
        (
            key
            for key in relay_policy.keys
            if (key.issuer, key.key_id) == (claims.issuer, claims.key_id)
        ),
        None,
    )
    if key is None:
        raise FxSourceAdmissionRejected("FX_SOURCE_RELAY_KEY_REQUIRED")
    expected = hmac.new(
        key.secret.encode("utf-8"), _claims_bytes(claims), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(expected, token.signature):
        raise FxSourceAdmissionRejected("FX_SOURCE_RELAY_SIGNATURE_INVALID")
    if (
        claims.cut_id != cut.cut_id
        or claims.content_hash != cut.content_hash
        or (claims.tenant_id, claims.provider_id, claims.source_id)
        != (cut.scope.tenant_id, cut.scope.provider_id, cut.scope.source_id)
    ):
        raise FxSourceAdmissionRejected("FX_SOURCE_RELAY_CONTENT_MISMATCH")
    digest = _attestation_hash(token)
    return token, digest


def verify_fx_cut_authorization(
    token: SignedFxCutAuthorization,
    cut: FxSourceCut,
    *,
    admission_policy: FxSourceAdmissionPolicy,
    relay_policy: FxCutRelayPolicy,
    now: datetime,
    committed: CommittedFxCutVerification | None = None,
) -> VerifiedFxCutAuthorization:
    token, digest = authenticate_fx_cut_authorization(token, cut, relay_policy=relay_policy)
    claims = token.claims
    admitted = FxSourceAdmission(
        cut,
        claims.accepted_at,
        claims.principal,
        claims.enrollment_version,
        claims.calendar_version,
    )
    if committed is not None:
        if committed != CommittedFxCutVerification(cut.cut_id, cut.content_hash, digest):
            raise FxSourceAdmissionRejected("FX_SOURCE_RETAINED_REPLAY_MISMATCH")
        return VerifiedFxCutAuthorization(admitted, digest, True)
    ttl = (claims.expires_at - claims.accepted_at).total_seconds()
    if (
        now.utcoffset() is None
        or claims.accepted_at > now
        or not 0 < ttl <= relay_policy.ttl_seconds
        or now >= claims.expires_at
    ):
        raise FxSourceAdmissionRejected("FX_SOURCE_RELAY_EXPIRED_OR_FUTURE")
    # Recheck current server enrollment for fresh work, not only historical signer authority.
    current = admission_policy.admit(
        cut,
        context=TenantContext(
            tenant_id=TenantId(claims.tenant_id),
            service_identity=claims.principal,
            identity_verified=True,
        ),
        # Authority is the authenticated purpose-bound server signature above,
        # never a consumer header claiming to be a verified HTTP principal.
        principal=VerifiedServicePrincipal(claims.principal, {FX_SOURCE_SUBMIT_CAPABILITY}),
        now=now,
    )
    if (current.enrollment_version, current.calendar_version) != (
        claims.enrollment_version,
        claims.calendar_version,
    ):
        raise FxSourceAdmissionRejected("FX_SOURCE_RELAY_ENROLLMENT_CHANGED")
    return VerifiedFxCutAuthorization(admitted, digest, False)
