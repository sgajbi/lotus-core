from __future__ import annotations

import json
import logging
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import func, select

from portfolio_common.config import DEFAULT_BUSINESS_CALENDAR_CODE
from portfolio_common.database_models import BusinessDate
from portfolio_common.db import SessionLocal

from ..dtos.capabilities_dto import (
    ConsumerSystem,
    FeatureCapability,
    IntegrationCapabilitiesResponse,
    WorkflowCapability,
)
from ..settings import env_bool, load_query_service_settings


logger = logging.getLogger(__name__)


_FEATURE_ENV_DEFAULTS: dict[str, tuple[str, bool]] = {
    "lotus_core.support.overview_api": ("LOTUS_CORE_CAP_SUPPORT_APIS_ENABLED", True),
    "lotus_core.support.lineage_api": ("LOTUS_CORE_CAP_LINEAGE_APIS_ENABLED", True),
    "core.observability.portfolio_supportability": (
        "LOTUS_CORE_PORTFOLIO_SUPPORTABILITY_ENABLED",
        True,
    ),
    "lotus_core.ingestion.bulk_upload_adapter": ("LOTUS_CORE_INGEST_UPLOAD_APIS_ENABLED", True),
    "lotus_core.ingestion.portfolio_bundle_adapter": (
        "LOTUS_CORE_INGEST_PORTFOLIO_BUNDLE_ENABLED",
        True,
    ),
    "lotus_core.simulation.what_if": ("LOTUS_CORE_CAP_SIMULATION_ENABLED", True),
}

_WORKFLOW_DEPENDENCIES: dict[str, list[str]] = {
    "advisor_workbench_overview": [
        "lotus_core.support.overview_api",
        "core.observability.portfolio_supportability",
    ],
    "portfolio_bulk_onboarding": [
        "lotus_core.ingestion.bulk_upload_adapter",
        "lotus_core.ingestion.portfolio_bundle_adapter",
    ],
    "portfolio_what_if_simulation": ["lotus_core.simulation.what_if"],
}

_DEFAULT_INPUT_MODES_BY_CONSUMER: dict[str, list[str]] = {
    "lotus-advise": ["lotus_core_ref"],
    "lotus-performance": ["lotus_core_ref"],
    "lotus-manage": ["lotus_core_ref"],
    "lotus-report": ["lotus_core_ref"],
    "lotus-risk": ["lotus_core_ref"],
    "lotus-workbench": ["lotus_core_ref"],
    "lotus-gateway": ["lotus_core_ref", "inline_bundle", "file_upload"],
    "UI": ["lotus_core_ref", "inline_bundle", "file_upload"],
    "UNKNOWN": ["lotus_core_ref"],
}


