"""Serve policy-resolved integration capabilities from the control plane."""

from __future__ import annotations

from datetime import UTC, date, datetime

from ..contracts.capabilities import (
    ConsumerSystem,
    IntegrationCapabilitiesResponse,
)
from ..ports import BusinessDateProvider
from .capability_policy import (
    CapabilitiesResponseAssembler,
    CapabilityCatalog,
    CapabilityPolicyResolver,
    CapabilityPolicySource,
    EnvironmentCapabilityPolicySource,
)


class CapabilitiesService:
    def __init__(
        self,
        *,
        policy_source: CapabilityPolicySource | None = None,
        catalog: CapabilityCatalog | None = None,
        resolver: CapabilityPolicyResolver | None = None,
        assembler: CapabilitiesResponseAssembler | None = None,
        business_dates: BusinessDateProvider | None = None,
    ) -> None:
        self._catalog = catalog or CapabilityCatalog()
        self._policy_source = policy_source or EnvironmentCapabilityPolicySource(self._catalog)
        self._resolver = resolver or CapabilityPolicyResolver(self._catalog)
        self._assembler = assembler or CapabilitiesResponseAssembler(self._catalog)
        self._business_dates = business_dates

    def _resolve_as_of_date(self) -> date:
        if self._business_dates is not None:
            latest = self._business_dates.latest_business_date()
            if latest is not None:
                return latest
        return datetime.now(UTC).date()

    def get_integration_capabilities(
        self,
        consumer_system: ConsumerSystem,
        tenant_id: str,
    ) -> IntegrationCapabilitiesResponse:
        inputs = self._policy_source.load_policy_inputs()
        policy = self._resolver.resolve(consumer_system, tenant_id, inputs)

        return self._assembler.assemble(
            consumer_system=consumer_system,
            tenant_id=tenant_id,
            generated_at=datetime.now(UTC),
            as_of_date=self._resolve_as_of_date(),
            policy=policy,
        )
