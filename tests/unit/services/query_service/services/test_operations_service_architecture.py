from pathlib import Path


def test_load_run_progress_builder_uses_shared_valuation_runtime_settings_module():
    builder_source = Path(
        "src/services/query_service/app/services/load_run_progress_builder.py"
    ).read_text(encoding="utf-8")
    service_source = Path(
        "src/services/query_service/app/services/operations_service.py"
    ).read_text(encoding="utf-8")

    assert "portfolio_common.valuation_runtime_settings" in builder_source
    assert "src.services.valuation_orchestrator_service.app.settings" not in service_source
    assert "src.services.valuation_orchestrator_service.app.settings" not in builder_source