class CapabilitiesService:
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
                if latest:
                    return latest
        except Exception:
            logger.warning(
                "Failed to resolve as_of_date from business_dates; falling back to current UTC date.",
                exc_info=True,
            )
        return datetime.now(UTC).date()

    @staticmethod
    def _env_bool(name: str, default: bool) -> bool:
        return env_bool(name, default)

    @staticmethod
    def _load_tenant_overrides() -> dict[str, dict[str, Any]]:
        raw = load_query_service_settings().capability_tenant_overrides_json
        if not raw:
            return {}
        try:
            decoded = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning(
                "Invalid LOTUS_CORE_CAPABILITY_TENANT_OVERRIDES_JSON; ignoring tenant overrides.",
            )
            return {}

        if not isinstance(decoded, dict):
            logger.warning(
                "LOTUS_CORE_CAPABILITY_TENANT_OVERRIDES_JSON must be a JSON object; ignoring tenant overrides.",
            )
            return {}

        normalized: dict[str, dict[str, Any]] = {}
        for tenant_id, policy in decoded.items():
            if not isinstance(tenant_id, str) or not isinstance(policy, dict):
                continue
            normalized[tenant_id] = policy
        return normalized

    def get_integration_capabilities(
        self,
        consumer_system: ConsumerSystem,
        tenant_id: str,
    ) -> IntegrationCapabilitiesResponse:
        feature_states: dict[str, bool] = {
            key: self._env_bool(env_name, default)
            for key, (env_name, default) in _FEATURE_ENV_DEFAULTS.items()
        }
        policy_version = load_query_service_settings().lotus_core_policy_version
        supported_input_modes = list(
            _DEFAULT_INPUT_MODES_BY_CONSUMER.get(consumer_system, ["lotus_core_ref"])
        )
        if not feature_states["lotus_core.ingestion.portfolio_bundle_adapter"]:
            supported_input_modes = [
                mode for mode in supported_input_modes if mode != "inline_bundle"
            ]
        if not feature_states["lotus_core.ingestion.bulk_upload_adapter"]:
            supported_input_modes = [
                mode for mode in supported_input_modes if mode != "file_upload"
            ]

        tenant_policy = self._load_tenant_overrides().get(tenant_id)
        if tenant_policy:
            feature_overrides = tenant_policy.get("features", {})
            if isinstance(feature_overrides, dict):
                for key, value in feature_overrides.items():
                    if key in feature_states and isinstance(value, bool):
                        feature_states[key] = value

            workflow_overrides = tenant_policy.get("workflows", {})
            policy_workflow_overrides: dict[str, bool] = {}
            if isinstance(workflow_overrides, dict):
                for key, value in workflow_overrides.items():
                    if key in _WORKFLOW_DEPENDENCIES and isinstance(value, bool):
                        policy_workflow_overrides[key] = value
            else:
                policy_workflow_overrides = {}

            tenant_policy_version = tenant_policy.get("policy_version")
            if isinstance(tenant_policy_version, str) and tenant_policy_version.strip():
                policy_version = tenant_policy_version.strip()

            input_modes = tenant_policy.get("supported_input_modes", {})
            if isinstance(input_modes, dict):
                consumer_modes = input_modes.get(consumer_system)
                fallback_modes = input_modes.get("default")
                mode_source = consumer_modes if isinstance(consumer_modes, list) else fallback_modes
                if isinstance(mode_source, list):
                    normalized_modes = [
                        mode for mode in mode_source if isinstance(mode, str) and mode.strip()
                    ]
                    if normalized_modes:
                        supported_input_modes = normalized_modes
        else:
            policy_workflow_overrides = {}

        features = [
            FeatureCapability(
                key="lotus_core.support.overview_api",
                enabled=feature_states["lotus_core.support.overview_api"],
                owner_service="lotus-core",
                description="Support diagnostics and operational support APIs.",
            ),
            FeatureCapability(
                key="lotus_core.support.lineage_api",
                enabled=feature_states["lotus_core.support.lineage_api"],
                owner_service="lotus-core",
                description="Lineage and epoch/watermark traceability APIs.",
            ),
            FeatureCapability(
                key="core.observability.portfolio_supportability",
                enabled=feature_states["core.observability.portfolio_supportability"],
                owner_service="lotus-core",
                description=(
                    "Portfolio supportability summary on readiness responses for "
                    "Gateway, Workbench, and downstream app health composition."
                ),
            ),
            FeatureCapability(
                key="lotus_core.ingestion.bulk_upload_adapter",
                enabled=feature_states["lotus_core.ingestion.bulk_upload_adapter"],
                owner_service="lotus-core",
                description="CSV/XLSX preview+commit adapter endpoints for onboarding workflows.",
            ),
            FeatureCapability(
                key="lotus_core.ingestion.portfolio_bundle_adapter",
                enabled=feature_states["lotus_core.ingestion.portfolio_bundle_adapter"],
                owner_service="lotus-core",
                description="Portfolio bundle adapter endpoint for UI/manual onboarding workflows.",
            ),
            FeatureCapability(
                key="lotus_core.simulation.what_if",
                enabled=feature_states["lotus_core.simulation.what_if"],
                owner_service="lotus-core",
                description="Sandbox what-if simulation session APIs.",
            ),
        ]

        workflows = [
            WorkflowCapability(
                workflow_key="advisor_workbench_overview",
                enabled=policy_workflow_overrides.get(
                    "advisor_workbench_overview",
                    all(
                        feature_states[key]
                        for key in _WORKFLOW_DEPENDENCIES["advisor_workbench_overview"]
                    ),
                ),
                required_features=list(_WORKFLOW_DEPENDENCIES["advisor_workbench_overview"]),
            ),
            WorkflowCapability(
                workflow_key="portfolio_bulk_onboarding",
                enabled=policy_workflow_overrides.get(
                    "portfolio_bulk_onboarding",
                    all(
                        feature_states[key]
                        for key in _WORKFLOW_DEPENDENCIES["portfolio_bulk_onboarding"]
                    ),
                ),
                required_features=list(_WORKFLOW_DEPENDENCIES["portfolio_bulk_onboarding"]),
            ),
            WorkflowCapability(
                workflow_key="portfolio_what_if_simulation",
                enabled=policy_workflow_overrides.get(
                    "portfolio_what_if_simulation",
                    all(
                        feature_states[key]
                        for key in _WORKFLOW_DEPENDENCIES["portfolio_what_if_simulation"]
                    ),
                ),
                required_features=list(_WORKFLOW_DEPENDENCIES["portfolio_what_if_simulation"]),
            ),
        ]

        return IntegrationCapabilitiesResponse(
            contract_version="v1",
            source_service="lotus-core",
            consumer_system=consumer_system,
            tenant_id=tenant_id,
            generated_at=datetime.now(UTC),
            as_of_date=self._resolve_as_of_date(),
            policy_version=policy_version,
            supported_input_modes=supported_input_modes,
            features=features,
            workflows=workflows,
        )
