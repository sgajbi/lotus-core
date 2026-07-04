from pathlib import Path

from scripts.infrastructure_adapter_layer_guard import (
    find_infrastructure_adapter_layer_findings,
)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_infrastructure_adapter_layer_guard_allows_migrated_store_adapter(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path / "src/services/ingestion_service/app/infrastructure/__init__.py",
        "",
    )
    _write(
        tmp_path / "src/services/ingestion_service/app/infrastructure/workflow_stores.py",
        "class SqlAlchemyIngestionJobStore: pass\nclass SqlAlchemyReplayAuditStore: pass\n",
    )
    _write(
        tmp_path / "src/services/ingestion_service/app/adapters/ingestion_workflow_stores.py",
        "from ..infrastructure.workflow_stores import (\n"
        "    SqlAlchemyIngestionJobStore,\n"
        "    SqlAlchemyReplayAuditStore,\n"
        ")\n",
    )
    _write(
        tmp_path / "src/services/ingestion_service/app/services/ingestion_job_service.py",
        "from ..infrastructure.workflow_stores import SqlAlchemyIngestionJobStore\n",
    )

    assert find_infrastructure_adapter_layer_findings(tmp_path) == []


def test_infrastructure_adapter_layer_guard_rejects_transitional_adapter_regression(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path / "src/services/ingestion_service/app/infrastructure/__init__.py",
        "",
    )
    _write(
        tmp_path / "src/services/ingestion_service/app/infrastructure/workflow_stores.py",
        "class SqlAlchemyIngestionJobStore: pass\n",
    )
    _write(
        tmp_path / "src/services/ingestion_service/app/adapters/ingestion_workflow_stores.py",
        "class SqlAlchemyIngestionJobStore:\n"
        "    async def create(self):\n"
        "        await create_or_get_job_result()\n",
    )
    _write(
        tmp_path / "src/services/ingestion_service/app/services/ingestion_job_service.py",
        "from ..adapters.ingestion_workflow_stores import SqlAlchemyIngestionJobStore\n",
    )

    findings = find_infrastructure_adapter_layer_findings(tmp_path)

    assert [finding.snippet for finding in findings] == [
        "from ..adapters.ingestion_workflow_stores import",
        "<missing-re-export>",
        "class SqlAlchemyIngestionJobStore",
        "create_or_get_job_result(",
    ]


def test_infrastructure_adapter_layer_guard_rejects_missing_infrastructure_module(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path / "src/services/ingestion_service/app/infrastructure/__init__.py",
        "",
    )

    findings = find_infrastructure_adapter_layer_findings(tmp_path)

    assert findings[0].path == (
        "src/services/ingestion_service/app/infrastructure/workflow_stores.py"
    )
    assert findings[0].snippet == "<missing-file>"
