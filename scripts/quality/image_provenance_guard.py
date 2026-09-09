"""Validate Lotus Core image provenance labels and runtime metadata endpoints."""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
RELEASE_WORKFLOW = Path(".github/workflows/image-release.yml")
LOCAL_BUILD_SCRIPT = Path("scripts/release/local_image_build.py")

REQUIRED_METADATA_ARGS = (
    "LOTUS_GIT_COMMIT_SHA",
    "LOTUS_GIT_BRANCH",
    "LOTUS_BUILD_TIMESTAMP",
    "LOTUS_REPO_URL",
    "LOTUS_IMAGE_VERSION",
    "LOTUS_IMAGE_DIGEST",
    "LOTUS_CI_RUN_ID",
)

EXPECTED_COMPOSE_ARGS = {
    "LOTUS_GIT_COMMIT_SHA": "${LOTUS_GIT_COMMIT_SHA:-unknown}",
    "LOTUS_GIT_BRANCH": "${LOTUS_GIT_BRANCH:-unknown}",
    "LOTUS_BUILD_TIMESTAMP": "${LOTUS_BUILD_TIMESTAMP:-unknown}",
    "LOTUS_REPO_URL": "${LOTUS_REPO_URL:-unknown}",
    "LOTUS_IMAGE_VERSION": "${LOTUS_IMAGE_VERSION:-unknown}",
    "LOTUS_IMAGE_DIGEST": "${LOTUS_IMAGE_DIGEST:-unavailable-before-push}",
    "LOTUS_CI_RUN_ID": "${LOTUS_CI_RUN_ID:-unavailable-local-build}",
}

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
    "fail-fast: false",
    "github.event_name == 'workflow_dispatch'",
    "packages: write",
    "id-token: write",
    "docker buildx build",
    "--push",
    '--tag "${{ steps.meta.outputs.image_tag }}"',
    "${GITHUB_SHA}",
    "--sbom=true",
    "--provenance=true",
    "aquasec/trivy",
    "--exit-code 0",
    "--scanners vuln,secret",
    "known_exploited_vulnerabilities.json",
    "curl --fail --location --silent --show-error",
    "--proto '=https' --proto-redir '=https' --max-redirs 3",
    "--retry 3 --retry-all-errors --connect-timeout 10 --max-time 60",
    "--severity UNKNOWN,LOW,MEDIUM,HIGH,CRITICAL",
    "--kev-catalog",
    "--kev-fetched-at",
    "--exception-register",
    "--exception-schema",
    "raw.githubusercontent.com/sgajbi/lotus-platform/2868348d289fc685ecf5a218b6c73256ac3a7742",
    "python -m scripts.release.image_scan_policy evaluate",
    "python -m scripts.release.image_scan_policy unavailable",
    "cisa_kev_fetch_failed",
    "trivy_scan_failed",
    "evidence_evaluation_failed",
    "exception_schema_fetch_failed",
    "Upload image scan policy receipt",
    "image-scan-policy-${{ matrix.service }}-attempt-${{ github.run_attempt }}",
    "if: ${{ always() }}",
    "if-no-files-found: error",
    "python -m scripts.release.image_scan_policy enforce",
    "--enforced-at",
    "--format cyclonedx",
    "-sbom.cdx.json",
    "cosign sign --yes",
    "cosign verify",
    "cosign attest --yes --type slsaprovenance1",
    "cosign verify-attestation",
    "write_slsa_provenance_predicate",
    "write_image_release_manifest.py",
    '--image-digest "${{ steps.digest.outputs.image_digest }}"',
    "--scan-receipt",
    "--authority-bundle",
    "--signature-verification",
    "--provenance-verification",
    "--base-lifecycle-inventory",
    "--base-manifest-evidence",
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


def _make_logical_lines(makefile: str) -> list[str]:
    lines: list[str] = []
    continued = ""
    for physical_line in makefile.splitlines():
        if continued:
            continued = f"{continued} {physical_line.lstrip()}"
        else:
            continued = physical_line
        if continued and not continued[0].isspace() and continued.endswith("\\"):
            continued = continued[:-1].rstrip()
            continue
        lines.append(continued)
        continued = ""
    if continued:
        lines.append(continued)
    return lines


