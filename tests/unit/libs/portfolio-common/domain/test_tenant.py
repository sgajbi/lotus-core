from dataclasses import FrozenInstanceError

import pytest
from portfolio_common.domain.tenant import (
    MAX_TENANT_ID_LENGTH,
    TenantAuthorityMismatchError,
    TenantContext,
    TenantId,
    bind_tenant_authority,
)


def test_tenant_id_normalizes_only_boundary_whitespace() -> None:
    tenant_id = TenantId("  Tenant-SG-01  ")

    assert tenant_id.value == "Tenant-SG-01"
    assert str(tenant_id) == "Tenant-SG-01"


@pytest.mark.parametrize("value", ["", " ", "\t\n"])
def test_tenant_id_rejects_blank_identity(value: str) -> None:
    with pytest.raises(ValueError, match="must be nonblank"):
        TenantId(value)


def test_tenant_id_rejects_unbounded_identity() -> None:
    with pytest.raises(ValueError, match=f"must not exceed {MAX_TENANT_ID_LENGTH}"):
        TenantId("t" * (MAX_TENANT_ID_LENGTH + 1))


def test_tenant_context_is_immutable_and_preserves_verified_authority() -> None:
    context = TenantContext(
        tenant_id=TenantId(" tenant-sg "),
        actor_id=" operator-1 ",
        role=" operations ",
        service_identity=" lotus-gateway ",
        correlation_id=" correlation-1 ",
        identity_verified=True,
    )

    assert context.tenant_id_text == "tenant-sg"
    assert context.actor_id == "operator-1"
    assert context.identity_verified is True
    with pytest.raises(FrozenInstanceError):
        context.actor_id = "other"  # type: ignore[misc]


def test_tenant_context_requires_canonical_tenant_value_object() -> None:
    with pytest.raises(TypeError, match="must be a TenantId"):
        TenantContext(tenant_id="tenant-sg")  # type: ignore[arg-type]


def test_bind_tenant_authority_rejects_conflicting_payload_scope() -> None:
    context = TenantContext(tenant_id=TenantId("tenant-a"), identity_verified=True)

    with pytest.raises(TenantAuthorityMismatchError, match="does not match"):
        bind_tenant_authority("tenant-b", context)


def test_bind_tenant_authority_overwrites_omitted_scope_with_admitted_value() -> None:
    context = TenantContext(tenant_id=TenantId("tenant-a"), identity_verified=True)

    assert bind_tenant_authority(None, context) == "tenant-a"
