"""Synthetic cryptographic controls, never provider or monthly approval proof."""

import hashlib
import hmac
import json
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from portfolio_common.api_contract.portfolio_source_verification import (
    ObservationVerificationClaims,
    ObservationVerificationScope,
    ObservationVerificationSubject,
    SignedObservationVerificationReceipt,
)
from portfolio_common.domain.portfolio_source_observations import (
    CashAvailabilityObservation,
    FundingInvestmentObservation,
    ObservationConflict,
    ObservationCoverage,
    ObservationEnvelope,
)
from portfolio_common.portfolio_source_observation_verification import (
    ObservationCutRegistration,
    ObservationReceiptVerifier,
    ObservationVerificationAuthority,
    ObservationVerificationKey,
    observation_verification_claims_bytes,
)
from pydantic import ValidationError

pytestmark = [pytest.mark.unit, pytest.mark.security]
NOW = datetime(2026, 10, 9, 4, tzinfo=timezone.utc)
SECRET = "synthetic-unit-only-verification-key-not-provider"
ENVELOPE = ObservationEnvelope(
    tenant_id="TENANT_SYNTHETIC",
    portfolio_id="PORTFOLIO_SYNTHETIC",
    producer_id="synthetic-producer",
    source_record_id="synthetic-fact",
    source_revision=1,
    source_cut_id="synthetic-cut",
    definition_version="synthetic-definition-v1",
    effective_from=date(2026, 10, 1),
    effective_to=date(2026, 11, 1),
    observed_at=NOW - timedelta(hours=2),
    generated_at=NOW - timedelta(hours=1),
    coverage=ObservationCoverage.COMPLETE,
    coverage_scope="synthetic-portfolio-cut",
)


def subject(observation=None):
    observation = observation or CashAvailabilityObservation(
        ENVELOPE, "SGD", Decimal("0"), None, Decimal("2.5")
    )
    return ObservationVerificationSubject.from_observation(
        observation,
        source_cut_manifest_hash="a" * 64,
        consumer_id="synthetic-manage-consumer",
        as_of_date=date(2026, 10, 9),
    )


def key(expected):
    return ObservationVerificationKey(
        "synthetic-verifier",
        "synthetic-key-v1",
        ObservationVerificationScope.from_subject(expected),
        NOW - timedelta(days=1),
        NOW + timedelta(days=1),
        SECRET,
    )


def receipt(expected, **changes):
    claims = ObservationVerificationClaims(
        issuer_id="synthetic-verifier",
        key_id="synthetic-key-v1",
        artifact_revision="synthetic-artifact-v1",
        subject=expected,
        issued_at=NOW - timedelta(minutes=1),
        expires_at=NOW + timedelta(minutes=10),
        **changes,
    )
    return sign(claims)


def sign(claims):
    signature = hmac.new(
        SECRET.encode(), observation_verification_claims_bytes(claims), hashlib.sha256
    ).hexdigest()
    return SignedObservationVerificationReceipt(claims=claims, signature=signature)


@pytest.mark.parametrize("readiness", [False, True])
def test_synthetic_valid_receipt_preserves_fact_hash_and_unknown_values(readiness):
    fact = (
        FundingInvestmentObservation(ENVELOPE, None, False)
        if readiness
        else CashAvailabilityObservation(ENVELOPE, "SGD", Decimal("0"), None, Decimal("2.5"))
    )
    original_hash = fact.content_hash
    expected = subject(fact)
    signed = receipt(expected)
    verified = ObservationReceiptVerifier((key(expected),)).verify(
        signed, expected=expected, now=NOW
    )
    assert verified.receipt == signed
    assert len(verified.attestation_sha256) == 64
    assert expected.content_hash == original_hash == fact.content_hash
    assert not hasattr(verified, "qualification")
    if readiness:
        assert fact.funded is None and fact.invested is False
        assert expected.currency is None
    else:
        assert fact.settled == Decimal("0") and fact.encumbered is None
        assert fact.available == Decimal("2.5")


def test_empty_trust_never_promotes_an_authenticated_assertion():
    expected = subject()
    with pytest.raises(ObservationConflict, match="AUTHORITY_UNAVAILABLE"):
        ObservationReceiptVerifier().verify(receipt(expected), expected=expected, now=NOW)


