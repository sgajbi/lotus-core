import importlib

import portfolio_common.db as db_module
import sqlalchemy
import sqlalchemy.ext.asyncio as sa_async

import src.services.query_service.app.services.capabilities_service as capabilities_module
from src.services.query_service.app.services.capabilities_service import CapabilitiesService


def test_capabilities_default_flags(monkeypatch):
    monkeypatch.delenv("LOTUS_CORE_INGEST_UPLOAD_APIS_ENABLED", raising=False)
    monkeypatch.delenv("LOTUS_CORE_INGEST_PORTFOLIO_BUNDLE_ENABLED", raising=False)
    monkeypatch.delenv("LOTUS_CORE_PORTFOLIO_SUPPORTABILITY_ENABLED", raising=False)
    monkeypatch.delenv("LOTUS_CORE_POLICY_VERSION", raising=False)
    monkeypatch.delenv("LOTUS_CORE_CAPABILITY_TENANT_OVERRIDES_JSON", raising=False)

    service = CapabilitiesService()
    response = service.get_integration_capabilities(
        consumer_system="lotus-gateway", tenant_id="default"
    )

    assert response.contract_version == "v1"
    assert response.consumer_system == "lotus-gateway"
    assert response.policy_version == "tenant-default-v1"
    assert set(response.supported_input_modes) == {
        "lotus_core_ref",
        "inline_bundle",
        "file_upload",
    }
    assert all(feature.enabled for feature in response.features[:2])
    feature_map = {feature.key: feature.enabled for feature in response.features}
    assert feature_map["core.observability.portfolio_supportability"] is True


def test_capabilities_env_override(monkeypatch):
    monkeypatch.setenv("LOTUS_CORE_INGEST_UPLOAD_APIS_ENABLED", "false")
    monkeypatch.setenv("LOTUS_CORE_INGEST_PORTFOLIO_BUNDLE_ENABLED", "false")
    monkeypatch.setenv("LOTUS_CORE_PORTFOLIO_SUPPORTABILITY_ENABLED", "false")
    monkeypatch.setenv("LOTUS_CORE_POLICY_VERSION", "tenant-x-v3")
    monkeypatch.delenv("LOTUS_CORE_CAPABILITY_TENANT_OVERRIDES_JSON", raising=False)

    service = CapabilitiesService()
    response = service.get_integration_capabilities(
        consumer_system="lotus-manage", tenant_id="tenant-x"
    )

    feature_map = {feature.key: feature.enabled for feature in response.features}
    assert feature_map["lotus_core.ingestion.bulk_upload_adapter"] is False
    assert feature_map["lotus_core.ingestion.portfolio_bundle_adapter"] is False
    assert feature_map["core.observability.portfolio_supportability"] is False
    assert response.policy_version == "tenant-x-v3"
    assert set(response.supported_input_modes) == {"lotus_core_ref"}
    assert response.tenant_id == "tenant-x"


def test_capabilities_tenant_policy_override(monkeypatch):
    monkeypatch.setenv(
        "LOTUS_CORE_CAPABILITY_TENANT_OVERRIDES_JSON",
        (
            '{"tenant-a":{"policy_version":"tenant-a-v7",'
            '"features":{"lotus_core.ingestion.bulk_upload_adapter":false,'
            '"lotus_core.ingestion.portfolio_bundle_adapter":false,'
            '"lotus_core.support.lineage_api":false},'
            '"workflows":{"portfolio_bulk_onboarding":false},'
            '"supported_input_modes":{"lotus-manage":["lotus_core_ref"],"default":["lotus_core_ref"]}}}'
        ),
    )
    monkeypatch.setenv("LOTUS_CORE_INGEST_UPLOAD_APIS_ENABLED", "true")
    monkeypatch.setenv("LOTUS_CORE_INGEST_PORTFOLIO_BUNDLE_ENABLED", "true")

    service = CapabilitiesService()
    response = service.get_integration_capabilities(
        consumer_system="lotus-manage", tenant_id="tenant-a"
    )
    feature_map = {feature.key: feature.enabled for feature in response.features}
    workflow_map = {workflow.workflow_key: workflow.enabled for workflow in response.workflows}

    assert response.policy_version == "tenant-a-v7"
    assert response.supported_input_modes == ["lotus_core_ref"]
    assert feature_map["lotus_core.ingestion.bulk_upload_adapter"] is False
    assert feature_map["lotus_core.ingestion.portfolio_bundle_adapter"] is False
    assert feature_map["lotus_core.support.lineage_api"] is False
    assert workflow_map["portfolio_bulk_onboarding"] is False


