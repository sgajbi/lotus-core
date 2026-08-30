"""Canonical tenant identity and request-scoped authority context."""

from __future__ import annotations

from dataclasses import dataclass

MAX_TENANT_ID_LENGTH = 128


@dataclass(frozen=True, slots=True)
class TenantId:
    """A nonblank, source-owned tenant identifier."""

    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str):
            raise TypeError("tenant_id must be a string")
        normalized = self.value.strip()
        if not normalized:
            raise ValueError("tenant_id must be nonblank")
        if len(normalized) > MAX_TENANT_ID_LENGTH:
            raise ValueError(f"tenant_id must not exceed {MAX_TENANT_ID_LENGTH} characters")
        object.__setattr__(self, "value", normalized)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class TenantContext:
    """Immutable tenant authority carried explicitly through one request."""

    tenant_id: TenantId
    actor_id: str | None = None
    role: str | None = None
    service_identity: str | None = None
    correlation_id: str | None = None
    identity_verified: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.tenant_id, TenantId):
            raise TypeError("tenant_id must be a TenantId")
        for field_name in ("actor_id", "role", "service_identity", "correlation_id"):
            value = getattr(self, field_name)
            if value is None:
                continue
            if not isinstance(value, str):
                raise TypeError(f"{field_name} must be a string or None")
            normalized = value.strip()
            object.__setattr__(self, field_name, normalized or None)

    @property
    def tenant_id_text(self) -> str:
        """Return the canonical identifier for persistence and contracts."""

        return self.tenant_id.value
