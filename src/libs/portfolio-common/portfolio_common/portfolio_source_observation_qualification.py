"""Server-owned submission grants; no provider is institutionally qualified here."""

from dataclasses import dataclass
from typing import Protocol

from .domain.portfolio_source_observations import (
    ObservationConflict,
    ObservationFamily,
    require_observation_identity,
)
from .domain.tenant import TenantContext


@dataclass(frozen=True, slots=True)
class ProducerSubmissionGrant:
    """Injected server configuration, never deserialized from a request payload."""

    tenant_id: str
    portfolio_id: str
    producer_id: str
    family: ObservationFamily

    def __post_init__(self) -> None:
        for name in ("tenant_id", "portfolio_id", "producer_id"):
            require_observation_identity(getattr(self, name), name)
        if not isinstance(self.family, ObservationFamily):
            raise ValueError("producer submission grant requires a typed family")


@dataclass(frozen=True, slots=True)
class UnqualifiedProducerAdmission:
    """Permission to retain an assertion is explicitly not bank authority."""

    grant: ProducerSubmissionGrant

    @property
    def qualification(self) -> str:
        return "unqualified"

    @property
    def policy_version(self) -> str:
        return "portfolio-source-observation-admission.v1"


class ProducerObservationAuthority(Protocol):
    def admit(
        self, context: TenantContext, grant: ProducerSubmissionGrant
    ) -> UnqualifiedProducerAdmission: ...


@dataclass(frozen=True, slots=True)
class UnqualifiedProducerAuthority:
    """Empty deployed default. Explicit injected synthetic grants cannot qualify facts."""

    grants: tuple[ProducerSubmissionGrant, ...] = ()

    def __post_init__(self) -> None:
        if type(self.grants) is not tuple or any(
            not isinstance(grant, ProducerSubmissionGrant) for grant in self.grants
        ):
            raise ValueError("producer grants must be an immutable typed configuration")
        if len(set(self.grants)) != len(self.grants):
            raise ValueError("duplicate producer submission grant")

    def admit(
        self, context: TenantContext, grant: ProducerSubmissionGrant
    ) -> UnqualifiedProducerAdmission:
        if (
            not context.identity_verified
            or context.tenant_id_text != grant.tenant_id
            or context.service_identity != grant.producer_id
            or grant not in self.grants
        ):
            raise ObservationConflict("SOURCE_OBSERVATION_PRODUCER_NOT_ADMITTED")
        return UnqualifiedProducerAdmission(grant)