@pytest.mark.parametrize(
    "field,value",
    [
        ("tenant_id", "OTHER_TENANT"),
        ("portfolio_id", "OTHER_PORTFOLIO"),
        ("producer_id", "other-producer"),
        ("source_record_id", "other-fact"),
        ("source_cut_id", "other-cut"),
        ("definition_version", "other-definition"),
        ("coverage_scope", "other-scope"),
        ("observed_at", NOW - timedelta(hours=3)),
        ("generated_at", NOW - timedelta(minutes=30)),
        ("effective_from", date(2026, 10, 2)),
        ("effective_to", date(2026, 10, 31)),
    ],
)
def test_signed_receipt_cannot_replace_original_envelope_custody(field, value):
    expected = subject()
    other = expected.model_copy(update={"envelope": replace(ENVELOPE, **{field: value})})
    with pytest.raises(ObservationConflict, match="BINDING_MISMATCH"):
        ObservationReceiptVerifier((key(expected),)).verify(
            receipt(other), expected=expected, now=NOW
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("content_hash", "b" * 64),
        ("source_cut_manifest_hash", "c" * 64),
        ("consumer_id", "other-consumer"),
        ("currency", "USD"),
        ("as_of_date", date(2026, 10, 10)),
    ],
)
def test_receipt_rebinding_requires_independently_resolved_expected_identity(field, value):
    expected = subject()
    other = expected.model_copy(update={field: value})
    with pytest.raises(ObservationConflict, match="BINDING_MISMATCH"):
        ObservationReceiptVerifier((key(expected),)).verify(
            receipt(other), expected=expected, now=NOW
        )


def test_correction_same_business_date_cannot_reuse_original_receipt():
    expected = subject()
    corrected = expected.model_copy(
        update={
            "envelope": replace(
                ENVELOPE,
                source_revision=2,
                predecessor_id=expected.content_hash,
                expected_head_hash=expected.content_hash,
            ),
            "content_hash": "d" * 64,
        }
    )
    with pytest.raises(ObservationConflict, match="BINDING_MISMATCH"):
        ObservationReceiptVerifier((key(expected),)).verify(
            receipt(expected), expected=corrected, now=NOW
        )


@pytest.mark.parametrize(
    "purpose", ["COMPOSITE_MONTHLY_SOURCE_CUT", "FX_SOURCE_CUT", "PRODUCER_SUBMISSION"]
)
def test_unsafe_purpose_copy_cannot_bypass_closed_receipt_contract(purpose):
    expected = subject()
    unsafe = receipt(expected).claims.model_copy(update={"purpose": purpose})
    with pytest.raises(ObservationConflict, match="SHAPE_INVALID"):
        ObservationReceiptVerifier((key(expected),)).verify(
            sign(unsafe), expected=expected, now=NOW
        )


def test_signature_tampering_refused_without_leaking_claims_or_key():
    expected = subject()
    tampered = receipt(expected).model_copy(update={"signature": "0" * 64})
    with pytest.raises(ObservationConflict, match="^SOURCE_VERIFICATION_SIGNATURE_INVALID$"):
        ObservationReceiptVerifier((key(expected),)).verify(tampered, expected=expected, now=NOW)
    assert SECRET not in repr(key(expected))


@pytest.mark.parametrize("offset", [-61, 600, 601])
def test_future_or_expired_receipt_exact_boundaries_refused(offset):
    expected = subject()
    with pytest.raises(ObservationConflict, match="EXPIRED_OR_REVOKED"):
        ObservationReceiptVerifier((key(expected),)).verify(
            receipt(expected), expected=expected, now=NOW + timedelta(seconds=offset)
        )


def test_revocation_and_key_validity_refused_even_with_valid_signature():
    expected = subject()
    for invalid_key in (
        replace(key(expected), revoked_at=NOW),
        replace(key(expected), valid_to=NOW + timedelta(minutes=9)),
        replace(key(expected), valid_from=NOW),
    ):
        with pytest.raises(ObservationConflict, match="EXPIRED_OR_REVOKED"):
            ObservationReceiptVerifier((invalid_key,)).verify(
                receipt(expected), expected=expected, now=NOW
            )


@pytest.mark.parametrize("coverage", [ObservationCoverage.PARTIAL, ObservationCoverage.MISSING])
def test_valid_signature_never_turns_incomplete_coverage_into_complete(coverage):
    expected = subject(
        CashAvailabilityObservation(replace(ENVELOPE, coverage=coverage), "SGD", None, None, None)
    )
    with pytest.raises(ObservationConflict, match="COVERAGE_INCOMPLETE"):
        ObservationReceiptVerifier((key(expected),)).verify(
            receipt(expected), expected=expected, now=NOW
        )


