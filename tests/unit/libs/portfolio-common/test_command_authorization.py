"""Purpose-scoped delegation and durable replay do not trust caller grants."""

from dataclasses import replace

import pytest
from portfolio_common.command_authorization import (
    SOURCE_CORRECTION_CAPABILITY,
    CommandAuthorizationClaims,
    CommandAuthorizationPolicy,
    CommandAuthorizationRejected,
    CommandProducerEnrollment,
    CommittedCommandVerification,
    sign_command_authorization,
    verify_command_authorization,
)
from portfolio_common.domain.tenant import TenantContext, TenantId
from portfolio_common.enterprise_readiness import VerifiedServicePrincipal
from pydantic import ValidationError


def authority():
    claims = CommandAuthorizationClaims(
        issuer="qualified-test-issuer",
        key_id="active-test-key",
        principal="qualified-test-service",
        actor_id="qualified-test-actor",
        tenant_id="test-tenant",
        command_id="test-command",
        operation_id="test-operation",
        target_transaction_id="test-transaction",
        root_raw_id="test-raw",
        root_raw_sha256="1" * 64,
        expected_head_id="test-raw",
        expected_head_sha256="2" * 64,
        canonical_request_sha256="3" * 64,
        issued_at=100,
        expires_at=200,
        nonce="test-nonce",
        correlation_id="test-correlation",
        trace_id="test-trace",
    )
    enrollment = CommandProducerEnrollment(
        issuer=claims.issuer,
        key_id=claims.key_id,
        principal=claims.principal,
        secret="synthetic-test-key-material-not-enrolled-in-production",
        signing_enabled=True,
    )
    policy = CommandAuthorizationPolicy((enrollment,))
    principal = VerifiedServicePrincipal(claims.principal, {SOURCE_CORRECTION_CAPABILITY})
    context = TenantContext(
        TenantId(claims.tenant_id),
        actor_id=claims.actor_id,
        service_identity=claims.principal,
        identity_verified=True,
    )
    return claims, policy, principal, context


def signed():
    claims, policy, principal, context = authority()
    token = sign_command_authorization(
        claims, principal=principal, tenant_context=context, policy=policy, now=100
    )
    return token, policy


def test_empty_enrollment_denies_signing_and_verification():
    claims, _, principal, context = authority()
    with pytest.raises(CommandAuthorizationRejected, match="NOT_ENROLLED"):
        sign_command_authorization(
            claims,
            principal=principal,
            tenant_context=context,
            policy=CommandAuthorizationPolicy(),
            now=100,
        )
    token, _ = signed()
    with pytest.raises(CommandAuthorizationRejected, match="NOT_ENROLLED"):
        verify_command_authorization(
            token, expected_request_sha256="3" * 64, policy=CommandAuthorizationPolicy(), now=100
        )


@pytest.mark.parametrize("change", ["unverified", "ordinary-grant", "tenant", "actor", "service"])
def test_signer_requires_verified_exact_dedicated_authority(change):
    claims, policy, principal, context = authority()
    if change == "unverified":
        context = replace(context, identity_verified=False)
    elif change == "ordinary-grant":
        principal = VerifiedServicePrincipal(claims.principal, {"ingestion.transactions.write"})
    elif change == "tenant":
        context = replace(context, tenant_id=TenantId("foreign"))
    elif change == "actor":
        context = replace(context, actor_id="foreign")
    else:
        context = replace(context, service_identity="foreign")
    with pytest.raises(CommandAuthorizationRejected, match="GRANT_REQUIRED"):
        sign_command_authorization(
            claims, principal=principal, tenant_context=context, policy=policy, now=100
        )


def test_exact_committed_redelivery_survives_expiry_but_unused_command_does_not():
    token, policy = signed()
    verified = verify_command_authorization(
        token, expected_request_sha256="3" * 64, policy=policy, now=100
    )
    committed = CommittedCommandVerification(
        token.claims.tenant_id,
        token.claims.command_id,
        token.claims.canonical_request_sha256,
        verified.attestation_sha256,
    )
    with pytest.raises(CommandAuthorizationRejected, match="EXPIRED"):
        verify_command_authorization(
            token, expected_request_sha256="3" * 64, policy=policy, now=200
        )
    replay = verify_command_authorization(
        token, expected_request_sha256="3" * 64, policy=policy, now=999, committed=committed
    )
    assert replay.durable_replay and replay.attestation_sha256 == verified.attestation_sha256


@pytest.mark.parametrize(
    "field", ["target_transaction_id", "tenant_id", "expected_head_id", "nonce"]
)
def test_signature_binds_command_owner_revision_and_nonce(field):
    token, policy = signed()
    changed = token.model_copy(
        update={"claims": token.claims.model_copy(update={field: "foreign"})}
    )
    with pytest.raises(CommandAuthorizationRejected, match="SIGNATURE_INVALID"):
        verify_command_authorization(
            changed, expected_request_sha256="3" * 64, policy=policy, now=100
        )


