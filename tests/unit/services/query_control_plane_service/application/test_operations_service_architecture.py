from pathlib import Path


def test_load_run_progress_builder_uses_shared_valuation_runtime_settings_module():
    builder_source = Path(
        "src/services/query_control_plane_service/app/application/operations/load_run_progress.py"
    ).read_text(encoding="utf-8")
    service_source = Path(
        "src/services/query_control_plane_service/app/application/operations/service.py"
    ).read_text(encoding="utf-8")

    assert "portfolio_common.valuation_runtime_settings" in builder_source
    assert "src.services.valuation_orchestrator_service.app.settings" not in service_source
    assert "src.services.valuation_orchestrator_service.app.settings" not in builder_source


def test_operations_application_depends_on_port_not_sqlalchemy_adapter():
    service_source = Path(
        "src/services/query_control_plane_service/app/application/operations/service.py"
    ).read_text(encoding="utf-8")

    assert "ports.operations import OperationsSupportRepository" in service_source
    assert "sqlalchemy" not in service_source
    assert "infrastructure.operations" not in service_source
    assert "OperationsRepository(" not in service_source