def test_invalid_key_configuration_and_unknown_wire_fields_refused():
    expected = subject()
    with pytest.raises(ValueError, match="duplicate"):
        ObservationReceiptVerifier((key(expected), key(expected)))
    with pytest.raises(ValueError):
        replace(key(expected), secret="short")
    wire = receipt(expected).model_dump(mode="json")
    wire["qualified"] = True
    with pytest.raises(ValidationError):
        SignedObservationVerificationReceipt.model_validate(wire)


@pytest.mark.parametrize(
    "changes",
    [
        {"valid_from": None},
        {"valid_to": "tomorrow"},
        {"secret": None},
        {"valid_from": NOW.replace(tzinfo=None)},
        {"revoked_at": "today"},
    ],
)
def test_malformed_server_key_configuration_fails_at_construction(changes):
    with pytest.raises(ValueError):
        replace(key(subject()), **changes)


@pytest.mark.parametrize("now", [NOW.replace(tzinfo=None), None, "2026-10-09"])
def test_invalid_evaluation_clock_refused_with_source_safe_error(now):
    expected = subject()
    with pytest.raises(ObservationConflict, match="EXPIRED_OR_REVOKED"):
        ObservationReceiptVerifier((key(expected),)).verify(
            receipt(expected), expected=expected, now=now
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("content_hash", "not-a-digest"),
        ("consumer_id", " "),
        ("currency", "sgd"),
        ("as_of_date", date(2026, 11, 1)),
    ],
)
def test_unsafe_expected_copy_is_revalidated_before_trust(field, value):
    expected = subject()
    unsafe = expected.model_copy(update={field: value})
    with pytest.raises(ObservationConflict, match="SHAPE_INVALID"):
        ObservationReceiptVerifier((key(expected),)).verify(
            receipt(expected), expected=unsafe, now=NOW
        )


@pytest.mark.parametrize("revision", [0, True, "1"])
def test_unsafe_envelope_instance_cannot_hide_invalid_original_revision(revision):
    expected = subject()
    unsafe_envelope = replace(ENVELOPE)
    object.__setattr__(unsafe_envelope, "source_revision", revision)
    unsafe = expected.model_copy(update={"envelope": unsafe_envelope})
    with pytest.raises(ObservationConflict, match="SHAPE_INVALID"):
        ObservationReceiptVerifier((key(expected),)).verify(
            receipt(expected), expected=unsafe, now=NOW
        )


def authority(expected):
    return ObservationVerificationAuthority(
        ObservationReceiptVerifier((key(expected),)),
        (
            ObservationCutRegistration(
                ObservationVerificationScope.from_subject(expected),
                expected.envelope.source_cut_id,
                expected.source_cut_manifest_hash,
            ),
        ),
    )


def test_empty_deployed_registry_denies_trust(monkeypatch):
    from portfolio_common.portfolio_source_verification_configuration import (
        load_observation_verification_authority,
    )

    monkeypatch.delenv("LOTUS_PORTFOLIO_FACT_VERIFICATION_KEYS", raising=False)
    monkeypatch.delenv("LOTUS_PORTFOLIO_FACT_VERIFICATION_CUTS", raising=False)
    configured = load_observation_verification_authority()
    assert configured.verifier.keys == () and configured.cuts == ()


@pytest.mark.parametrize(
    "invalid", ["{}", "[{}]", "x" * 65537], ids=["object", "missing", "oversize"]
)
def test_invalid_registry_refuses_with_bounded_source_safe_reason(monkeypatch, invalid):
    from portfolio_common import portfolio_source_verification_configuration as configuration

    # Probe the loader's bound without exceeding Windows' own environment-value limit.
    monkeypatch.setattr(configuration, "env_str", lambda name, default: invalid)
    with pytest.raises(ValueError) as error:
        configuration.load_observation_verification_authority()
    assert str(error.value) == "SOURCE_VERIFICATION_CONFIGURATION_INVALID"


