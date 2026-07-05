from pathlib import Path

from scripts.image_provenance_guard import find_image_provenance_findings


def _write_required_sources(root: Path, *, bootstrap_content: str | None = None) -> None:
    bootstrap = (
        root / "src" / "libs" / "portfolio-common" / "portfolio_common" / "http_app_bootstrap.py"
    )
    bootstrap.parent.mkdir(parents=True, exist_ok=True)
    bootstrap.write_text(
        bootstrap_content
        or (
            "def configure_standard_http_app():\n"
            "    create_version_router(service_name=service_name)\n"
            '"/version"\n'
        ),
        encoding="utf-8",
    )
    root.joinpath(
        "src", "libs", "portfolio-common", "portfolio_common", "build_metadata.py"
    ).write_text(
        "\n".join(
            [
                "OCI_METADATA_LABELS",
                "org.opencontainers.image.revision",
                "org.opencontainers.image.ref.name",
                "org.opencontainers.image.created",
                "org.opencontainers.image.source",
                "org.opencontainers.image.version",
                "org.opencontainers.image.digest",
                "org.opencontainers.image.ci.run_id",
                "oci_labels",
            ]
        ),
        encoding="utf-8",
    )
    scripts_dir = root / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    scripts_dir.joinpath("prebuild_ci_images.py").write_text(
        "\n".join(
            [
                "--build-arg",
                "LOTUS_GIT_COMMIT_SHA",
                "LOTUS_GIT_BRANCH",
                "LOTUS_BUILD_TIMESTAMP",
                "LOTUS_REPO_URL",
                "LOTUS_IMAGE_VERSION",
                "LOTUS_IMAGE_DIGEST",
                "LOTUS_CI_RUN_ID",
            ]
        ),
        encoding="utf-8",
    )
    scripts_dir.joinpath("write_build_provenance.py").write_text(
        "image_build_metadata", encoding="utf-8"
    )
    scripts_dir.joinpath("write_image_release_manifest.py").write_text(
        "\n".join(
            [
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
            ]
        ),
        encoding="utf-8",
    )
    workflow = root / ".github" / "workflows" / "image-release.yml"
    workflow.parent.mkdir(parents=True, exist_ok=True)
    workflow.write_text(
        "\n".join(
            [
                "permissions:",
                "  packages: write",
                "  id-token: write",
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
            ]
        ),
        encoding="utf-8",
    )


def _write_dockerfile(root: Path, content: str) -> None:
    dockerfile = root / "src" / "services" / "query_service" / "Dockerfile"
    dockerfile.parent.mkdir(parents=True, exist_ok=True)
    dockerfile.write_text(content, encoding="utf-8")


def _complete_dockerfile() -> str:
    return """
ARG LOTUS_GIT_COMMIT_SHA=unknown
ARG LOTUS_GIT_BRANCH=unknown
ARG LOTUS_BUILD_TIMESTAMP=unknown
ARG LOTUS_REPO_URL=unknown
ARG LOTUS_IMAGE_VERSION=unknown
ARG LOTUS_IMAGE_DIGEST=unknown
ARG LOTUS_CI_RUN_ID=unknown
FROM python:3.11 AS runtime-base
ARG LOTUS_GIT_COMMIT_SHA
ARG LOTUS_GIT_BRANCH
ARG LOTUS_BUILD_TIMESTAMP
ARG LOTUS_REPO_URL
ARG LOTUS_IMAGE_VERSION
ARG LOTUS_IMAGE_DIGEST
ARG LOTUS_CI_RUN_ID
LABEL org.opencontainers.image.revision=${LOTUS_GIT_COMMIT_SHA} \\
    org.opencontainers.image.ref.name=${LOTUS_GIT_BRANCH} \\
    org.opencontainers.image.created=${LOTUS_BUILD_TIMESTAMP} \\
    org.opencontainers.image.source=${LOTUS_REPO_URL} \\
    org.opencontainers.image.version=${LOTUS_IMAGE_VERSION} \\
    org.opencontainers.image.digest=${LOTUS_IMAGE_DIGEST} \\
    org.opencontainers.image.ci.run_id=${LOTUS_CI_RUN_ID}
ENV LOTUS_GIT_COMMIT_SHA=${LOTUS_GIT_COMMIT_SHA} \\
    LOTUS_GIT_BRANCH=${LOTUS_GIT_BRANCH} \\
    LOTUS_BUILD_TIMESTAMP=${LOTUS_BUILD_TIMESTAMP} \\
    LOTUS_REPO_URL=${LOTUS_REPO_URL} \\
    LOTUS_IMAGE_VERSION=${LOTUS_IMAGE_VERSION} \\
    LOTUS_IMAGE_DIGEST=${LOTUS_IMAGE_DIGEST} \\
    LOTUS_CI_RUN_ID=${LOTUS_CI_RUN_ID}
"""


def test_image_provenance_guard_accepts_complete_contract(tmp_path: Path) -> None:
    _write_required_sources(tmp_path)
    _write_dockerfile(tmp_path, _complete_dockerfile())

    assert find_image_provenance_findings(tmp_path) == []


def test_image_provenance_guard_reports_missing_digest_label(tmp_path: Path) -> None:
    _write_required_sources(tmp_path)
    _write_dockerfile(
        tmp_path,
        _complete_dockerfile().replace(
            "    org.opencontainers.image.digest=${LOTUS_IMAGE_DIGEST} \\\n",
            "",
        ),
    )

    findings = find_image_provenance_findings(tmp_path)

    assert any("missing OCI label org.opencontainers.image.digest" in f.detail for f in findings)


def test_image_provenance_guard_requires_standard_version_endpoint(tmp_path: Path) -> None:
    _write_required_sources(
        tmp_path, bootstrap_content="def configure_standard_http_app():\n    pass\n"
    )
    _write_dockerfile(tmp_path, _complete_dockerfile())

    findings = find_image_provenance_findings(tmp_path)

    assert any("missing /version route" in f.detail for f in findings)


def test_image_provenance_guard_requires_version_endpoint_oci_label_parity(
    tmp_path: Path,
) -> None:
    _write_required_sources(tmp_path)
    build_metadata = (
        tmp_path / "src" / "libs" / "portfolio-common" / "portfolio_common" / "build_metadata.py"
    )
    build_metadata.write_text("oci_labels\n", encoding="utf-8")
    _write_dockerfile(tmp_path, _complete_dockerfile())

    findings = find_image_provenance_findings(tmp_path)

    assert any(
        "version endpoint metadata omits org.opencontainers.image.digest" in f.detail
        for f in findings
    )
