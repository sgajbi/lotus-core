from pathlib import Path

from scripts.application_error_taxonomy_guard import (
    find_application_error_taxonomy_findings,
)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_application_error_taxonomy_guard_allows_application_errors(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path / "src/services/ingestion_service/app/application/errors.py",
        "class ApplicationError(Exception): pass\n"
        "class ValidationRejected(ApplicationError): pass\n"
        "class UnsupportedOperation(ApplicationError): pass\n",
    )
    _write(
        tmp_path / "src/services/ingestion_service/app/services/upload_ingestion_service.py",
        "from ..application.errors import UnsupportedOperation, ValidationRejected\n"
        "raise UnsupportedOperation(reason_code='unsupported', detail='bad')\n"
        "raise ValidationRejected(reason_code='invalid', detail='bad')\n",
    )

    assert find_application_error_taxonomy_findings(tmp_path) == []


def test_application_error_taxonomy_guard_rejects_http_exceptions(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path / "src/services/ingestion_service/app/application/errors.py",
        "class ApplicationError(Exception): pass\n"
        "class ValidationRejected(ApplicationError): pass\n"
        "class UnsupportedOperation(ApplicationError): pass\n",
    )
    _write(
        tmp_path / "src/services/ingestion_service/app/services/upload_ingestion_service.py",
        "from fastapi import HTTPException, status\n"
        "raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='bad')\n",
    )

    findings = find_application_error_taxonomy_findings(tmp_path)

    assert [finding.snippet for finding in findings] == [
        "ValidationRejected",
        "UnsupportedOperation",
        "HTTPException",
        "status.HTTP_",
        "from fastapi",
    ]


def test_application_error_taxonomy_guard_rejects_missing_taxonomy_symbol(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path / "src/services/ingestion_service/app/application/errors.py",
        "class ApplicationError(Exception): pass\n"
        "class ValidationRejected(ApplicationError): pass\n",
    )
    _write(
        tmp_path / "src/services/ingestion_service/app/services/upload_ingestion_service.py",
        "from ..application.errors import UnsupportedOperation, ValidationRejected\n",
    )

    findings = find_application_error_taxonomy_findings(tmp_path)

    assert findings[0].path == "src/services/ingestion_service/app/application/errors.py"
    assert findings[0].snippet == "class UnsupportedOperation"
