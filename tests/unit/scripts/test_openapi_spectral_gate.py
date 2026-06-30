from pathlib import Path

from scripts.openapi_spectral_gate import npx_executable, spectral_command


def test_npx_executable_uses_windows_command_shim() -> None:
    assert npx_executable("win32") == "npx.cmd"


def test_spectral_command_uses_direct_artifact_paths() -> None:
    command = spectral_command(
        [Path("output/openapi/query_service.openapi.json")],
        ruleset=Path(".spectral.yaml"),
        platform="linux",
    )

    assert command[:4] == ["npx", "--yes", "@stoplight/spectral-cli", "lint"]
    normalized_command = [item.replace("\\", "/") for item in command]
    assert "output/openapi/query_service.openapi.json" in normalized_command
    assert "*.openapi.json" not in command
    assert command[-4:] == ["--ruleset", ".spectral.yaml", "--fail-severity", "warn"]