def _make_target_recipes(makefile: str, target: str) -> list[str]:
    lines = _make_logical_lines(makefile)
    recipes: list[str] = []
    for offset, line in enumerate(lines):
        if not line or line[0].isspace() or ":" not in line:
            continue
        rule_targets = line.partition(":")[0].split()
        dynamic_target = any("$" in rule_target for rule_target in rule_targets)
        if target not in rule_targets and not dynamic_target:
            continue
        recipe: list[str] = []
        for candidate in lines[offset + 1 :]:
            if candidate.startswith("\t"):
                command = candidate[1:].lstrip().lstrip("@+-").lstrip()
                executable = command.split("#", maxsplit=1)[0].rstrip()
                if executable:
                    recipe.append(executable)
                continue
            if not candidate.strip() or candidate.lstrip().startswith("#"):
                continue
            break
        recipes.append("\n".join(recipe))
    return recipes


def _dockerfile_instructions(content: str) -> list[tuple[str, str]]:
    instructions: list[tuple[str, str]] = []
    logical_line = ""
    for physical_line in content.splitlines():
        stripped = physical_line.strip()
        if not logical_line and (not stripped or stripped.startswith("#")):
            continue
        continued = stripped.endswith("\\")
        fragment = stripped[:-1].rstrip() if continued else stripped
        logical_line = f"{logical_line} {fragment}".strip()
        if continued:
            continue
        instruction, separator, arguments = logical_line.partition(" ")
        instructions.append((instruction.upper(), arguments if separator else ""))
        logical_line = ""
    if logical_line:
        instruction, separator, arguments = logical_line.partition(" ")
        instructions.append((instruction.upper(), arguments if separator else ""))
    return instructions


def _effective_assignments(content: str, instruction_name: str) -> dict[str, str]:
    effective: dict[str, str] = {}
    for instruction, arguments in _dockerfile_instructions(content):
        if instruction != instruction_name:
            continue
        tokens = shlex.split(arguments, posix=True)
        if tokens and "=" not in tokens[0]:
            effective[tokens[0]] = " ".join(tokens[1:])
            continue
        for token in tokens:
            key, separator, value = token.partition("=")
            if separator:
                effective[key] = value
    return effective