def test_capabilities_ignores_invalid_tenant_policy_json(monkeypatch):
    monkeypatch.setenv("LOTUS_CORE_CAPABILITY_TENANT_OVERRIDES_JSON", "not-json")

    service = CapabilitiesService()
    response = service.get_integration_capabilities(
        consumer_system="lotus-gateway", tenant_id="tenant-a"
    )

    assert response.policy_version == "tenant-default-v1"
    assert set(response.supported_input_modes) == {
        "lotus_core_ref",
        "inline_bundle",
        "file_upload",
    }


def test_capabilities_ignores_non_object_overrides_payload(monkeypatch):
    monkeypatch.setenv("LOTUS_CORE_CAPABILITY_TENANT_OVERRIDES_JSON", '["invalid"]')
    service = CapabilitiesService()

    response = service.get_integration_capabilities(
        consumer_system="lotus-manage", tenant_id="tenant-a"
    )

    assert response.policy_version == "tenant-default-v1"
    assert response.supported_input_modes == ["lotus_core_ref"]


def test_capabilities_ignores_invalid_tenant_entries_and_non_dict_workflow_override(monkeypatch):
    monkeypatch.setenv(
        "LOTUS_CORE_CAPABILITY_TENANT_OVERRIDES_JSON",
        ('{"tenant-x":{"workflows":["invalid"],"policy_version":"tenant-x-v1"},"tenant-y":"bad"}'),
    )
    service = CapabilitiesService()
    response = service.get_integration_capabilities(
        consumer_system="lotus-manage", tenant_id="tenant-x"
    )

    workflow_map = {workflow.workflow_key: workflow.enabled for workflow in response.workflows}
    assert response.policy_version == "tenant-x-v1"
    assert workflow_map["portfolio_bulk_onboarding"] is True


def test_capabilities_workflow_required_features_are_canonical() -> None:
    service = CapabilitiesService()
    response = service.get_integration_capabilities(
        consumer_system="lotus-gateway",
        tenant_id="default",
    )

    feature_keys = {feature.key for feature in response.features}
    for workflow in response.workflows:
        assert workflow.required_features
        assert set(workflow.required_features).issubset(feature_keys)


def test_capabilities_includes_ecosystem_consumers() -> None:
    service = CapabilitiesService()

    response = service.get_integration_capabilities(
        consumer_system="lotus-workbench",
        tenant_id="tenant_sg_pb",
    )

    assert response.consumer_system == "lotus-workbench"
    assert response.supported_input_modes == ["lotus_core_ref"]
    workflow_map = {
        workflow.workflow_key: workflow.required_features for workflow in response.workflows
    }
    assert (
        "core.observability.portfolio_supportability" in workflow_map["advisor_workbench_overview"]
    )


def test_resolve_as_of_date_uses_latest_business_date_from_db(monkeypatch):
    class _MockResult:
        @staticmethod
        def scalar_one_or_none():
            from datetime import date

            return date(2026, 2, 27)

    class _MockSession:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        @staticmethod
        def execute(_stmt):
            return _MockResult()

    monkeypatch.setenv("DATABASE_URL", "postgresql://dummy")
    monkeypatch.setattr(
        "src.services.query_service.app.services.capabilities_service.SessionLocal",
        lambda: _MockSession(),
    )

    assert CapabilitiesService._resolve_as_of_date().isoformat() == "2026-02-27"


def test_resolve_as_of_date_falls_back_when_db_access_fails(monkeypatch):
    class _FailSession:
        def __enter__(self):
            raise RuntimeError("db not available")

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setenv("DATABASE_URL", "postgresql://dummy")
    monkeypatch.setattr(
        "src.services.query_service.app.services.capabilities_service.SessionLocal",
        lambda: _FailSession(),
    )

    resolved = CapabilitiesService._resolve_as_of_date()
    assert resolved.isoformat() >= "2026-01-01"


def test_capabilities_service_import_does_not_create_db_engines(monkeypatch):
    sync_calls = []
    async_calls = []

    monkeypatch.setattr(
        sqlalchemy,
        "create_engine",
        lambda *args, **kwargs: sync_calls.append((args, kwargs)) or object(),
    )
    monkeypatch.setattr(
        sa_async,
        "create_async_engine",
        lambda *args, **kwargs: async_calls.append((args, kwargs)) or object(),
    )

    importlib.reload(db_module)
    importlib.reload(capabilities_module)

    assert db_module._engine is None
    assert db_module._async_engine is None
    assert sync_calls == []
    assert async_calls == []
