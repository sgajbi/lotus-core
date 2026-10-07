"""Submission permission cannot become institutional provider qualification."""

from dataclasses import replace

import pytest
from portfolio_common.domain.portfolio_source_observations import (
    ObservationConflict,
    ObservationFamily,
)
from portfolio_common.domain.tenant import TenantContext, TenantId
from portfolio_common.portfolio_source_observation_qualification import (
    ProducerSubmissionGrant,
    UnqualifiedProducerAuthority,
)

pytestmark = [pytest.mark.unit, pytest.mark.security]

GRANT = ProducerSubmissionGrant(
    "TENANT_SYNTHETIC",
    "PORTFOLIO_SYNTHETIC",
    "producer-synthetic",
    ObservationFamily.CASH_AVAILABILITY,
)
CONTEXT = TenantContext(
    TenantId("TENANT_SYNTHETIC"), service_identity="producer-synthetic", identity_verified=True
)


def test_empty_default_refuses_even_verified_identity() -> None:
    with pytest.raises(ObservationConflict, match="SOURCE_OBSERVATION_PRODUCER_NOT_ADMITTED"):
        UnqualifiedProducerAuthority().admit(CONTEXT, GRANT)


def test_explicit_server_grant_only_retains_unqualified_assertion() -> None:
    admission = UnqualifiedProducerAuthority((GRANT,)).admit(CONTEXT, GRANT)
    assert admission.grant == GRANT
    assert admission.qualification == "unqualified"
    assert admission.policy_version == "portfolio-source-observation-admission.v1"


@pytest.mark.parametrize(
    "changes",
    [
        {"identity_verified": False},
        {"service_identity": "other-producer"},
        {"tenant_id": TenantId("OTHER_TENANT")},
        {"service_identity": None},
    ],
)
def test_missing_or_mismatched_trusted_context_refused(changes) -> None:
    with pytest.raises(ObservationConflict, match="SOURCE_OBSERVATION_PRODUCER_NOT_ADMITTED"):
        UnqualifiedProducerAuthority((GRANT,)).admit(replace(CONTEXT, **changes), GRANT)


@pytest.mark.parametrize(
    "changes",
    [
        {"portfolio_id": "OTHER_PORTFOLIO"},
        {"family": ObservationFamily.FUNDING_INVESTMENT},
        {"producer_id": "other-producer"},
        {"tenant_id": "OTHER_TENANT"},
    ],
)
def test_grant_cannot_be_reused_for_different_scope(changes) -> None:
    with pytest.raises(ObservationConflict, match="SOURCE_OBSERVATION_PRODUCER_NOT_ADMITTED"):
        UnqualifiedProducerAuthority((GRANT,)).admit(CONTEXT, replace(GRANT, **changes))


def test_revoked_grant_cannot_be_resubmitted_and_duplicate_configuration_refused() -> None:
    assert (
        UnqualifiedProducerAuthority((GRANT,)).admit(CONTEXT, GRANT).qualification == "unqualified"
    )
    with pytest.raises(ObservationConflict):
        UnqualifiedProducerAuthority().admit(CONTEXT, GRANT)
    with pytest.raises(ValueError, match="duplicate"):
        UnqualifiedProducerAuthority((GRANT, GRANT))


@pytest.mark.parametrize("value", ["", " producer ", "bad\nproducer", "x" * 129])
def test_server_grant_cannot_admit_malformed_producer_identity(value) -> None:
    with pytest.raises(ValueError):
        replace(GRANT, producer_id=value)