def _dockerfile_findings(root: Path) -> list[ImageProvenanceFinding]:
    findings: list[ImageProvenanceFinding] = []
    for dockerfile in sorted((root / "src" / "services").rglob("Dockerfile")):
        content = dockerfile.read_text(encoding="utf-8")
        instructions = _dockerfile_instructions(content)
        if any(instruction == "ADD" for instruction, _ in instructions):
            findings.append(
                ImageProvenanceFinding(
                    _relative(dockerfile, root),
                    "Dockerfile ADD is not permitted at the local provenance boundary",
                )
            )
        for instruction, arguments in instructions:
            if instruction != "RUN":
                continue
            for token in shlex.split(arguments):
                if not token.startswith("--mount="):
                    continue
                mount_options = dict(
                    option.partition("=")[::2]
                    for option in token.removeprefix("--mount=").split(",")
                )
                if mount_options.get("type", "bind") == "bind":
                    findings.append(
                        ImageProvenanceFinding(
                            _relative(dockerfile, root),
                            "Dockerfile context bind mounts are not permitted",
                        )
                    )
        offset = 0
        from_offsets: list[int] = []
        for physical_line in content.splitlines(keepends=True):
            tokens = physical_line.lstrip().split(maxsplit=1)
            if tokens and tokens[0].upper() == "FROM":
                from_offsets.append(offset)
            offset += len(physical_line)
        final_stage = content[from_offsets[-1] :] if from_offsets else ""
        effective_labels = _effective_assignments(final_stage, "LABEL")
        effective_environment = _effective_assignments(final_stage, "ENV")
        stage_offset = 0
        stage_run_offsets: list[int] = []
        for physical_line in final_stage.splitlines(keepends=True):
            tokens = physical_line.lstrip().split(maxsplit=1)
            if tokens and tokens[0].upper() == "RUN":
                stage_run_offsets.append(stage_offset)
            stage_offset += len(physical_line)
        last_stage_run = max(stage_run_offsets, default=-1)
        for line_number, line in enumerate(content.splitlines(), start=1):
            stripped = line.strip()
            tokens = stripped.split(maxsplit=1)
            if len(tokens) < 2 or tokens[0].upper() not in {"ARG", "ENV"}:
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
            stage_declaration = f"\nARG {arg_name}\n"
            if final_stage.count(stage_declaration) != 1:
                findings.append(
                    ImageProvenanceFinding(
                        _relative(dockerfile, root),
                        f"missing final-stage build arg {arg_name}",
                    )
                )
            elif final_stage.find(stage_declaration) < last_stage_run:
                findings.append(
                    ImageProvenanceFinding(
                        _relative(dockerfile, root),
                        f"volatile build arg {arg_name} must follow dependency-install RUN layers",
                    )
                )
            if effective_environment.get(arg_name) != f"${{{arg_name}}}":
                findings.append(
                    ImageProvenanceFinding(
                        _relative(dockerfile, root),
                        f"missing or incorrect effective final-stage runtime env {arg_name}",
                    )
                )
        for label_name, arg_name in REQUIRED_OCI_LABELS.items():
            if effective_labels.get(label_name) != f"${{{arg_name}}}":
                findings.append(
                    ImageProvenanceFinding(
                        _relative(dockerfile, root),
                        f"missing or incorrect effective final-stage OCI label {label_name}",
                    )
                )
        if final_stage.rfind("\nLABEL org.opencontainers.image.revision=") < last_stage_run:
            findings.append(
                ImageProvenanceFinding(
                    _relative(dockerfile, root),
                    "volatile OCI provenance labels must follow dependency-install RUN layers",
                )
            )
        if final_stage.rfind("\nENV LOTUS_GIT_COMMIT_SHA=") < last_stage_run:
            findings.append(
                ImageProvenanceFinding(
                    _relative(dockerfile, root),
                    "volatile runtime provenance must follow dependency-install RUN layers",
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

    try:
        workflow = yaml.safe_load(workflow_content)
        jobs = workflow["jobs"]
        release_job = jobs["publish-images"]
        diagnostic_job = jobs["diagnose-images"]
        prepare_job = jobs["prepare-image-matrix"]
    except (KeyError, TypeError, yaml.YAMLError) as exc:
        findings.append(
            ImageProvenanceFinding(
                RELEASE_WORKFLOW,
                f"image release workflow trust boundary is not parseable: {exc}",
            )
        )
    else:
        if workflow.get("permissions") != {"contents": "read"}:
            findings.append(
                ImageProvenanceFinding(
                    RELEASE_WORKFLOW,
                    "image release workflow must be read-only by default",
                )
            )
        expected_release_condition = (
            "${{ github.ref == 'refs/heads/main' || startsWith(github.ref, 'refs/tags/v') }}"
        )
        if " ".join(str(release_job.get("if", "")).split()) != expected_release_condition:
            findings.append(
                ImageProvenanceFinding(
                    RELEASE_WORKFLOW,
                    "image publication must be limited to main and version tags",
                )
            )
        if release_job.get("permissions") != {
            "contents": "read",
            "id-token": "write",
            "packages": "write",
        }:
            findings.append(
                ImageProvenanceFinding(
                    RELEASE_WORKFLOW,
                    "release write permissions must be scoped to the trusted publish job",
                )
            )
        expected_diagnostic_condition = (
            "${{ github.event_name == 'workflow_dispatch' && "
            "github.ref != 'refs/heads/main' && !startsWith(github.ref, 'refs/tags/v') }}"
        )
        if " ".join(str(diagnostic_job.get("if", "")).split()) != expected_diagnostic_condition:
            findings.append(
                ImageProvenanceFinding(
                    RELEASE_WORKFLOW,
                    "feature dispatch must be isolated in the diagnostic job",
                )
            )
        if diagnostic_job.get("permissions") != {"contents": "read"}:
            findings.append(
                ImageProvenanceFinding(
                    RELEASE_WORKFLOW,
                    "diagnostic image scans must remain read-only",
                )
            )
        diagnostic_text = str(diagnostic_job)
        for forbidden in (
            "docker login",
            "--push",
            "cosign",
            "write_image_release_manifest.py",
            "render_release_deployment.py",
            "--promotion-environments",
            "--format cyclonedx",
        ):
            if forbidden in diagnostic_text:
                findings.append(
                    ImageProvenanceFinding(
                        RELEASE_WORKFLOW,
                        f"diagnostic image job contains release operation {forbidden}",
                    )
                )
        for required in (
            "--load",
            "--evidence-posture diagnostic",
            "--expected-evidence-posture diagnostic",
        ):
            if required not in diagnostic_text:
                findings.append(
                    ImageProvenanceFinding(
                        RELEASE_WORKFLOW,
                        f"diagnostic image job missing {required}",
                    )
                )
        release_matrix = release_job.get("strategy", {}).get("matrix")
        diagnostic_matrix = diagnostic_job.get("strategy", {}).get("matrix")
        if release_matrix != diagnostic_matrix or "write_image_build_matrix" not in str(
            prepare_job
        ):
            findings.append(
                ImageProvenanceFinding(
                    RELEASE_WORKFLOW,
                    "release and diagnostic jobs must share one source-owned image matrix",
                )
            )

    ordered_release_steps = (
        "python -m scripts.release.image_scan_policy evaluate",
        "Upload image scan policy receipt",
        "python -m scripts.release.image_scan_policy enforce",
        "cosign sign --yes",
        "cosign verify",
        "cosign attest --yes --type slsaprovenance1",
        "cosign verify-attestation",
        "Re-verify scan receipt at manifest boundary",
        "write_image_release_manifest.py",
    )
    step_offsets = [workflow_content.find(step) for step in ordered_release_steps]
    if any(offset < 0 for offset in step_offsets) or step_offsets != sorted(step_offsets):
        findings.append(
            ImageProvenanceFinding(
                RELEASE_WORKFLOW,
                "image scan receipt must be generated, uploaded, and enforced before "
                "signing and manifest generation",
            )
        )
    if "--exit-code 1" in workflow_content:
        findings.append(
            ImageProvenanceFinding(
                RELEASE_WORKFLOW,
                "image scan evidence generation must not couple report creation to "
                "policy exit status",
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
        if relative == Path("scripts/quality/image_provenance_guard.py"):
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

    prebuild = root / "scripts" / "release" / "prebuild_ci_images.py"
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

    build_provenance = root / "scripts" / "release" / "write_build_provenance.py"
    build_provenance_content = build_provenance.read_text(encoding="utf-8")
    if "image_build_metadata" not in build_provenance_content:
        findings.append(
            ImageProvenanceFinding(
                _relative(build_provenance, root),
                "build provenance manifest omits image metadata",
            )
        )
    release_manifest = root / "scripts" / "release" / "write_image_release_manifest.py"
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


def _local_build_path_findings(root: Path) -> list[ImageProvenanceFinding]:
    findings: list[ImageProvenanceFinding] = []
    compose_path = root / "docker-compose.yml"
    inspected_dockerfiles = {
        dockerfile.resolve() for dockerfile in (root / "src" / "services").rglob("Dockerfile")
    }
    try:
        compose = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
        services = compose["services"]
    except (KeyError, TypeError, yaml.YAMLError) as exc:
        return [
            ImageProvenanceFinding(
                _relative(compose_path, root),
                f"cannot inspect local Compose build provenance: {exc}",
            )
        ]

    if compose.get("include") is not None:
        findings.append(
            ImageProvenanceFinding(
                _relative(compose_path, root),
                "Compose include is not permitted at the local image build boundary",
            )
        )

    for service_name, service in services.items():
        if isinstance(service, dict) and service.get("extends") is not None:
            findings.append(
                ImageProvenanceFinding(
                    _relative(compose_path, root),
                    f"Compose build {service_name} must not inherit an uninspected configuration",
                )
            )
        build = service.get("build") if isinstance(service, dict) else None
        if build is None:
            continue
        if not isinstance(build, dict):
            findings.append(
                ImageProvenanceFinding(
                    _relative(compose_path, root),
                    f"Compose build {service_name} must use mapping form with provenance args",
                )
            )
            continue
        if build.get("context") != ".":
            findings.append(
                ImageProvenanceFinding(
                    _relative(compose_path, root),
                    f"Compose build {service_name} must use the governed repository context",
                )
            )
        if build.get("additional_contexts") is not None:
            findings.append(
                ImageProvenanceFinding(
                    _relative(compose_path, root),
                    f"Compose build {service_name} must not use additional build contexts",
                )
            )
        for external_input in ("secrets", "ssh"):
            if build.get(external_input) is not None:
                findings.append(
                    ImageProvenanceFinding(
                        _relative(compose_path, root),
                        f"Compose build {service_name} must not use external {external_input}",
                    )
                )
        build_labels = build.get("labels")
        if isinstance(build_labels, dict):
            overridden_labels = set(build_labels)
        elif isinstance(build_labels, list):
            overridden_labels = {
                item.partition("=")[0] for item in build_labels if isinstance(item, str)
            }
        else:
            overridden_labels = set()
        for label_name in REQUIRED_OCI_LABELS:
            if label_name in overridden_labels:
                findings.append(
                    ImageProvenanceFinding(
                        _relative(compose_path, root),
                        f"Compose build {service_name} overrides provenance label {label_name}",
                    )
                )
        selected_dockerfile = build.get("dockerfile")
        if not isinstance(selected_dockerfile, str):
            findings.append(
                ImageProvenanceFinding(
                    _relative(compose_path, root),
                    f"Compose build {service_name} must select an inspected Dockerfile",
                )
            )
        elif (root / selected_dockerfile).resolve() not in inspected_dockerfiles:
            findings.append(
                ImageProvenanceFinding(
                    _relative(compose_path, root),
                    f"Compose build {service_name} selects an uninspected Dockerfile",
                )
            )
        if build.get("target") is not None:
            findings.append(
                ImageProvenanceFinding(
                    _relative(compose_path, root),
                    f"Compose build {service_name} must use the inspected final Docker stage",
                )
            )
        environment = service.get("environment")
        if isinstance(environment, dict):
            runtime_overrides = set(environment)
        elif isinstance(environment, list):
            runtime_overrides = {
                item.partition("=")[0] for item in environment if isinstance(item, str)
            }
        else:
            runtime_overrides = set()
        for arg_name in REQUIRED_METADATA_ARGS:
            if arg_name in runtime_overrides:
                findings.append(
                    ImageProvenanceFinding(
                        _relative(compose_path, root),
                        f"Compose build {service_name} overrides runtime provenance {arg_name}",
                    )
                )
        if service.get("env_file") is not None:
            findings.append(
                ImageProvenanceFinding(
                    _relative(compose_path, root),
                    f"Compose build {service_name} must not use an uninspected env_file",
                )
            )
        args = build.get("args")
        for arg_name in REQUIRED_METADATA_ARGS:
            if not isinstance(args, dict) or arg_name not in args:
                findings.append(
                    ImageProvenanceFinding(
                        _relative(compose_path, root),
                        f"Compose build {service_name} does not receive {arg_name}",
                    )
                )
            elif args[arg_name] != EXPECTED_COMPOSE_ARGS[arg_name]:
                findings.append(
                    ImageProvenanceFinding(
                        _relative(compose_path, root),
                        f"Compose build {service_name} does not bind "
                        f"{arg_name} to its source value",
                    )
                )

    makefile_path = root / "Makefile"
    makefile = makefile_path.read_text(encoding="utf-8")
    repository_python_bindings = [
        line.strip()
        for line in _make_logical_lines(makefile)
        if re.match(r"^(?:override\s+)?REPOSITORY_PYTHON\s*[:+?]?=", line.strip())
    ]
    if repository_python_bindings != [
        "override REPOSITORY_PYTHON := python scripts/development/repository_python.py"
    ]:
        findings.append(
            ImageProvenanceFinding(
                _relative(makefile_path, root),
                "REPOSITORY_PYTHON must have one non-overridable governed binding",
            )
        )
    for line in _make_logical_lines(makefile):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if re.search(r"\$[({]\s*eval(?:\s|[)}])", line):
            findings.append(
                ImageProvenanceFinding(
                    _relative(makefile_path, root),
                    "Makefile eval is not permitted at the local image build boundary",
                )
            )
            break
        if line.startswith("\t"):
            continue
        directive = line.lstrip().split(maxsplit=1)[0]
        if directive in {"include", "-include", "sinclude"}:
            findings.append(
                ImageProvenanceFinding(
                    _relative(makefile_path, root),
                    "Makefile includes are not permitted at the local image build boundary",
                )
            )
            break
    for target, operation in (("docker-build", "docker-build"), ("docker-up", "compose-up")):
        expected = f"$(REPOSITORY_PYTHON) scripts/release/local_image_build.py {operation}"
        if _make_target_recipes(makefile, target) != [expected]:
            findings.append(
                ImageProvenanceFinding(
                    _relative(makefile_path, root),
                    f"{target} must route through the source-derived local image build boundary",
                )
            )

    build_script = root / LOCAL_BUILD_SCRIPT
    if not build_script.exists():
        findings.append(
            ImageProvenanceFinding(LOCAL_BUILD_SCRIPT, "missing local image build boundary")
        )
        return findings
    script_content = build_script.read_text(encoding="utf-8")
    for required in (
        "git_commit_sha",
        '"core.fileMode=true"',
        '"status",',
        "unavailable-before-push",
        "unavailable-local-build",
    ):
        if required not in script_content:
            findings.append(
                ImageProvenanceFinding(
                    LOCAL_BUILD_SCRIPT,
                    f"local image build boundary omits {required}",
                )
            )
    if "shell=True" in script_content:
        findings.append(
            ImageProvenanceFinding(
                LOCAL_BUILD_SCRIPT,
                "local Git-derived values must not pass through a shell",
            )
        )
    return findings


def find_image_provenance_findings(root: Path = REPO_ROOT) -> list[ImageProvenanceFinding]:
    return [
        *_dockerfile_findings(root),
        *_release_workflow_findings(root),
        *_kubernetes_digest_findings(root),
        *_source_contract_findings(root),
        *_local_build_path_findings(root),
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