def test_explicit_key_and_independent_cut_configuration_accept_then_revoke(monkeypatch):
    from portfolio_common.portfolio_source_verification_configuration import (
        load_observation_verification_authority,
    )

    expected = subject()
    scope = ObservationVerificationScope.from_subject(expected).model_dump(mode="json")
    entry = dict(
        scope=scope,
        issuer_id="synthetic-verifier",
        key_id="synthetic-key-v1",
        valid_from=(NOW - timedelta(days=1)).isoformat(),
        valid_to=(NOW + timedelta(days=1)).isoformat(),
        secret_env="LOTUS_PORTFOLIO_FACT_VERIFICATION_KEY_UNIT",
    )
    monkeypatch.setenv("LOTUS_PORTFOLIO_FACT_VERIFICATION_KEY_UNIT", SECRET)
    monkeypatch.setenv("LOTUS_PORTFOLIO_FACT_VERIFICATION_KEYS", json.dumps([entry]))
    monkeypatch.setenv(
        "LOTUS_PORTFOLIO_FACT_VERIFICATION_CUTS",
        json.dumps(
            [dict(scope=scope, source_cut_id=ENVELOPE.source_cut_id, manifest_hash="a" * 64)]
        ),
    )
    configured = load_observation_verification_authority()
    assert (
        configured.verifier.verify(
            receipt(expected), expected=expected, now=NOW
        ).receipt.claims.subject
        == expected
    )
    entry["revoked_at"] = NOW.isoformat()
    monkeypatch.setenv("LOTUS_PORTFOLIO_FACT_VERIFICATION_KEYS", json.dumps([entry]))
    with pytest.raises(ObservationConflict, match="EXPIRED_OR_REVOKED"):
        load_observation_verification_authority().verifier.verify(
            receipt(expected), expected=expected, now=NOW
        )


def test_registered_manifest_cannot_be_replaced_by_a_signed_caller_digest():
    fact = CashAvailabilityObservation(ENVELOPE, "SGD", Decimal("0"), None, Decimal("2.5"))
    expected = subject(fact)
    trusted = authority(expected)
    verified = trusted.verify_fact(
        fact,
        receipt(expected),
        consumer_id=expected.consumer_id,
        as_of_date=expected.as_of_date,
        now=NOW,
    )
    assert verified.receipt.claims.subject == expected
    caller = expected.model_copy(update={"source_cut_manifest_hash": "b" * 64})
    with pytest.raises(ObservationConflict, match="BINDING_MISMATCH"):
        trusted.verify_fact(
            fact,
            receipt(caller),
            consumer_id=expected.consumer_id,
            as_of_date=expected.as_of_date,
            now=NOW,
        )
    with pytest.raises(ObservationConflict, match="CUT_UNAVAILABLE"):
        ObservationVerificationAuthority(trusted.verifier).verify_fact(
            fact,
            receipt(expected),
            consumer_id=expected.consumer_id,
            as_of_date=expected.as_of_date,
            now=NOW,
        )


@pytest.mark.parametrize("consumer", ["synthetic-manage-consumer", "foreign-consumer"])
@pytest.mark.asyncio
async def test_existing_read_port_projects_only_current_consumer_bound_receipt(
    monkeypatch, consumer
):
    from src.services.query_control_plane_service.app.application import (
        portfolio_source_observations as app,
    )
    from src.services.query_control_plane_service.app.contracts import (
        portfolio_source_observations as contracts,
    )
    from src.services.query_control_plane_service.app.ports.portfolio_source_observations import (
        PersistedSourceObservation,
    )

    class Clock:
        @staticmethod
        def now(zone):
            return NOW

    monkeypatch.setattr(app, "datetime", Clock)
    fact = CashAvailabilityObservation(ENVELOPE, "SGD", Decimal("0"), None, Decimal("2.5"))
    expected = subject(fact)
    signed = receipt(expected)
    record = PersistedSourceObservation(
        fact, fact.content_hash, NOW, "synthetic-job", "unqualified", (signed,)
    )

    class Reader:
        async def read_snapshot(self, **scope):
            return record, None

    request = contracts.PortfolioSourceObservationsRequest(
        as_of_date=expected.as_of_date,
        cash=contracts.ObservationSelector(
            producer_id=ENVELOPE.producer_id,
            source_record_id=ENVELOPE.source_record_id,
            observation_id=fact.content_hash,
            content_hash=fact.content_hash,
            source_cut_id=ENVELOPE.source_cut_id,
            source_version=1,
        ),
    )
    service = app.PortfolioSourceObservationsService(Reader(), authority(expected))
    result = await service.query(
        tenant_id=ENVELOPE.tenant_id,
        portfolio_id=ENVELOPE.portfolio_id,
        request=request,
        consumer_id=consumer,
    )
    assert result.fact_verification_status == (
        "FACT_VERIFIED" if consumer == expected.consumer_id else "UNAVAILABLE"
    )
    assert (
        result.cash.content_hash == fact.content_hash and result.cash.qualification == "unqualified"
    )
    assert result.cash.verification_receipt == (
        signed if consumer == expected.consumer_id else None
    )
    rejected = await service.query(
        tenant_id="foreign-tenant",
        portfolio_id=ENVELOPE.portfolio_id,
        request=request,
        consumer_id=consumer,
    )
    assert rejected.cash is None and rejected.fact_verification_status == "UNAVAILABLE"