def test_existing_command_identity_does_not_authorize_changed_request_digest():
    token, policy = signed()
    committed = CommittedCommandVerification("test-tenant", "test-command", "3" * 64, "4" * 64)
    with pytest.raises(CommandAuthorizationRejected, match="DIGEST_MISMATCH"):
        verify_command_authorization(
            token, expected_request_sha256="9" * 64, policy=policy, now=999, committed=committed
        )
    with pytest.raises(CommandAuthorizationRejected, match="REPLAY_CONFLICT"):
        verify_command_authorization(
            token, expected_request_sha256="3" * 64, policy=policy, now=999, committed=committed
        )


@pytest.mark.parametrize(
    "field,value", [("purpose", "other"), ("audience", "other"), ("issued_at", True)]
)
def test_claims_are_closed_purpose_scoped_and_strict(field, value):
    claims, _, _, _ = authority()
    with pytest.raises(ValidationError):
        CommandAuthorizationClaims.model_validate({**claims.model_dump(), field: value})


def test_enrollment_never_exposes_secret_in_repr():
    _, policy, _, _ = authority()
    assert policy.enrollments[0].secret not in repr(policy)


def test_unchecked_model_copy_cannot_bypass_literal_purpose_at_signer():
    claims, policy, principal, context = authority()
    claims = claims.model_copy(update={"purpose": "other"})
    with pytest.raises(CommandAuthorizationRejected, match="ATTESTATION_INVALID"):
        sign_command_authorization(
            claims, principal=principal, tenant_context=context, policy=policy, now=100
        )


@pytest.mark.parametrize(
    "field,value", [("purpose", "other"), ("audience", "other"), ("issued_at", True)]
)
def test_verifier_revalidates_unchecked_nested_claims_before_crypto_or_replay(field, value):
    token, policy = signed()
    changed = token.model_copy(update={"claims": token.claims.model_copy(update={field: value})})
    committed = CommittedCommandVerification("test-tenant", "test-command", "3" * 64, "4" * 64)
    with pytest.raises(CommandAuthorizationRejected, match="ATTESTATION_INVALID") as rejected:
        verify_command_authorization(
            changed, expected_request_sha256="3" * 64, policy=policy, now=999, committed=committed
        )
    assert str(rejected.value) == "COMMAND_ATTESTATION_INVALID"
    assert rejected.value.__cause__ is None


def test_previous_verification_key_cannot_sign_new_commands():
    claims, policy, principal, context = authority()
    previous = replace(policy, enrollments=(replace(policy.enrollments[0], signing_enabled=False),))
    with pytest.raises(CommandAuthorizationRejected, match="GRANT_REQUIRED"):
        sign_command_authorization(
            claims, principal=principal, tenant_context=context, policy=previous, now=100
        )
    token, _ = signed()
    verified = verify_command_authorization(
        token, expected_request_sha256="3" * 64, policy=previous, now=100
    )
    assert not verified.durable_replay


def test_retired_key_refuses_even_exact_durable_replay():
    token, policy = signed()
    verified = verify_command_authorization(
        token, expected_request_sha256="3" * 64, policy=policy, now=100
    )
    committed = CommittedCommandVerification(
        token.claims.tenant_id, token.claims.command_id, "3" * 64, verified.attestation_sha256
    )
    with pytest.raises(CommandAuthorizationRejected, match="NOT_ENROLLED"):
        verify_command_authorization(
            token,
            expected_request_sha256="3" * 64,
            policy=CommandAuthorizationPolicy(),
            now=999,
            committed=committed,
        )


@pytest.mark.parametrize(
    "issued_at,expires_at,now,reason",
    [
        (100, 100, 100, "TTL_INVALID"),
        (100, 401, 100, "TTL_INVALID"),
        (131, 200, 100, "FUTURE"),
        (100, 200, 200, "EXPIRED"),
    ],
)
def test_signer_refuses_invalid_time_authority(issued_at, expires_at, now, reason):
    claims, policy, principal, context = authority()
    claims = claims.model_copy(update={"issued_at": issued_at, "expires_at": expires_at})
    with pytest.raises(CommandAuthorizationRejected, match=reason):
        sign_command_authorization(
            claims, principal=principal, tenant_context=context, policy=policy, now=now
        )


def test_modified_token_never_borrows_committed_replay_authority():
    token, policy = signed()
    verified = verify_command_authorization(
        token, expected_request_sha256="3" * 64, policy=policy, now=100
    )
    committed = CommittedCommandVerification(
        token.claims.tenant_id, token.claims.command_id, "3" * 64, verified.attestation_sha256
    )
    changed = token.model_copy(update={"signature": "0" * 64})
    with pytest.raises(CommandAuthorizationRejected, match="SIGNATURE_INVALID"):
        verify_command_authorization(
            changed, expected_request_sha256="3" * 64, policy=policy, now=999, committed=committed
        )
