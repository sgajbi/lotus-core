from pathlib import Path

from scripts import generate_runtime_sbom


def test_runtime_sbom_command_uses_governed_audit_exceptions() -> None:
    python_bin = Path("runtime") / "python"
    requirements_file = Path("requirements") / "shared-runtime.lock.txt"
    output_file = Path("output") / "build-evidence" / "shared-runtime-sbom.cdx.json"

    command = generate_runtime_sbom.runtime_sbom_command(
        python_bin,
        requirements_file=requirements_file,
        output_file=output_file,
    )

    assert command == [
        str(python_bin),
        "-m",
        "pip_audit",
        "-r",
        str(requirements_file),
        "--format",
        "cyclonedx-json",
        "-o",
        str(output_file),
        "--ignore-vuln",
        "CVE-2026-3219",
        "--ignore-vuln",
        "PYSEC-2026-161",
    ]
