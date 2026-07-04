from pathlib import Path

from scripts.ingestion_service_framework_guard import (
    find_ingestion_service_framework_findings,
)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_ingestion_service_framework_guard_allows_plain_business_modules(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path / "src/services/ingestion_service/app/adapter_mode.py",
        "class AdapterModeDisabledError(RuntimeError): pass\n",
    )
    _write(
        tmp_path / "src/services/ingestion_service/app/services/upload_ingestion_service.py",
        "class UploadIngestionService: pass\n",
    )

    assert find_ingestion_service_framework_findings(tmp_path) == []


def test_ingestion_service_framework_guard_rejects_fastapi_coupling(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path / "src/services/ingestion_service/app/adapter_mode.py",
        "from fastapi import HTTPException, status\nraise HTTPException(status.HTTP_410_GONE)\n",
    )
    _write(
        tmp_path / "src/services/ingestion_service/app/services/ingestion_service.py",
        "from fastapi import Depends\ndef provider(dep=Depends(object)): pass\n",
    )

    findings = find_ingestion_service_framework_findings(tmp_path)

    assert [finding.snippet for finding in findings] == [
        "from fastapi import",
        "HTTPException",
        "status.HTTP",
        "from fastapi import",
        "Depends(",
    ]
