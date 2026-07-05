"""Validate HTTP security control coverage for lotus-core FastAPI apps."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = Path("contracts/security/security-control-coverage.v1.json")
SHARED_BOOTSTRAP_PATH = Path("src/libs/portfolio-common/portfolio_common/http_app_bootstrap.py")
SHARED_ENTERPRISE_PATH = Path("src/libs/portfolio-common/portfolio_common/enterprise_readiness.py")
INGESTION_UPLOAD_ROUTER_PATH = Path("src/services/ingestion_service/app/routers/uploads.py")
INGESTION_SETTINGS_PATH = Path("src/services/ingestion_service/app/settings.py")

REQUIRED_SHARED_BOOTSTRAP_ANCHORS = {
    "secure_response_headers": "configure_secure_response_headers",
    "cors_policy": "configure_cors_policy",
    "trusted_host_policy": "configure_trusted_host_policy",
    "metrics_access_policy": "configure_metrics_access_policy",
    "safe_unhandled_error_response": "unhandled_exception_handler",
}

VALID_AUTH_AUDIT_CONTROLS = {
    "enterprise_middleware",
    "health_only_no_business_routes",
}

VALID_PAYLOAD_CONTROLS = {
    "enterprise_middleware",
    "not_applicable_health_only",
}

VALID_UPLOAD_CONTROLS = {
    "ingestion_upload_max_bytes",
    "not_applicable",
}


def _read_text(path: Path, *, repo_root: Path) -> str:
    return (repo_root / path).read_text(encoding="utf-8")


def _load_contract(*, repo_root: Path) -> dict[str, Any]:
    return json.loads(_read_text(CONTRACT_PATH, repo_root=repo_root))


def _relative(path: Path, *, repo_root: Path) -> str:
    return path.relative_to(repo_root).as_posix()


def _is_generated(path: Path, *, repo_root: Path) -> bool:
    return "/build/" in f"/{_relative(path, repo_root=repo_root)}/"


def _discover_fastapi_apps(*, repo_root: Path) -> set[str]:
    discovered: set[str] = set()
    for path in (repo_root / "src/services").glob("**/app/*.py"):
        if path.name not in {"main.py", "web.py"} or _is_generated(path, repo_root=repo_root):
            continue
        content = path.read_text(encoding="utf-8")
        if "FastAPI(" in content or "create_standard_health_app(" in content:
            discovered.add(_relative(path, repo_root=repo_root))
    return discovered


def _contract_app_paths(contract: dict[str, Any]) -> set[str]:
    return {str(app.get("app_path", "")) for app in contract.get("apps", [])}


def _append_missing_anchor(
    findings: list[dict[str, object]],
    *,
    file: str,
    control: str,
    anchor: str,
) -> None:
    findings.append(
        {
            "file": file,
            "control": control,
            "missing_anchor": anchor,
        }
    )


def _contains_any_anchor(content: str, anchors: tuple[str, ...]) -> bool:
    return any(anchor in content for anchor in anchors)


def _enterprise_middleware_installed(content: str) -> bool:
    return _contains_any_anchor(
        content,
        (
            "build_enterprise_audit_middleware",
            "build_default_enterprise_audit_middleware",
        ),
    )


def _enterprise_runtime_validation_installed(content: str) -> bool:
    return _contains_any_anchor(
        content,
        (
            "validate_enterprise_runtime_config",
            "validate_default_enterprise_runtime_config",
        ),
    )


def _validate_shared_bootstrap_anchors(
    findings: list[dict[str, object]],
    *,
    repo_root: Path,
) -> None:
    bootstrap = _read_text(SHARED_BOOTSTRAP_PATH, repo_root=repo_root)
    for control, anchor in REQUIRED_SHARED_BOOTSTRAP_ANCHORS.items():
        if anchor not in bootstrap:
            _append_missing_anchor(
                findings,
                file=SHARED_BOOTSTRAP_PATH.as_posix(),
                control=control,
                anchor=anchor,
            )


def _validate_enterprise_shared_anchors(
    findings: list[dict[str, object]],
    *,
    repo_root: Path,
) -> None:
    enterprise = _read_text(SHARED_ENTERPRISE_PATH, repo_root=repo_root)
    for anchor in (
        "build_enterprise_audit_middleware",
        "validate_enterprise_runtime_config",
        "enterprise_max_write_payload_bytes",
        "payload_too_large",
    ):
        if anchor not in enterprise:
            _append_missing_anchor(
                findings,
                file=SHARED_ENTERPRISE_PATH.as_posix(),
                control="enterprise_middleware",
                anchor=anchor,
            )


def _validate_ingestion_upload_limit(
    findings: list[dict[str, object]],
    *,
    repo_root: Path,
) -> None:
    router = _read_text(INGESTION_UPLOAD_ROUTER_PATH, repo_root=repo_root)
    settings = _read_text(INGESTION_SETTINGS_PATH, repo_root=repo_root)
    for file, text, anchor in (
        (INGESTION_UPLOAD_ROUTER_PATH, router, "_read_bounded_upload_content"),
        (INGESTION_UPLOAD_ROUTER_PATH, router, "INGESTION_UPLOAD_TOO_LARGE"),
        (INGESTION_SETTINGS_PATH, settings, "LOTUS_CORE_INGEST_UPLOAD_MAX_BYTES"),
    ):
        if anchor not in text:
            _append_missing_anchor(
                findings,
                file=file.as_posix(),
                control="ingestion_upload_max_bytes",
                anchor=anchor,
            )


def _validate_app_entry(
    app: dict[str, Any],
    findings: list[dict[str, object]],
    *,
    repo_root: Path,
) -> None:
    app_path = str(app.get("app_path", ""))
    if not app_path:
        findings.append({"app": app.get("service_name"), "missing": "app_path"})
        return

    path = Path(app_path)
    if not (repo_root / path).exists():
        findings.append({"app": app.get("service_name"), "missing_file": app_path})
        return

    content = _read_text(path, repo_root=repo_root)
    if (
        "configure_standard_http_app(" not in content
        and "create_standard_health_app(" not in content
    ):
        _append_missing_anchor(
            findings,
            file=app_path,
            control="standard_http_bootstrap",
            anchor="configure_standard_http_app or create_standard_health_app",
        )

    auth_control = str(app.get("auth_audit_control", ""))
    if auth_control not in VALID_AUTH_AUDIT_CONTROLS:
        findings.append({"file": app_path, "invalid_auth_audit_control": auth_control})
    elif auth_control == "enterprise_middleware":
        if not _enterprise_middleware_installed(content):
            _append_missing_anchor(
                findings,
                file=app_path,
                control="enterprise_middleware",
                anchor="build_enterprise_audit_middleware",
            )
        if not _enterprise_runtime_validation_installed(content):
            _append_missing_anchor(
                findings,
                file=app_path,
                control="enterprise_middleware",
                anchor="validate_enterprise_runtime_config",
            )
    elif "create_standard_health_app(" not in content:
        _append_missing_anchor(
            findings,
            file=app_path,
            control="health_only_no_business_routes",
            anchor="create_standard_health_app",
        )

    payload_control = str(app.get("payload_limit_control", ""))
    if payload_control not in VALID_PAYLOAD_CONTROLS:
        findings.append({"file": app_path, "invalid_payload_limit_control": payload_control})
    elif payload_control == "enterprise_middleware" and not _enterprise_middleware_installed(
        content
    ):
        _append_missing_anchor(
            findings,
            file=app_path,
            control="payload_limit_control",
            anchor="build_enterprise_audit_middleware",
        )

    upload_control = str(app.get("upload_limit_control", ""))
    if upload_control not in VALID_UPLOAD_CONTROLS:
        findings.append({"file": app_path, "invalid_upload_limit_control": upload_control})
    elif upload_control == "ingestion_upload_max_bytes":
        _validate_ingestion_upload_limit(findings, repo_root=repo_root)

    allowlist = app.get("unauthenticated_allowlist")
    if not isinstance(allowlist, list) or not {
        "/health/live",
        "/health/ready",
        "/metrics",
    }.issubset(set(allowlist)):
        findings.append({"file": app_path, "invalid_unauthenticated_allowlist": allowlist})


def evaluate_security_control_coverage(*, repo_root: Path = REPO_ROOT) -> list[dict[str, object]]:
    findings: list[dict[str, object]] = []
    contract = _load_contract(repo_root=repo_root)

    if contract.get("schema_version") != "security-control-coverage.v1":
        findings.append({"contract": CONTRACT_PATH.as_posix(), "invalid_schema_version": True})

    discovered_apps = _discover_fastapi_apps(repo_root=repo_root)
    contract_apps = _contract_app_paths(contract)
    if missing_from_contract := sorted(discovered_apps - contract_apps):
        findings.append({"missing_from_contract": missing_from_contract})
    if stale_contract_entries := sorted(contract_apps - discovered_apps):
        findings.append({"stale_contract_entries": stale_contract_entries})

    _validate_shared_bootstrap_anchors(findings, repo_root=repo_root)
    _validate_enterprise_shared_anchors(findings, repo_root=repo_root)

    for app in contract.get("apps", []):
        if isinstance(app, dict):
            _validate_app_entry(app, findings, repo_root=repo_root)
        else:
            findings.append({"invalid_app_entry": app})

    return findings


def main() -> int:
    findings = evaluate_security_control_coverage()
    if findings:
        print("Security control coverage guard failed:")
        print(json.dumps(findings, indent=2))
        return 1
    print("Security control coverage guard passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
