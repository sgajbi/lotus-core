"""Server enrollment controls with explicitly synthetic principal and calendar."""

from dataclasses import replace
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

import pytest
from portfolio_common.domain.market_data.fx_source import (
    FxSourceCut,
    FxSourceRevision,
    FxSourceScope,
    fx_cut_membership_hash,
)
from portfolio_common.domain.tenant import TenantContext, TenantId
from portfolio_common.enterprise_readiness import VerifiedServicePrincipal
from portfolio_common.fx_cut_authorization import (
    CommittedFxCutVerification,
    FxCutRelayKey,
    FxCutRelayPolicy,
    sign_fx_cut_authorization,
    verify_fx_cut_authorization,
)
from portfolio_common.fx_source_admission import (
    FX_SOURCE_SUBMIT_CAPABILITY,
    FxFixingCalendar,
    FxSourceAdmissionPolicy,
    FxSourceAdmissionRejected,
    FxSourceEnrollment,
)

pytestmark = [pytest.mark.unit, pytest.mark.security, pytest.mark.contract]
NOW = datetime(2026, 10, 8, 16, tzinfo=UTC)
SCOPE = FxSourceScope("SYNTHETIC_TENANT", "SYNTHETIC_PROVIDER", "SYNTHETIC_FEED")
PRINCIPAL = VerifiedServicePrincipal("SYNTHETIC_INGEST", {FX_SOURCE_SUBMIT_CAPABILITY})
CONTEXT = TenantContext(
    TenantId(SCOPE.tenant_id), service_identity=PRINCIPAL.service_identity, identity_verified=True
)
CALENDAR = FxFixingCalendar("SYNTHETIC_V1", "CLOSE", "UTC", time(16), 60)
ENROLLMENT = FxSourceEnrollment(
    "SYNTHETIC_ENROLLMENT_V1",
    SCOPE,
    PRINCIPAL.service_identity,
    (("USD", "SGD"),),
    CALENDAR.version,
    NOW - timedelta(days=1),
    NOW + timedelta(days=1),
)
POLICY = FxSourceAdmissionPolicy((ENROLLMENT,), (CALENDAR,))
RELAY = FxCutRelayPolicy((FxCutRelayKey("SYNTHETIC_CORE", "SYNTHETIC_KEY", "x" * 32, True),))


def make_cut(**member_changes: object) -> FxSourceCut:
    member = FxSourceRevision(
        SCOPE,
        "USD-SGD-CLOSE",
        "1",
        "USD",
        "SGD",
        date(2026, 10, 8),
        Decimal("1.35"),
        NOW,
        "CLOSE",
        CALENDAR.version,
    )
    member = replace(member, **member_changes)
    return FxSourceCut(
        member.scope,
        "SYNTHETIC_CLOSE",
        "1",
        max(NOW, member.source_observed_at),
        (member,),
        1,
        fx_cut_membership_hash((member,)),
    )


def test_valid_server_configuration_binds_accepted_time_and_enrollment() -> None:
    admitted = POLICY.admit(make_cut(), context=CONTEXT, principal=PRINCIPAL, now=NOW)
    assert admitted.accepted_at == NOW
    assert admitted.enrollment_version == ENROLLMENT.version
    assert admitted.calendar_version == CALENDAR.version
    assert admitted.cut.scope == SCOPE


@pytest.mark.parametrize(
    "context",
    [
        replace(CONTEXT, identity_verified=False),
        replace(CONTEXT, service_identity="UNVERIFIED_OTHER"),
        replace(CONTEXT, tenant_id=TenantId("OTHER_TENANT")),
    ],
)
def test_bypass_and_scope_mismatch_refuse(context: TenantContext) -> None:
    with pytest.raises(FxSourceAdmissionRejected, match="VERIFIED_PRINCIPAL_REQUIRED"):
        POLICY.admit(make_cut(), context=context, principal=PRINCIPAL, now=NOW)


