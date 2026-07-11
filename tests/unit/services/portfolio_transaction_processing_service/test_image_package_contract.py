from __future__ import annotations

import tomllib
from pathlib import Path

SERVICE_ROOT = (
    Path(__file__).resolve().parents[4] / "src/services/portfolio_transaction_processing_service"
)


def test_target_package_declares_one_bounded_runtime_distribution() -> None:
    project = tomllib.loads((SERVICE_ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert project["project"]["name"] == "portfolio-transaction-processing-service"
    assert set(project["project"]["dependencies"]) == {
        "portfolio-common==0.1.0",
        "fastapi==0.136.3",
        "prometheus-fastapi-instrumentator==8.0.0",
        "uvicorn[standard]==0.49.0",
    }
    assert project["tool"]["setuptools"]["packages"]["find"] == {
        "where": ["."],
        "include": ["app", "app.*"],
    }


def test_target_image_uses_bounded_source_closure_without_legacy_wheel_collisions() -> None:
    dockerfile = (SERVICE_ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "COPY src /app/src" not in dockerfile
    assert "cost_calculator_service/pyproject.toml" not in dockerfile
    assert "cashflow_calculator_service/pyproject.toml" not in dockerfile
    assert "position_calculator/pyproject.toml" not in dockerfile
    for module_root in (
        "cost_calculator_service",
        "cashflow_calculator_service",
        "position_calculator",
    ):
        assert f"src/services/calculators/{module_root} " in dockerfile
        assert f"/app/src/services/calculators/{module_root}" in dockerfile
    assert (
        "COPY --chown=appuser:appuser src/services/pipeline_orchestrator_service/app "
        not in dockerfile
    )
    for pipeline_module in (
        "adapters/outbox_event_mapper.py",
        "adapters/pipeline_event_factory.py",
        "domain/pipeline_stage_state_machine.py",
        "repositories/pipeline_stage_repository.py",
        "services/pipeline_orchestrator_service.py",
    ):
        assert f"src/services/pipeline_orchestrator_service/app/{pipeline_module}" in dockerfile
    assert (
        'RUN python -c "import app.main; import app.infrastructure.sqlalchemy_unit_of_work"'
        in dockerfile
    )
    install_command = (
        "pip install --no-index --find-links=/wheels portfolio-transaction-processing-service"
    )
    assert install_command in dockerfile
    assert 'USER appuser\nEXPOSE 8085\nCMD ["python", "-m", "app.main"]' in dockerfile
