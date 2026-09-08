from pathlib import Path

from scripts.quality.image_provenance_guard import find_image_provenance_findings

SOURCE_WORKFLOW = (
    Path(__file__).resolve().parents[3] / ".github" / "workflows" / "image-release.yml"
)


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
    scripts_dir = root / "scripts" / "release"
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
    workflow.write_text(SOURCE_WORKFLOW.read_text(encoding="utf-8"), encoding="utf-8")
    root.joinpath("docker-compose.yml").write_text(
        """services:
  query_service:
    build:
      context: .
      dockerfile: ./src/services/query_service/Dockerfile
      args:
        LOTUS_GIT_COMMIT_SHA: ${LOTUS_GIT_COMMIT_SHA:-unknown}
        LOTUS_GIT_BRANCH: ${LOTUS_GIT_BRANCH:-unknown}
        LOTUS_BUILD_TIMESTAMP: ${LOTUS_BUILD_TIMESTAMP:-unknown}
        LOTUS_REPO_URL: ${LOTUS_REPO_URL:-unknown}
        LOTUS_IMAGE_VERSION: ${LOTUS_IMAGE_VERSION:-unknown}
        LOTUS_IMAGE_DIGEST: ${LOTUS_IMAGE_DIGEST:-unavailable-before-push}
        LOTUS_CI_RUN_ID: ${LOTUS_CI_RUN_ID:-unavailable-local-build}
""",
        encoding="utf-8",
    )
    root.joinpath("Makefile").write_text(
        """override REPOSITORY_PYTHON := python scripts/development/repository_python.py
docker-build:
\t$(REPOSITORY_PYTHON) scripts/release/local_image_build.py docker-build
docker-up:
\t$(REPOSITORY_PYTHON) scripts/release/local_image_build.py compose-up
""",
        encoding="utf-8",
    )
    local_build = root / "scripts" / "release" / "local_image_build.py"
    local_build.write_text(
        'git_commit_sha\n"status", "--porcelain"\nunavailable-before-push\n'
        "unavailable-local-build\n",
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
RUN install-dependencies
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


def test_image_provenance_guard_requires_metadata_in_final_stage(tmp_path: Path) -> None:
    _write_required_sources(tmp_path)
    _write_dockerfile(
        tmp_path,
        _complete_dockerfile() + '\nFROM python:3.11 AS final\nCMD ["python"]\n',
    )

    findings = find_image_provenance_findings(tmp_path)

    assert any("missing final-stage build arg" in finding.detail for finding in findings)
    assert any("effective final-stage OCI label" in finding.detail for finding in findings)
    assert any("effective final-stage runtime env" in finding.detail for finding in findings)


def test_image_provenance_guard_rejects_effective_label_override(tmp_path: Path) -> None:
    _write_required_sources(tmp_path)
    _write_dockerfile(
        tmp_path,
        _complete_dockerfile() + "\nLABEL org.opencontainers.image.digest=bogus\n",
    )

    findings = find_image_provenance_findings(tmp_path)

    assert any(
        "incorrect effective final-stage OCI label org.opencontainers.image.digest"
        in finding.detail
        for finding in findings
    )


def test_image_provenance_guard_rejects_effective_environment_override(
    tmp_path: Path,
) -> None:
    _write_required_sources(tmp_path)
    _write_dockerfile(
        tmp_path,
        _complete_dockerfile() + "\nENV LOTUS_GIT_COMMIT_SHA=bogus\n",
    )

    findings = find_image_provenance_findings(tmp_path)

    assert any(
        "incorrect effective final-stage runtime env LOTUS_GIT_COMMIT_SHA" in finding.detail
        for finding in findings
    )


def test_image_provenance_guard_rejects_compose_build_without_metadata_args(
    tmp_path: Path,
) -> None:
    _write_required_sources(tmp_path)
    _write_dockerfile(tmp_path, _complete_dockerfile())
    compose = tmp_path / "docker-compose.yml"
    compose.write_text(
        compose.read_text(encoding="utf-8").replace(
            "        LOTUS_GIT_COMMIT_SHA: ${LOTUS_GIT_COMMIT_SHA:-unknown}\n", ""
        ),
        encoding="utf-8",
    )

    findings = find_image_provenance_findings(tmp_path)

    assert any("query_service does not receive LOTUS_GIT_COMMIT_SHA" in f.detail for f in findings)


def test_image_provenance_guard_rejects_compose_build_with_constant_metadata(
    tmp_path: Path,
) -> None:
    _write_required_sources(tmp_path)
    _write_dockerfile(tmp_path, _complete_dockerfile())
    compose = tmp_path / "docker-compose.yml"
    compose.write_text(
        compose.read_text(encoding="utf-8").replace(
            "        LOTUS_GIT_COMMIT_SHA: ${LOTUS_GIT_COMMIT_SHA:-unknown}\n",
            "        LOTUS_GIT_COMMIT_SHA: unknown\n",
        ),
        encoding="utf-8",
    )

    findings = find_image_provenance_findings(tmp_path)

    assert any("query_service does not bind LOTUS_GIT_COMMIT_SHA" in f.detail for f in findings)


def test_image_provenance_guard_rejects_shorthand_compose_build(tmp_path: Path) -> None:
    _write_required_sources(tmp_path)
    _write_dockerfile(tmp_path, _complete_dockerfile())
    compose = tmp_path / "docker-compose.yml"
    compose.write_text(
        compose.read_text(encoding="utf-8").replace(
            "    build:\n      context: .\n"
            "      dockerfile: ./src/services/query_service/Dockerfile\n      args:\n",
            "    build: .\n    ignored-args:\n",
        ),
        encoding="utf-8",
    )

    findings = find_image_provenance_findings(tmp_path)

    assert any("query_service must use mapping form" in f.detail for f in findings)


def test_image_provenance_guard_rejects_make_build_path_bypass(tmp_path: Path) -> None:
    _write_required_sources(tmp_path)
    _write_dockerfile(tmp_path, _complete_dockerfile())
    makefile = tmp_path / "Makefile"
    makefile.write_text(
        makefile.read_text(encoding="utf-8").replace(
            "$(REPOSITORY_PYTHON) scripts/release/local_image_build.py docker-build",
            "docker build .",
        )
        + "\nunused-helper:\n"
        "\t$(REPOSITORY_PYTHON) scripts/release/local_image_build.py docker-build\n",
        encoding="utf-8",
    )

    findings = find_image_provenance_findings(tmp_path)

    assert any("docker-build must route through" in f.detail for f in findings)


def test_image_provenance_guard_rejects_commented_make_wrapper(tmp_path: Path) -> None:
    _write_required_sources(tmp_path)
    _write_dockerfile(tmp_path, _complete_dockerfile())
    makefile = tmp_path / "Makefile"
    makefile.write_text(
        makefile.read_text(encoding="utf-8").replace(
            "\t$(REPOSITORY_PYTHON) scripts/release/local_image_build.py docker-build",
            "\tdocker build . # $(REPOSITORY_PYTHON) "
            "scripts/release/local_image_build.py docker-build",
        ),
        encoding="utf-8",
    )

    findings = find_image_provenance_findings(tmp_path)

    assert any("docker-build must route through" in f.detail for f in findings)


def test_image_provenance_guard_rejects_echoed_make_wrapper(tmp_path: Path) -> None:
    _write_required_sources(tmp_path)
    _write_dockerfile(tmp_path, _complete_dockerfile())
    makefile = tmp_path / "Makefile"
    makefile.write_text(
        makefile.read_text(encoding="utf-8").replace(
            "\t$(REPOSITORY_PYTHON) scripts/release/local_image_build.py docker-build",
            "\t@echo $(REPOSITORY_PYTHON) "
            "scripts/release/local_image_build.py docker-build\n\tdocker build .",
        ),
        encoding="utf-8",
    )

    findings = find_image_provenance_findings(tmp_path)

    assert any("docker-build must route through" in f.detail for f in findings)


def test_image_provenance_guard_rejects_additional_make_build_command(tmp_path: Path) -> None:
    _write_required_sources(tmp_path)
    _write_dockerfile(tmp_path, _complete_dockerfile())
    makefile = tmp_path / "Makefile"
    makefile.write_text(
        makefile.read_text(encoding="utf-8").replace(
            "\t$(REPOSITORY_PYTHON) scripts/release/local_image_build.py docker-build",
            "\t$(REPOSITORY_PYTHON) scripts/release/local_image_build.py docker-build\n"
            "\tdocker build -t portfolio-analytics-query-service:ci .",
        ),
        encoding="utf-8",
    )

    findings = find_image_provenance_findings(tmp_path)

    assert any("docker-build must route through" in f.detail for f in findings)


def test_image_provenance_guard_continues_past_makefile_comment(tmp_path: Path) -> None:
    _write_required_sources(tmp_path)
    _write_dockerfile(tmp_path, _complete_dockerfile())
    makefile = tmp_path / "Makefile"
    makefile.write_text(
        makefile.read_text(encoding="utf-8").replace(
            "\t$(REPOSITORY_PYTHON) scripts/release/local_image_build.py docker-build",
            "\t$(REPOSITORY_PYTHON) scripts/release/local_image_build.py docker-build\n"
            "# This comment does not end the recipe.\n"
            "\tdocker build -t portfolio-analytics-query-service:ci .",
        ),
        encoding="utf-8",
    )

    findings = find_image_provenance_findings(tmp_path)

    assert any("docker-build must route through" in f.detail for f in findings)


def test_image_provenance_guard_rejects_overridden_make_target(tmp_path: Path) -> None:
    _write_required_sources(tmp_path)
    _write_dockerfile(tmp_path, _complete_dockerfile())
    makefile = tmp_path / "Makefile"
    makefile.write_text(
        makefile.read_text(encoding="utf-8")
        + "\ndocker-build:\n\tdocker build -t portfolio-analytics-query-service:ci .\n",
        encoding="utf-8",
    )

    findings = find_image_provenance_findings(tmp_path)

    assert any("docker-build must route through" in f.detail for f in findings)


def test_image_provenance_guard_rejects_multi_target_override(tmp_path: Path) -> None:
    _write_required_sources(tmp_path)
    _write_dockerfile(tmp_path, _complete_dockerfile())
    makefile = tmp_path / "Makefile"
    makefile.write_text(
        makefile.read_text(encoding="utf-8") + "\ndocker-build docker-up:\n"
        "\tdocker build -t portfolio-analytics-query-service:ci .\n",
        encoding="utf-8",
    )

    findings = find_image_provenance_findings(tmp_path)

    assert any("docker-build must route through" in f.detail for f in findings)
    assert any("docker-up must route through" in f.detail for f in findings)


def test_image_provenance_guard_rejects_continued_target_override(tmp_path: Path) -> None:
    _write_required_sources(tmp_path)
    _write_dockerfile(tmp_path, _complete_dockerfile())
    makefile = tmp_path / "Makefile"
    makefile.write_text(
        makefile.read_text(encoding="utf-8") + "\ndocker-build \\\nother-target:\n"
        "\tdocker build -t portfolio-analytics-query-service:ci .\n",
        encoding="utf-8",
    )

    findings = find_image_provenance_findings(tmp_path)

    assert any("docker-build must route through" in f.detail for f in findings)


def test_image_provenance_guard_rejects_variable_target_override(tmp_path: Path) -> None:
    _write_required_sources(tmp_path)
    _write_dockerfile(tmp_path, _complete_dockerfile())
    makefile = tmp_path / "Makefile"
    makefile.write_text(
        makefile.read_text(encoding="utf-8") + "\nTARGET := docker-build\n$(TARGET):\n"
        "\tdocker build -t portfolio-analytics-query-service:ci .\n",
        encoding="utf-8",
    )

    findings = find_image_provenance_findings(tmp_path)

    assert any("docker-build must route through" in f.detail for f in findings)


def test_image_provenance_guard_rejects_included_makefile_override(tmp_path: Path) -> None:
    _write_required_sources(tmp_path)
    _write_dockerfile(tmp_path, _complete_dockerfile())
    (tmp_path / "override.mk").write_text(
        "docker-build:\n\tdocker build -t portfolio-analytics-query-service:ci .\n",
        encoding="utf-8",
    )
    makefile = tmp_path / "Makefile"
    makefile.write_text(
        makefile.read_text(encoding="utf-8") + "\ninclude override.mk\n",
        encoding="utf-8",
    )

    findings = find_image_provenance_findings(tmp_path)

    assert any("Makefile includes are not permitted" in f.detail for f in findings)


def test_image_provenance_guard_rejects_evaluated_makefile_include(tmp_path: Path) -> None:
    _write_required_sources(tmp_path)
    _write_dockerfile(tmp_path, _complete_dockerfile())
    (tmp_path / "override.mk").write_text(
        "docker-build:\n\tdocker build -t portfolio-analytics-query-service:ci .\n",
        encoding="utf-8",
    )
    makefile = tmp_path / "Makefile"
    makefile.write_text(
        makefile.read_text(encoding="utf-8") + "\n$(eval include override.mk)\n",
        encoding="utf-8",
    )

    findings = find_image_provenance_findings(tmp_path)

    assert any("Makefile eval is not permitted" in finding.detail for finding in findings)


def test_image_provenance_guard_rejects_reassigned_make_wrapper(tmp_path: Path) -> None:
    _write_required_sources(tmp_path)
    _write_dockerfile(tmp_path, _complete_dockerfile())
    makefile = tmp_path / "Makefile"
    makefile.write_text(
        makefile.read_text(encoding="utf-8").replace(
            "override REPOSITORY_PYTHON := python scripts/development/repository_python.py",
            "REPOSITORY_PYTHON := docker build -t bypass . ; true",
        ),
        encoding="utf-8",
    )

    findings = find_image_provenance_findings(tmp_path)

    assert any("non-overridable governed binding" in finding.detail for finding in findings)


def test_image_provenance_guard_rejects_compose_build_target(tmp_path: Path) -> None:
    _write_required_sources(tmp_path)
    _write_dockerfile(tmp_path, _complete_dockerfile())
    compose = tmp_path / "docker-compose.yml"
    compose.write_text(
        compose.read_text(encoding="utf-8").replace(
            "      dockerfile: ./src/services/query_service/Dockerfile\n",
            "      dockerfile: ./src/services/query_service/Dockerfile\n"
            "      target: runtime-base\n",
        ),
        encoding="utf-8",
    )

    findings = find_image_provenance_findings(tmp_path)

    assert any("inspected final Docker stage" in finding.detail for finding in findings)


def test_image_provenance_guard_rejects_uninspected_compose_dockerfile(
    tmp_path: Path,
) -> None:
    _write_required_sources(tmp_path)
    _write_dockerfile(tmp_path, _complete_dockerfile())
    alternate = tmp_path / "uninspected.Dockerfile"
    alternate.write_text("FROM python:3.11\n", encoding="utf-8")
    compose = tmp_path / "docker-compose.yml"
    compose.write_text(
        compose.read_text(encoding="utf-8").replace(
            "./src/services/query_service/Dockerfile", "./uninspected.Dockerfile"
        ),
        encoding="utf-8",
    )

    findings = find_image_provenance_findings(tmp_path)

    assert any("selects an uninspected Dockerfile" in finding.detail for finding in findings)


def test_image_provenance_guard_rejects_coupled_scan_policy_exit(tmp_path: Path) -> None:
    _write_required_sources(tmp_path)
    workflow = tmp_path / ".github" / "workflows" / "image-release.yml"
    workflow.write_text(
        workflow.read_text(encoding="utf-8").replace("--exit-code 0", "--exit-code 1"),
        encoding="utf-8",
    )
    _write_dockerfile(tmp_path, _complete_dockerfile())

    findings = find_image_provenance_findings(tmp_path)

    assert any("must not couple report creation" in finding.detail for finding in findings)


def test_image_provenance_guard_rejects_scan_policy_ordering_drift(tmp_path: Path) -> None:
    _write_required_sources(tmp_path)
    workflow = tmp_path / ".github" / "workflows" / "image-release.yml"
    content = workflow.read_text(encoding="utf-8")
    content = content.replace(
        "python -m scripts.release.image_scan_policy enforce",
        "write_image_release_manifest.py\npython -m scripts.release.image_scan_policy enforce",
    )
    workflow.write_text(content, encoding="utf-8")
    _write_dockerfile(tmp_path, _complete_dockerfile())

    findings = find_image_provenance_findings(tmp_path)

    assert any(
        "must be generated, uploaded, and enforced" in finding.detail for finding in findings
    )


def test_image_provenance_guard_rejects_workflow_level_write_permissions(
    tmp_path: Path,
) -> None:
    _write_required_sources(tmp_path)
    workflow = tmp_path / ".github" / "workflows" / "image-release.yml"
    workflow.write_text(
        workflow.read_text(encoding="utf-8").replace(
            "permissions:\n  contents: read\n",
            "permissions:\n  contents: read\n  packages: write\n",
            1,
        ),
        encoding="utf-8",
    )
    _write_dockerfile(tmp_path, _complete_dockerfile())

    findings = find_image_provenance_findings(tmp_path)

    assert any("read-only by default" in finding.detail for finding in findings)


def test_image_provenance_guard_rejects_release_operation_in_diagnostic_job(
    tmp_path: Path,
) -> None:
    _write_required_sources(tmp_path)
    workflow = tmp_path / ".github" / "workflows" / "image-release.yml"
    workflow.write_text(
        workflow.read_text(encoding="utf-8").replace("--load", "--push", 1),
        encoding="utf-8",
    )
    _write_dockerfile(tmp_path, _complete_dockerfile())

    findings = find_image_provenance_findings(tmp_path)

    assert any(
        "diagnostic image job contains release operation --push" in finding.detail
        for finding in findings
    )


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

    assert any(
        "effective final-stage OCI label org.opencontainers.image.digest" in f.detail
        for f in findings
    )


def test_image_provenance_guard_rejects_volatile_metadata_before_build_layers(
    tmp_path: Path,
) -> None:
    _write_required_sources(tmp_path)
    _write_dockerfile(
        tmp_path,
        _complete_dockerfile().replace("RUN install-dependencies\n", "")
        + "\nRUN install-dependencies\n",
    )

    findings = find_image_provenance_findings(tmp_path)

    assert any("labels must follow dependency-install RUN layers" in f.detail for f in findings)
    assert any(
        "runtime provenance must follow dependency-install RUN layers" in f.detail for f in findings
    )


def test_image_provenance_guard_rejects_volatile_arg_before_build_layers(
    tmp_path: Path,
) -> None:
    _write_required_sources(tmp_path)
    _write_dockerfile(
        tmp_path,
        _complete_dockerfile()
        .replace("RUN install-dependencies\n", "")
        .replace(
            "ARG LOTUS_BUILD_TIMESTAMP\n",
            "ARG LOTUS_BUILD_TIMESTAMP\nRUN install-dependencies\n",
        ),
    )

    findings = find_image_provenance_findings(tmp_path)

    assert any(
        "LOTUS_BUILD_TIMESTAMP must follow dependency-install RUN layers" in f.detail
        for f in findings
    )


def test_image_provenance_guard_parses_run_case_insensitively(tmp_path: Path) -> None:
    _write_required_sources(tmp_path)
    _write_dockerfile(
        tmp_path,
        _complete_dockerfile() + "\n  run install-more-dependencies\n",
    )

    findings = find_image_provenance_findings(tmp_path)

    assert any("labels must follow dependency-install RUN layers" in f.detail for f in findings)
    assert any(
        "runtime provenance must follow dependency-install RUN layers" in f.detail for f in findings
    )


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