@pytest.mark.parametrize("principal", [None, VerifiedServicePrincipal("SYNTHETIC_INGEST", set())])
def test_missing_verified_principal_or_capability_refuses(principal: object) -> None:
    with pytest.raises(FxSourceAdmissionRejected, match="VERIFIED_PRINCIPAL_REQUIRED"):
        POLICY.admit(make_cut(), context=CONTEXT, principal=principal, now=NOW)


@pytest.mark.parametrize(
    "policy",
    [
        FxSourceAdmissionPolicy(),
        replace(POLICY, enrollments=(replace(ENROLLMENT, active=False),)),
        replace(POLICY, enrollments=(replace(ENROLLMENT, valid_until=NOW),)),
        replace(
            POLICY, enrollments=(replace(ENROLLMENT, scope=replace(SCOPE, provider_id="OTHER")),)
        ),
    ],
)
def test_empty_revoked_expired_or_other_provider_configuration_denies(
    policy: FxSourceAdmissionPolicy,
) -> None:
    with pytest.raises(FxSourceAdmissionRejected, match="ENROLLMENT_REQUIRED"):
        policy.admit(make_cut(), context=CONTEXT, principal=PRINCIPAL, now=NOW)


def test_unknown_calendar_and_wrong_pair_refuse() -> None:
    with pytest.raises(FxSourceAdmissionRejected, match="CALENDAR_REQUIRED"):
        replace(POLICY, calendars=()).admit(
            make_cut(), context=CONTEXT, principal=PRINCIPAL, now=NOW
        )
    with pytest.raises(FxSourceAdmissionRejected, match="PAIR_NOT_ENROLLED"):
        POLICY.admit(make_cut(to_currency="EUR"), context=CONTEXT, principal=PRINCIPAL, now=NOW)


@pytest.mark.parametrize(
    "changes",
    [
        {"fixing_kind": "INTRADAY"},
        {"calendar_version": "UNAPPROVED"},
        {"rate_date": date(2026, 10, 7)},
        {"source_observed_at": NOW - timedelta(seconds=1)},
    ],
)
def test_fixing_kind_calendar_business_date_and_cutoff_refuse(changes: dict[str, object]) -> None:
    with pytest.raises(FxSourceAdmissionRejected, match="FIXING_NOT_ADMITTED"):
        POLICY.admit(make_cut(**changes), context=CONTEXT, principal=PRINCIPAL, now=NOW)


def test_closed_date_and_weekend_are_not_inferred_business_days() -> None:
    assert not replace(CALENDAR, closed_dates=(NOW.date(),)).permits(NOW.date(), NOW)
    saturday = NOW + timedelta(days=2)
    assert not CALENDAR.permits(saturday.date(), saturday)


def test_calendar_publication_boundary_is_explicit() -> None:
    assert CALENDAR.permits(NOW.date(), NOW + timedelta(seconds=60))
    assert not CALENDAR.permits(NOW.date(), NOW + timedelta(seconds=61))


@pytest.mark.parametrize(
    "business_date,fixing_time,observed_at,expected",
    [
        (date(2026, 11, 1), time(1, 30), datetime(2026, 11, 1, 5, 30, tzinfo=UTC), False),
        (date(2026, 11, 1), time(1, 30), datetime(2026, 11, 1, 6, 30, tzinfo=UTC), False),
        (date(2026, 3, 8), time(2, 30), datetime(2026, 3, 8, 7, 30, tzinfo=UTC), False),
        (date(2026, 3, 9), time(2, 30), datetime(2026, 3, 9, 6, 30, tzinfo=UTC), True),
    ],
    ids=["ambiguous-first-fold", "ambiguous-second-fold", "nonexistent", "ordinary-day"],
)
def test_calendar_refuses_dst_ambiguity_and_gap_but_accepts_ordinary_fixing(
    business_date, fixing_time, observed_at, expected
) -> None:
    calendar = replace(
        CALENDAR,
        timezone="America/New_York",
        fixing_time=fixing_time,
        business_weekdays=tuple(range(7)),
    )
    assert calendar.permits(business_date, observed_at) is expected


def test_ambiguous_provider_authority_configuration_is_rejected() -> None:
    with pytest.raises(ValueError, match="AMBIGUOUS"):
        replace(POLICY, enrollments=(ENROLLMENT, replace(ENROLLMENT, version="OTHER")))
    with pytest.raises(ValueError, match="AMBIGUOUS"):
        replace(POLICY, calendars=(CALENDAR, replace(CALENDAR, fixing_kind="OTHER")))


