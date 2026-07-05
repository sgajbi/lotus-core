from __future__ import annotations

import logging
from datetime import UTC, date, datetime

from portfolio_common.config import DEFAULT_BUSINESS_CALENDAR_CODE
from portfolio_common.database_models import BusinessDate
from portfolio_common.db import SessionLocal
from sqlalchemy import func, select

from ..dtos.capabilities_dto import (
    ConsumerSystem,
    IntegrationCapabilitiesResponse,
)
from ..settings import load_query_service_settings
from .capability_policy import (
    CapabilitiesResponseAssembler,
    CapabilityCatalog,
    CapabilityPolicyResolver,
    CapabilityPolicySource,
    EnvironmentCapabilityPolicySource,
)

logger = logging.getLogger(__name__)


class CapabilitiesService:
    def __init__(
        self,
        *,
        policy_source: CapabilityPolicySource | None = None,
        catalog: CapabilityCatalog | None = None,
        resolver: CapabilityPolicyResolver | None = None,
        assembler: CapabilitiesResponseAssembler | None = None,
    ) -> None:
        self._catalog = catalog or CapabilityCatalog()
        self._policy_source = policy_source or EnvironmentCapabilityPolicySource(self._catalog)
        self._resolver = resolver or CapabilityPolicyResolver(self._catalog)
        self._assembler = assembler or CapabilitiesResponseAssembler(self._catalog)

    @staticmethod
    def _resolve_as_of_date() -> date:
        if not load_query_service_settings().has_database_url:
            return datetime.now(UTC).date()
        try:
            with SessionLocal() as db:
                stmt = select(func.max(BusinessDate.date)).where(
                    BusinessDate.calendar_code == DEFAULT_BUSINESS_CALENDAR_CODE
                )
                latest = db.execute(stmt).scalar_one_or_none()
                if isinstance(latest, date):
                    return latest
        except Exception:
            logger.warning(
                "Failed to resolve as_of_date from business_dates; "
                "falling back to current UTC date.",
                exc_info=True,
            )
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
