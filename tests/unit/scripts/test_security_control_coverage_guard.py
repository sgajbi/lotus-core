from __future__ import annotations

import json
from pathlib import Path

from scripts import security_control_coverage_guard as guard


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _minimal_contract(app_path: str) -> dict[str, object]:
    return {
        "schema_version": "security-control-coverage.v1",
        "apps": [
            {
                "service_name": "demo_service",
                "app_path": app_path,
                "app_kind": "business_api",
                "auth_audit_control": "enterprise_middleware",
                "payload_limit_control": "enterprise_middleware",
                "upload_limit_control": "not_applicable",
                "unauthenticated_allowlist": [
                    "/docs",
                    "/health/live",
                    "/health/ready",
                    "/metrics",
                    "/openapi.json",
                    "/redoc",
                    "/version",
                ],
            }
        ],
    }


def _write_minimal_guard_repo(tmp_path: Path, *, app_source: str) -> Path:
    app_path = "src/services/demo_service/app/main.py"
    _write(
        tmp_path / "contracts/security/security-control-coverage.v1.json",
        json.dumps(_minimal_contract(app_path)),
    )
    _write(
        tmp_path / "src/libs/portfolio-common/portfolio_common/http_app_bootstrap.py",
        "\n".join(
            [
                "def configure_secure_response_headers(): pass",
                "def configure_cors_policy(): pass",
                "def configure_trusted_host_policy(): pass",
                "def configure_metrics_access_policy(): pass",
                "def unhandled_exception_handler(): pass",
            ]
        ),
    )
    _write(
        tmp_path / "src/libs/portfolio-common/portfolio_common/enterprise_readiness.py",
        "\n".join(
            [
                "enterprise_max_write_payload_bytes = 1",
                "payload_too_large = 'payload_too_large'",
                "def build_enterprise_audit_middleware(): pass",
                "def validate_enterprise_runtime_config(): pass",
            ]
        ),
    )
    _write(
        tmp_path / "src/services/ingestion_service/app/routers/uploads.py",
        "_read_bounded_upload_content = None\nINGESTION_UPLOAD_TOO_LARGE = 'x'\n",
    )
    _write(
        tmp_path / "src/services/ingestion_service/app/settings.py",
        "LOTUS_CORE_INGEST_UPLOAD_MAX_BYTES = 'LOTUS_CORE_INGEST_UPLOAD_MAX_BYTES'\n",
    )
    _write(tmp_path / app_path, app_source)
    return tmp_path


def test_security_control_coverage_guard_accepts_current_truth() -> None:
    assert guard.evaluate_security_control_coverage() == []


def test_security_control_coverage_guard_accepts_service_local_enterprise_wrapper(
    tmp_path: Path,
) -> None:
    repo_root = _write_minimal_guard_repo(
        tmp_path,
        app_source=(
            "from fastapi import FastAPI\n"
            "app = FastAPI()\n"
            "build_ingestion_enterprise_audit_middleware()\n"
            "validate_enterprise_runtime_config()\n"
            "configure_standard_http_app()\n"
        ),
    )

    assert guard.evaluate_security_control_coverage(repo_root=repo_root) == []


def test_security_control_coverage_guard_rejects_unregistered_fastapi_app(tmp_path: Path) -> None:
    repo_root = _write_minimal_guard_repo(
        tmp_path,
        app_source=(
            "from fastapi import FastAPI\n"
            "app = FastAPI()\n"
            "build_enterprise_audit_middleware()\n"
            "validate_enterprise_runtime_config()\n"
            "configure_standard_http_app()\n"
        ),
    )
    _write(
        tmp_path / "src/services/new_service/app/main.py",
        "from fastapi import FastAPI\napp = FastAPI()\nconfigure_standard_http_app()\n",
    )

    findings = guard.evaluate_security_control_coverage(repo_root=repo_root)

    assert findings[0] == {"missing_from_contract": ["src/services/new_service/app/main.py"]}


def test_security_control_coverage_guard_rejects_missing_enterprise_middleware(
    tmp_path: Path,
) -> None:
    repo_root = _write_minimal_guard_repo(
        tmp_path,
        app_source=(
            "from fastapi import FastAPI\napp = FastAPI()\nconfigure_standard_http_app()\n"
        ),
    )

    findings = guard.evaluate_security_control_coverage(repo_root=repo_root)

    assert {
        "file": "src/services/demo_service/app/main.py",
        "control": "enterprise_middleware",
        "missing_anchor": "build_enterprise_audit_middleware",
    } in findings
    assert {
        "file": "src/services/demo_service/app/main.py",
        "control": "enterprise_middleware",
        "missing_anchor": "validate_enterprise_runtime_config",
    } in findings
