from pathlib import Path


def test_operations_service_uses_shared_valuation_runtime_settings_module():
    service_source = Path(
        "src/services/query_service/app/services/operations_service.py"
    ).read_text(encoding="utf-8")

    assert "portfolio_common.valuation_runtime_settings" in service_source
    assert "src.services.valuation_orchestrator_service.app.settings" not in service_source
