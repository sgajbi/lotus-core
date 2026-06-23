from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any, cast

from portfolio_common.config import DEFAULT_BUSINESS_CALENDAR_CODE
from portfolio_common.database_models import BusinessDate
from portfolio_common.db import SessionLocal
from sqlalchemy import func, select

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

_INGESTION_INPUT_MODE_BY_FEATURE: dict[str, str] = {
    "lotus_core.ingestion.portfolio_bundle_adapter": "inline_bundle",
    "lotus_core.ingestion.bulk_upload_adapter": "file_upload",
}

_FEATURE_DESCRIPTIONS: dict[str, str] = {
    "lotus_core.support.overview_api": "Support diagnostics and operational support APIs.",
    "lotus_core.support.lineage_api": "Lineage and epoch/watermark traceability APIs.",
    "core.observability.portfolio_supportability": (
        "Portfolio supportability summary on readiness responses for "
        "Gateway, Workbench, and downstream app health composition."
    ),
    "lotus_core.ingestion.bulk_upload_adapter": (
        "CSV/XLSX preview+commit adapter endpoints for onboarding workflows."
    ),
    "lotus_core.ingestion.portfolio_bundle_adapter": (
        "Portfolio bundle adapter endpoint for UI/manual onboarding workflows."
    ),
    "lotus_core.simulation.what_if": "Sandbox what-if simulation session APIs.",
}

_DEFAULT_INPUT_MODES_BY_CONSUMER: dict[str, list[str]] = {
    "lotus-advise": ["lotus_core_ref"],
    "lotus-idea": ["lotus_core_ref"],
    "lotus-performance": ["lotus_core_ref"],
    "lotus-manage": ["lotus_core_ref"],
    "lotus-report": ["lotus_core_ref"],
    "lotus-risk": ["lotus_core_ref"],
    "lotus-workbench": ["lotus_core_ref"],
    "lotus-gateway": ["lotus_core_ref", "inline_bundle", "file_upload"],
    "UI": ["lotus_core_ref", "inline_bundle", "file_upload"],
    "UNKNOWN": ["lotus_core_ref"],
}


