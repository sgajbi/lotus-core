"""Server-owned submission grants; no provider is institutionally qualified here."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Protocol

from .domain.portfolio_source_observations import (
    ObservationConflict,
    ObservationFamily,
    require_observation_identity,
)
from .domain.tenant import TenantContext


def parse_submission_grants(value: str) -> tuple[ProducerSubmissionGrant, ...]:
    """Bounded public configuration; caller authentication remains independent."""
    if value == "":
        return ()
    if len(value.encode("utf-8")) > 65536:
        raise ValueError("producer grant configuration exceeds limit")

    def unique_object(pairs):
        result = {}
        for key, item in pairs:
            if key in result:
                raise ValueError("duplicate grant field")
            result[key] = item
        return result

    records = json.loads(value, object_pairs_hook=unique_object)
    if type(records) is not list or len(records) > 100:
        raise ValueError("producer grants require a bounded list")
    grants = []
    for record in records:
        if type(record) is not dict or set(record) != {
            "tenant_id",
            "portfolio_id",
            "producer_id",
            "family",
        }:
            raise ValueError("producer grant fields must be explicit")
        if any(type(item) is not str or "*" in item for item in record.values()):
            raise ValueError("producer grant wildcard or untyped scope")
        grants.append(
            ProducerSubmissionGrant(
                record["tenant_id"],
                record["portfolio_id"],
                record["producer_id"],
                ObservationFamily(record["family"]),
            )
        )
    result = tuple(grants)
    UnqualifiedProducerAuthority(result)
    return result


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
