import json
from pathlib import Path

from scripts.quality.openapi_spectral_gate import (
    npm_ci_command,
    spectral_command,
    spectral_executable,
)


def test_npm_ci_command_uses_clean_lock_install_without_scripts() -> None:
    assert npm_ci_command("win32") == [
        "npm.cmd",
        "ci",
        "--ignore-scripts",
        "--no-audit",
        "--no-fund",
    ]


def test_api_governance_toolchain_versions_are_exact_and_locked() -> None:
    tool_root = Path("tools/api_governance")
    manifest = json.loads((tool_root / "package.json").read_text(encoding="utf-8"))
    lock = json.loads((tool_root / "package-lock.json").read_text(encoding="utf-8"))

    assert manifest["devDependencies"]["@stoplight/spectral-cli"] == "6.16.1"
    assert manifest["overrides"]["@asyncapi/specs"] == "6.11.1"
    assert lock["packages"]["node_modules/@stoplight/spectral-cli"]["version"] == "6.16.1"
    asyncapi_package = "node_modules/@stoplight/spectral-rulesets/node_modules/@asyncapi/specs"
    assert lock["packages"][asyncapi_package]["version"] == "6.11.1"


def test_spectral_executable_uses_lock_installed_windows_command_shim() -> None:
    executable = spectral_executable(
        "win32",
        tool_root=Path("tools/api_governance"),
    )

    assert executable.replace("\\", "/") == ("tools/api_governance/node_modules/.bin/spectral.cmd")


def test_spectral_command_uses_direct_artifact_paths() -> None:
    command = spectral_command(
        [Path("output/openapi/query_service.openapi.json")],
        ruleset=Path(".spectral.yaml"),
        platform="linux",
        tool_root=Path("tools/api_governance"),
    )

    normalized_command = [item.replace("\\", "/") for item in command]
    assert normalized_command[:2] == [
        "tools/api_governance/node_modules/.bin/spectral",
        "lint",
    ]
    assert "npx" not in " ".join(command)
    assert "@stoplight/spectral-cli" not in command
    assert "output/openapi/query_service.openapi.json" in normalized_command
    assert "*.openapi.json" not in command
    assert command[-4:] == ["--ruleset", ".spectral.yaml", "--fail-severity", "warn"]
