"""Validate Lotus Core image provenance labels and runtime metadata endpoints."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
RELEASE_WORKFLOW = Path(".github/workflows/image-release.yml")

REQUIRED_METADATA_ARGS = (
    "LOTUS_GIT_COMMIT_SHA",
    "LOTUS_GIT_BRANCH",
    "LOTUS_BUILD_TIMESTAMP",
    "LOTUS_REPO_URL",
    "LOTUS_IMAGE_VERSION",
    "LOTUS_IMAGE_DIGEST",
    "LOTUS_CI_RUN_ID",
)

REQUIRED_OCI_LABELS = {
    "org.opencontainers.image.revision": "LOTUS_GIT_COMMIT_SHA",
    "org.opencontainers.image.ref.name": "LOTUS_GIT_BRANCH",
    "org.opencontainers.image.created": "LOTUS_BUILD_TIMESTAMP",
    "org.opencontainers.image.source": "LOTUS_REPO_URL",
    "org.opencontainers.image.version": "LOTUS_IMAGE_VERSION",
    "org.opencontainers.image.digest": "LOTUS_IMAGE_DIGEST",
    "org.opencontainers.image.ci.run_id": "LOTUS_CI_RUN_ID",
}

SECRET_LIKE_TOKENS = ("SECRET", "TOKEN", "PASSWORD", "CREDENTIAL", "PRIVATE_KEY")

REQUIRED_RELEASE_WORKFLOW_SNIPPETS = (
    "packages: write",
    "id-token: write",
    "docker buildx build",
    "--push",
    '--tag "${{ steps.meta.outputs.image_tag }}"',
    "${GITHUB_SHA}",
    "--sbom=true",
    "--provenance=true",
    "aquasec/trivy",
    "--severity HIGH,CRITICAL",
    "--format cyclonedx",
    "-sbom.cdx.json",
    "cosign sign --yes",
    "write_image_release_manifest.py",
    '--image-digest "${{ steps.digest.outputs.image_digest }}"',
    "--kubernetes-deploys-by-digest true",
    "--promotion-environments dev uat prod",
)


@dataclass(frozen=True)
class ImageProvenanceFinding:
    path: Path
    detail: str


def _relative(path: Path, root: Path) -> Path:
    try:
        return path.relative_to(root)
    except ValueError:
        return path


def _dockerfile_findings(root: Path) -> list[ImageProvenanceFinding]:
    findings: list[ImageProvenanceFinding] = []
    for dockerfile in sorted((root / "src" / "services").rglob("Dockerfile")):
        content = dockerfile.read_text(encoding="utf-8")
        for line_number, line in enumerate(content.splitlines(), start=1):
            stripped = line.strip()
            if not (stripped.startswith("ARG ") or stripped.startswith("ENV ")):
                continue
            upper_line = stripped.upper()
            if any(token in upper_line for token in SECRET_LIKE_TOKENS):
                findings.append(
                    ImageProvenanceFinding(
                        _relative(dockerfile, root),
                        f"secret-like build ARG/ENV at line {line_number}",
                    )
                )
        for arg_name in REQUIRED_METADATA_ARGS:
            if f"ARG {arg_name}=unknown" not in content:
                findings.append(
                    ImageProvenanceFinding(
                        _relative(dockerfile, root),
                        f"missing default build arg {arg_name}",
                    )
                )
            if content.count(f"ARG {arg_name}") < 2:
                findings.append(
                    ImageProvenanceFinding(
                        _relative(dockerfile, root),
                        f"missing stage build arg {arg_name}",
                    )
                )
            if f"{arg_name}=${{{arg_name}}}" not in content:
                findings.append(
                    ImageProvenanceFinding(
                        _relative(dockerfile, root),
                        f"missing runtime env {arg_name}",
                    )
                )
        for label_name, arg_name in REQUIRED_OCI_LABELS.items():
            if f"{label_name}=${{{arg_name}}}" not in content:
                findings.append(
                    ImageProvenanceFinding(
                        _relative(dockerfile, root),
                        f"missing OCI label {label_name}",
                    )
                )
    return findings


def _release_workflow_findings(root: Path) -> list[ImageProvenanceFinding]:
    findings: list[ImageProvenanceFinding] = []
    workflow_path = root / RELEASE_WORKFLOW
    if not workflow_path.exists():
        return [
            ImageProvenanceFinding(
                RELEASE_WORKFLOW,
                "missing CI-only image release workflow",
            )
        ]
    workflow_content = workflow_path.read_text(encoding="utf-8")
    for snippet in REQUIRED_RELEASE_WORKFLOW_SNIPPETS:
        if snippet not in workflow_content:
            findings.append(
                ImageProvenanceFinding(
                    RELEASE_WORKFLOW,
                    f"image release workflow missing {snippet}",
                )
            )

    for line_number, line in enumerate(workflow_content.splitlines(), start=1):
        if "--build-arg" not in line:
            continue
        upper_line = line.upper()
        if any(token in upper_line for token in SECRET_LIKE_TOKENS):
            findings.append(
                ImageProvenanceFinding(
                    RELEASE_WORKFLOW,
                    f"secret-like build arg in image release workflow at line {line_number}",
                )
            )

    push_scan_roots = (root / ".github" / "workflows", root / "scripts", root / "Makefile")
    push_scan_paths: list[Path] = []
    for scan_root in push_scan_roots:
        if scan_root.is_file():
            push_scan_paths.append(scan_root)
        elif scan_root.exists():
            push_scan_paths.extend(path for path in scan_root.rglob("*") if path.is_file())
    for path in sorted(push_scan_paths):
        if not path.is_file() or ".git" in path.parts:
            continue
        relative = _relative(path, root)
        if relative == RELEASE_WORKFLOW:
            continue
        if relative == Path("scripts/image_provenance_guard.py"):
            continue
        if any(part in {"output", ".venv", "__pycache__", "node_modules"} for part in path.parts):
            continue
        if path.suffix.lower() not in {".yml", ".yaml", ".sh", ".ps1", ".py", ""}:
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if "docker push" in content or "buildx build" in content and "--push" in content:
            findings.append(
                ImageProvenanceFinding(
                    relative,
                    "image push must remain isolated to the CI image release workflow",
                )
            )
    return findings


def _kubernetes_digest_findings(root: Path) -> list[ImageProvenanceFinding]:
    findings: list[ImageProvenanceFinding] = []
    deployment_root = root / "deployment" / "kubernetes"
    if not deployment_root.exists():
        return findings
    for manifest in sorted(deployment_root.rglob("*.y*ml")):
        for line_number, line in enumerate(
            manifest.read_text(encoding="utf-8").splitlines(), start=1
        ):
            stripped = line.strip()
            if not stripped.startswith("image:"):
                continue
            if "@sha256:" not in stripped:
                findings.append(
                    ImageProvenanceFinding(
                        _relative(manifest, root),
                        f"Kubernetes image reference at line {line_number} is not digest-pinned",
                    )
                )
    return findings


def _source_contract_findings(root: Path) -> list[ImageProvenanceFinding]:
    findings: list[ImageProvenanceFinding] = []
    bootstrap = (
        root / "src" / "libs" / "portfolio-common" / "portfolio_common" / "http_app_bootstrap.py"
    )
    bootstrap_content = bootstrap.read_text(encoding="utf-8")
    if '"/version"' not in bootstrap_content:
        findings.append(
            ImageProvenanceFinding(_relative(bootstrap, root), "missing /version route")
        )
    if "create_version_router(service_name=service_name)" not in bootstrap_content:
        findings.append(
            ImageProvenanceFinding(
                _relative(bootstrap, root),
                "standard HTTP app bootstrap does not include version router",
            )
        )

    prebuild = root / "scripts" / "prebuild_ci_images.py"
    prebuild_content = prebuild.read_text(encoding="utf-8")
    for arg_name in REQUIRED_METADATA_ARGS:
        if arg_name not in prebuild_content:
            findings.append(
                ImageProvenanceFinding(
                    _relative(prebuild, root),
                    f"CI prebuild script does not pass {arg_name}",
                )
            )
    if "--build-arg" not in prebuild_content:
        findings.append(
            ImageProvenanceFinding(_relative(prebuild, root), "CI prebuild script omits build args")
        )

    build_provenance = root / "scripts" / "write_build_provenance.py"
    build_provenance_content = build_provenance.read_text(encoding="utf-8")
    if "image_build_metadata" not in build_provenance_content:
        findings.append(
            ImageProvenanceFinding(
                _relative(build_provenance, root),
                "build provenance manifest omits image metadata",
            )
        )
    release_manifest = root / "scripts" / "write_image_release_manifest.py"
    release_manifest_content = release_manifest.read_text(encoding="utf-8")
    for required_field in (
        "image_digest",
        "digest_image_ref",
        "sbom_generated",
        "vulnerability_scan_status",
        "image_signed",
        "provenance_attestation_generated",
        "kubernetes_deploys_by_digest",
        "same_image_promoted_across_environments",
        "runtime_env",
        "oci_labels",
    ):
        if required_field not in release_manifest_content:
            findings.append(
                ImageProvenanceFinding(
                    _relative(release_manifest, root),
                    f"image release manifest omits {required_field}",
                )
            )

    build_metadata = (
        root / "src" / "libs" / "portfolio-common" / "portfolio_common" / "build_metadata.py"
    )
    build_metadata_content = build_metadata.read_text(encoding="utf-8")
    for required_source_term in (
        "OCI_METADATA_LABELS",
        "org.opencontainers.image.revision",
        "org.opencontainers.image.ref.name",
        "org.opencontainers.image.created",
        "org.opencontainers.image.source",
        "org.opencontainers.image.version",
        "org.opencontainers.image.digest",
        "org.opencontainers.image.ci.run_id",
        "oci_labels",
    ):
        if required_source_term not in build_metadata_content:
            findings.append(
                ImageProvenanceFinding(
                    _relative(build_metadata, root),
                    f"version endpoint metadata omits {required_source_term}",
                )
            )
    return findings


def find_image_provenance_findings(root: Path = REPO_ROOT) -> list[ImageProvenanceFinding]:
    return [
        *_dockerfile_findings(root),
        *_release_workflow_findings(root),
        *_kubernetes_digest_findings(root),
        *_source_contract_findings(root),
    ]


def main() -> int:
    findings = find_image_provenance_findings(REPO_ROOT)
    if findings:
        for finding in findings:
            print(f"{finding.path}: {finding.detail}")
        raise SystemExit(1)
    print("Image provenance guard passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