@dataclass(frozen=True)
class _ResolvedCapabilityPolicy:
    feature_states: dict[str, bool]
    policy_version: str
    supported_input_modes: list[str]
    workflow_overrides: dict[str, bool]


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
                if isinstance(latest, date):
                    return latest
        except Exception:
            logger.warning(
                "Failed to resolve as_of_date from business_dates; "
                "falling back to current UTC date.",
                exc_info=True,
            )
        return datetime.now(UTC).date()

    @staticmethod
    def _env_bool(name: str, default: bool) -> bool:
        return cast(bool, env_bool(name, default))

    @staticmethod
    def _decode_tenant_overrides_payload(raw: str) -> Any | None:
        try:
            decoded = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning(
                "Invalid LOTUS_CORE_CAPABILITY_TENANT_OVERRIDES_JSON; ignoring tenant overrides.",
            )
            return None

        if not isinstance(decoded, dict):
            logger.warning(
                "LOTUS_CORE_CAPABILITY_TENANT_OVERRIDES_JSON must be a JSON object; "
                "ignoring tenant overrides.",
            )
            return None
        return decoded

    @staticmethod
    def _normalized_tenant_overrides(decoded: dict[Any, Any]) -> dict[str, dict[str, Any]]:
        normalized: dict[str, dict[str, Any]] = {}
        for tenant_id, policy in decoded.items():
            if not isinstance(tenant_id, str) or not isinstance(policy, dict):
                continue
            normalized[tenant_id] = policy
        return normalized

    def _load_tenant_overrides(self) -> dict[str, dict[str, Any]]:
        raw = load_query_service_settings().capability_tenant_overrides_json
        if not raw:
            return {}
        decoded = self._decode_tenant_overrides_payload(raw)
        return self._normalized_tenant_overrides(decoded) if decoded is not None else {}

    def _default_feature_states(self) -> dict[str, bool]:
        return {
            key: self._env_bool(env_name, default)
            for key, (env_name, default) in _FEATURE_ENV_DEFAULTS.items()
        }

    @staticmethod
    def _default_input_modes(consumer_system: ConsumerSystem) -> list[str]:
        return list(_DEFAULT_INPUT_MODES_BY_CONSUMER.get(consumer_system, ["lotus_core_ref"]))

    @staticmethod
    def _prune_disabled_ingestion_modes(
        supported_input_modes: list[str],
        feature_states: dict[str, bool],
    ) -> list[str]:
        disabled_modes = {
            input_mode
            for feature_key, input_mode in _INGESTION_INPUT_MODE_BY_FEATURE.items()
            if not feature_states[feature_key]
        }
        return [mode for mode in supported_input_modes if mode not in disabled_modes]

    @staticmethod
    def _feature_overrides(tenant_policy: dict[str, Any]) -> dict[str, bool]:
        feature_overrides = tenant_policy.get("features", {})
        if not isinstance(feature_overrides, dict):
            return {}
        return {
            key: value
            for key, value in feature_overrides.items()
            if key in _FEATURE_ENV_DEFAULTS and isinstance(value, bool)
        }

    @staticmethod
    def _workflow_overrides(tenant_policy: dict[str, Any]) -> dict[str, bool]:
        workflow_overrides = tenant_policy.get("workflows", {})
        if not isinstance(workflow_overrides, dict):
            return {}
        return {
            key: value
            for key, value in workflow_overrides.items()
            if key in _WORKFLOW_DEPENDENCIES and isinstance(value, bool)
        }

    @staticmethod
    def _policy_version(default_policy_version: str, tenant_policy: dict[str, Any]) -> str:
        tenant_policy_version = tenant_policy.get("policy_version")
        if isinstance(tenant_policy_version, str) and tenant_policy_version.strip():
            return tenant_policy_version.strip()
        return default_policy_version

    @staticmethod
    def _tenant_input_modes(
        consumer_system: ConsumerSystem,
        tenant_policy: dict[str, Any],
    ) -> list[str] | None:
        input_modes = tenant_policy.get("supported_input_modes", {})
        if not isinstance(input_modes, dict):
            return None

        mode_source = CapabilitiesService._input_mode_source_for_consumer(
            consumer_system,
            input_modes,
        )
        if not isinstance(mode_source, list):
            return None
        return CapabilitiesService._normalized_input_modes(mode_source)

    @staticmethod
    def _input_mode_source_for_consumer(
        consumer_system: ConsumerSystem,
        input_modes: dict[Any, Any],
    ) -> Any:
        consumer_modes = input_modes.get(consumer_system)
        if isinstance(consumer_modes, list):
            return consumer_modes
        return input_modes.get("default")

    @staticmethod
    def _normalized_input_modes(mode_source: list[Any]) -> list[str] | None:
        normalized_modes = [mode for mode in mode_source if isinstance(mode, str) and mode.strip()]
        return normalized_modes or None

    def _resolve_capability_policy(
        self,
        consumer_system: ConsumerSystem,
        tenant_id: str,
    ) -> _ResolvedCapabilityPolicy:
        feature_states = self._default_feature_states()
        policy_version = load_query_service_settings().lotus_core_policy_version
        supported_input_modes = self._prune_disabled_ingestion_modes(
            self._default_input_modes(consumer_system),
            feature_states,
        )
        workflow_overrides: dict[str, bool] = {}

        tenant_policy = self._load_tenant_overrides().get(tenant_id)
        if tenant_policy:
            feature_states.update(self._feature_overrides(tenant_policy))
            workflow_overrides = self._workflow_overrides(tenant_policy)
            policy_version = self._policy_version(policy_version, tenant_policy)
            supported_input_modes = (
                self._tenant_input_modes(consumer_system, tenant_policy) or supported_input_modes
            )

        return _ResolvedCapabilityPolicy(
            feature_states=feature_states,
            policy_version=policy_version,
            supported_input_modes=supported_input_modes,
            workflow_overrides=workflow_overrides,
        )

    @staticmethod
    def _feature_capabilities(feature_states: dict[str, bool]) -> list[FeatureCapability]:
        return [
            FeatureCapability(
                key=key,
                enabled=feature_states[key],
                owner_service="lotus-core",
                description=description,
            )
            for key, description in _FEATURE_DESCRIPTIONS.items()
        ]

    @staticmethod
    def _workflow_enabled(
        workflow_key: str,
        feature_states: dict[str, bool],
        workflow_overrides: dict[str, bool],
    ) -> bool:
        if workflow_key in workflow_overrides:
            return workflow_overrides[workflow_key]
        return all(feature_states[key] for key in _WORKFLOW_DEPENDENCIES[workflow_key])

    def _workflow_capabilities(
        self,
        feature_states: dict[str, bool],
        workflow_overrides: dict[str, bool],
    ) -> list[WorkflowCapability]:
        return [
            WorkflowCapability(
                workflow_key=workflow_key,
                enabled=self._workflow_enabled(
                    workflow_key,
                    feature_states,
                    workflow_overrides,
                ),
                required_features=list(required_features),
            )
            for workflow_key, required_features in _WORKFLOW_DEPENDENCIES.items()
        ]

    def get_integration_capabilities(
        self,
        consumer_system: ConsumerSystem,
        tenant_id: str,
    ) -> IntegrationCapabilitiesResponse:
        policy = self._resolve_capability_policy(consumer_system, tenant_id)

        return IntegrationCapabilitiesResponse(
            contract_version="v1",
            source_service="lotus-core",
            consumer_system=consumer_system,
            tenant_id=tenant_id,
            generated_at=datetime.now(UTC),
            as_of_date=self._resolve_as_of_date(),
            policy_version=policy.policy_version,
            supported_input_modes=policy.supported_input_modes,
            features=self._feature_capabilities(policy.feature_states),
            workflows=self._workflow_capabilities(
                policy.feature_states,
                policy.workflow_overrides,
            ),
        )