def signed_cut():
    return sign_fx_cut_authorization(
        make_cut(),
        context=CONTEXT,
        principal=PRINCIPAL,
        admission_policy=POLICY,
        relay_policy=RELAY,
        now=NOW,
    )


def test_signed_relay_preserves_original_verified_admission() -> None:
    token = signed_cut()
    verified = verify_fx_cut_authorization(
        token,
        make_cut(),
        admission_policy=POLICY,
        relay_policy=RELAY,
        now=NOW + timedelta(seconds=1),
    )
    assert not verified.durable_replay
    assert verified.admission.accepted_at == NOW
    assert verified.admission.cut.content_hash == token.claims.content_hash
    assert len(verified.attestation_sha256) == 64


def test_changed_economics_with_recomputed_content_hash_cannot_reuse_signature() -> None:
    token = signed_cut()
    changed_cut = make_cut(rate=Decimal("1.36"))
    with pytest.raises(FxSourceAdmissionRejected, match="CONTENT_MISMATCH"):
        verify_fx_cut_authorization(
            token, changed_cut, admission_policy=POLICY, relay_policy=RELAY, now=NOW
        )
    forged = token.model_copy(
        update={
            "claims": token.claims.model_copy(update={"content_hash": changed_cut.content_hash})
        }
    )
    with pytest.raises(FxSourceAdmissionRejected, match="SIGNATURE_INVALID"):
        verify_fx_cut_authorization(
            forged, changed_cut, admission_policy=POLICY, relay_policy=RELAY, now=NOW
        )


def test_expiry_and_revocation_deny_fresh_work_but_exact_retained_replay_survives() -> None:
    token = signed_cut()
    verified = verify_fx_cut_authorization(
        token, make_cut(), admission_policy=POLICY, relay_policy=RELAY, now=NOW
    )
    retained = CommittedFxCutVerification(
        make_cut().cut_id, make_cut().content_hash, verified.attestation_sha256
    )
    after_expiry = NOW + timedelta(seconds=300)
    with pytest.raises(FxSourceAdmissionRejected, match="EXPIRED_OR_FUTURE"):
        verify_fx_cut_authorization(
            token, make_cut(), admission_policy=POLICY, relay_policy=RELAY, now=after_expiry
        )
    with pytest.raises(FxSourceAdmissionRejected, match="ENROLLMENT_REQUIRED"):
        verify_fx_cut_authorization(
            token,
            make_cut(),
            admission_policy=FxSourceAdmissionPolicy(),
            relay_policy=RELAY,
            now=NOW,
        )
    replay = verify_fx_cut_authorization(
        token,
        make_cut(),
        admission_policy=FxSourceAdmissionPolicy(),
        relay_policy=RELAY,
        now=after_expiry,
        committed=retained,
    )
    assert replay.durable_replay
    assert replay.admission.accepted_at == NOW
    with pytest.raises(FxSourceAdmissionRejected, match="RETAINED_REPLAY_MISMATCH"):
        verify_fx_cut_authorization(
            token,
            make_cut(),
            admission_policy=POLICY,
            relay_policy=RELAY,
            now=after_expiry,
            committed=replace(retained, attestation_sha256="0" * 64),
        )


def test_unknown_relay_key_and_missing_signer_never_fallback() -> None:
    with pytest.raises(FxSourceAdmissionRejected, match="KEY_REQUIRED"):
        verify_fx_cut_authorization(
            signed_cut(),
            make_cut(),
            admission_policy=POLICY,
            relay_policy=FxCutRelayPolicy(),
            now=NOW,
        )
    with pytest.raises(FxSourceAdmissionRejected, match="SIGNER_REQUIRED"):
        sign_fx_cut_authorization(
            make_cut(),
            context=CONTEXT,
            principal=PRINCIPAL,
            admission_policy=POLICY,
            relay_policy=FxCutRelayPolicy(),
            now=NOW,
        )
