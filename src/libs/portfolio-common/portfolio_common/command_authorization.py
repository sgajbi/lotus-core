"""Purpose-bound source-command delegation; absent enrollment always denies.

HTTP principal verification remains owned by enterprise_readiness. This module
binds that verified authority to one immutable command for the persistence owner;
it does not accept bearer credentials or create grants from caller headers.
"""

import hashlib
import hmac
import json
from dataclasses import dataclass, field
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

from portfolio_common.domain.tenant import TenantContext
from portfolio_common.enterprise_readiness import VerifiedServicePrincipal
from portfolio_common.runtime_settings import env_str

SOURCE_CORRECTION_CAPABILITY: Final = "ingestion.transactions.source_evidence.correct"
SOURCE_CORRECTION_PURPOSE: Final = "lotus-core.transaction-source-evidence-confirmation"


class CommandAuthorizationRejected(ValueError):
    """Safe refusal reason, never credentials or command payload values."""


class CommandAuthorizationClaims(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    contract_version: Literal["lotus.command-authorization.v1"] = "lotus.command-authorization.v1"
    purpose: Literal["lotus-core.transaction-source-evidence-confirmation"] = (
        SOURCE_CORRECTION_PURPOSE
    )
    audience: Literal["lotus-core.persistence-service"] = "lotus-core.persistence-service"
    capability: Literal["ingestion.transactions.source_evidence.correct"] = (
        SOURCE_CORRECTION_CAPABILITY
    )
    issuer: str = Field(min_length=1, max_length=128)
    key_id: str = Field(min_length=1, max_length=128)
    principal: str = Field(min_length=1, max_length=128)
    actor_id: str = Field(min_length=1, max_length=128)
    tenant_id: str = Field(min_length=1, max_length=128)
    command_id: str = Field(min_length=1, max_length=128)
    operation_id: str = Field(min_length=1, max_length=128)
    target_transaction_id: str = Field(min_length=1, max_length=256)
    root_raw_id: str = Field(min_length=1, max_length=128)
    root_raw_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_head_id: str = Field(min_length=1, max_length=128)
    expected_head_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    canonical_request_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    issued_at: int = Field(ge=0)
    expires_at: int = Field(ge=0)
    nonce: str = Field(min_length=1, max_length=128)
    correlation_id: str = Field(min_length=1, max_length=128)
    trace_id: str = Field(min_length=1, max_length=128)


class SignedCommandAuthorization(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    claims: CommandAuthorizationClaims
    signature: str = Field(pattern=r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class CommandProducerEnrollment:
    issuer: str
    key_id: str
    principal: str
    secret: str = field(repr=False)
    capability: str = SOURCE_CORRECTION_CAPABILITY
    signing_enabled: bool = False


@dataclass(frozen=True, slots=True)
class CommandAuthorizationPolicy:
    enrollments: tuple[CommandProducerEnrollment, ...] = ()
    max_ttl_seconds: int = 300
    clock_skew_seconds: int = 30

    def __post_init__(self) -> None:
        if (
            type(self.max_ttl_seconds) is not int
            or type(self.clock_skew_seconds) is not int
            or self.max_ttl_seconds <= 0
            or self.clock_skew_seconds < 0
        ):
            raise ValueError("Invalid command authorization time policy")
        identities = [(item.issuer, item.key_id, item.principal) for item in self.enrollments]
        if len(identities) != len(set(identities)):
            raise ValueError("Duplicate command producer enrollment")


class _ProducerEnrollmentSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    issuer: str = Field(pattern=r"^\S{1,128}$")
    key_id: str = Field(pattern=r"^\S{1,128}$")
    principal: str = Field(pattern=r"^\S{1,128}$")
    secret_env: str = Field(pattern=r"^LOTUS_SOURCE_CORRECTION_KEY_[A-Z0-9_]{1,64}$")
    signing_enabled: bool = False
    capability: Literal["ingestion.transactions.source_evidence.correct"] = (
        SOURCE_CORRECTION_CAPABILITY
    )


def load_command_authorization_policy() -> CommandAuthorizationPolicy:
    """Explicit purpose enrollment/key selection; never dev or static-token fallback.

    Secrets stay in the owning deployment's secret environment, not registry
    JSON or error output. Retained previous keys must explicitly disable signing.
    Empty configuration is a valid deny-all policy, not production enrollment.
    """
    raw = env_str("LOTUS_SOURCE_CORRECTION_PRODUCER_ENROLLMENTS", "[]")
    try:
        if len(raw) > 32768:
            raise ValueError("Oversized registry")
        settings = TypeAdapter(list[_ProducerEnrollmentSettings]).validate_python(
            json.loads(raw), strict=True
        )
        if len(settings) > 16:
            raise ValueError("Too many producers")
        enrolled = []
        signers = set()
        for item in settings:
            secret = env_str(item.secret_env, "")
            if len(secret.encode("utf-8")) < 32:
                raise ValueError("Missing or weak configured key")
            if item.signing_enabled:
                if item.principal in signers:
                    raise ValueError("Ambiguous active signing key")
                signers.add(item.principal)
            enrolled.append(
                CommandProducerEnrollment(
                    item.issuer,
                    item.key_id,
                    item.principal,
                    secret=secret,
                    capability=item.capability,
                    signing_enabled=item.signing_enabled,
                )
            )
        return CommandAuthorizationPolicy(tuple(enrolled))
    except (ValueError, TypeError):
        raise CommandAuthorizationRejected("COMMAND_PRODUCER_CONFIGURATION_INVALID") from None


@dataclass(frozen=True, slots=True)
class CommittedCommandVerification:
    """Loaded by the owning durable repository, never from a caller body."""

    tenant_id: str
    command_id: str
    canonical_request_sha256: str
    attestation_sha256: str


@dataclass(frozen=True, slots=True)
class VerifiedCommandAuthorization:
    claims: CommandAuthorizationClaims
    attestation_sha256: str
    durable_replay: bool


@dataclass(frozen=True, slots=True)
class AuthenticatedCommandAuthorization:
    """Crypto/digest authenticity only, not fresh grant/time or replay authority."""

    claims: CommandAuthorizationClaims
    attestation_sha256: str


def _canonical_bytes(value: BaseModel) -> bytes:
    return json.dumps(
        value.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _enrollment(
    claims: CommandAuthorizationClaims, policy: CommandAuthorizationPolicy
) -> CommandProducerEnrollment:
    matches = [
        item
        for item in policy.enrollments
        if (item.issuer, item.key_id, item.principal)
        == (claims.issuer, claims.key_id, claims.principal)
    ]
    if len(matches) != 1 or not matches[0].secret:
        raise CommandAuthorizationRejected("COMMAND_PRODUCER_NOT_ENROLLED")
    return matches[0]


def _require_time(
    claims: CommandAuthorizationClaims, policy: CommandAuthorizationPolicy, now: int
) -> None:
    ttl = claims.expires_at - claims.issued_at
    if ttl <= 0 or ttl > policy.max_ttl_seconds:
        raise CommandAuthorizationRejected("COMMAND_ATTESTATION_TTL_INVALID")
    if claims.issued_at > now + policy.clock_skew_seconds:
        raise CommandAuthorizationRejected("COMMAND_ATTESTATION_FUTURE")
    if now >= claims.expires_at:
        raise CommandAuthorizationRejected("COMMAND_ATTESTATION_EXPIRED")


def sign_command_authorization(
    claims: CommandAuthorizationClaims,
    *,
    principal: VerifiedServicePrincipal,
    tenant_context: TenantContext,
    policy: CommandAuthorizationPolicy,
    now: int,
) -> SignedCommandAuthorization:
    # Frozen models can still be constructed/copied without validation. Never
    # treat their Python type as proof at a signing authority boundary.
    try:
        claims = CommandAuthorizationClaims.model_validate(claims.model_dump(mode="python"))
    except ValidationError:
        raise CommandAuthorizationRejected("COMMAND_ATTESTATION_INVALID") from None
    enrollment = _enrollment(claims, policy)
    expected_actor = tenant_context.actor_id or principal.service_identity
    if (
        not tenant_context.identity_verified
        or tenant_context.service_identity != principal.service_identity
        or claims.principal != principal.service_identity
        or claims.tenant_id != tenant_context.tenant_id_text
        or claims.actor_id != expected_actor
        or SOURCE_CORRECTION_CAPABILITY not in principal.capabilities
        or enrollment.capability != SOURCE_CORRECTION_CAPABILITY
        or not enrollment.signing_enabled
    ):
        raise CommandAuthorizationRejected("COMMAND_CORRECTION_GRANT_REQUIRED")
    _require_time(claims, policy, now)
    signature = hmac.new(
        enrollment.secret.encode("utf-8"), _canonical_bytes(claims), hashlib.sha256
    ).hexdigest()
    return SignedCommandAuthorization(claims=claims, signature=signature)


def verify_command_authorization(
    token: SignedCommandAuthorization,
    *,
    expected_request_sha256: str,
    policy: CommandAuthorizationPolicy,
    now: int,
    committed: CommittedCommandVerification | None = None,
) -> VerifiedCommandAuthorization:
    """Verify authenticity before exact durable replay can bypass expiry.

    Keys must remain configured for replay verification; retired unknown keys
    fail closed. A durable result authorizes no new command or financial effect.
    """
    authenticated = authenticate_command_authorization(
        token, expected_request_sha256=expected_request_sha256, policy=policy
    )
    claims = authenticated.claims
    digest = authenticated.attestation_sha256
    if committed is not None:
        actual = CommittedCommandVerification(
            tenant_id=claims.tenant_id,
            command_id=claims.command_id,
            canonical_request_sha256=expected_request_sha256,
            attestation_sha256=digest,
        )
        if actual != committed:
            raise CommandAuthorizationRejected("COMMAND_DURABLE_REPLAY_CONFLICT")
        return VerifiedCommandAuthorization(claims, digest, True)
    enrollment = _enrollment(claims, policy)
    if enrollment.capability != SOURCE_CORRECTION_CAPABILITY:
        raise CommandAuthorizationRejected("COMMAND_CORRECTION_GRANT_REQUIRED")
    _require_time(claims, policy, now)
    return VerifiedCommandAuthorization(claims, digest, False)


def authenticate_command_authorization(
    token: SignedCommandAuthorization,
    *,
    expected_request_sha256: str,
    policy: CommandAuthorizationPolicy,
) -> AuthenticatedCommandAuthorization:
    """Authenticate before reading a purported durable command identity.

    This result does not bypass expiry or authorize fresh mutation. The owning
    application must call verify_command_authorization with durable evidence.
    """
    try:
        token = SignedCommandAuthorization.model_validate(token.model_dump(mode="python"))
    except ValidationError:
        raise CommandAuthorizationRejected("COMMAND_ATTESTATION_INVALID") from None
    enrollment = _enrollment(token.claims, policy)
    signature = hmac.new(
        enrollment.secret.encode("utf-8"), _canonical_bytes(token.claims), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(signature, token.signature):
        raise CommandAuthorizationRejected("COMMAND_ATTESTATION_SIGNATURE_INVALID")
    if token.claims.canonical_request_sha256 != expected_request_sha256:
        raise CommandAuthorizationRejected("COMMAND_REQUEST_DIGEST_MISMATCH")
    return AuthenticatedCommandAuthorization(
        token.claims, hashlib.sha256(_canonical_bytes(token)).hexdigest()
    )
