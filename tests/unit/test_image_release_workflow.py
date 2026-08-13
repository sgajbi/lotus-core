"""Failure-path evidence contracts for the immutable image release workflow."""

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "image-release.yml"


def _steps() -> list[dict[str, object]]:
    workflow = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
    return workflow["jobs"]["publish-images"]["steps"]


def _step(name: str) -> dict[str, object]:
    return next(step for step in _steps() if step.get("name") == name)


def _workflow() -> dict[str, object]:
    return yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))


def test_publish_boundary_is_limited_to_main_and_version_tags() -> None:
    workflow = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
    release_job = workflow["jobs"]["publish-images"]

    assert "workflow_dispatch" in workflow[True]
    assert " ".join(str(release_job["if"]).split()) == (
        "${{ github.ref == 'refs/heads/main' || startsWith(github.ref, 'refs/tags/v') }}"
    )
    assert workflow["permissions"] == {"contents": "read"}
    assert release_job["permissions"] == {
        "contents": "read",
        "id-token": "write",
        "packages": "write",
    }


def test_manual_feature_dispatch_is_diagnostic_and_non_release_shaped() -> None:
    workflow = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
    diagnostic_job = workflow["jobs"]["diagnose-images"]
    release_job = workflow["jobs"]["publish-images"]

    assert " ".join(str(diagnostic_job["if"]).split()) == (
        "${{ github.event_name == 'workflow_dispatch' && "
        "github.ref != 'refs/heads/main' && !startsWith(github.ref, 'refs/tags/v') }}"
    )
    assert diagnostic_job["permissions"] == {"contents": "read"}
    assert diagnostic_job["strategy"]["matrix"] == release_job["strategy"]["matrix"]
    diagnostic_text = yaml.safe_dump(diagnostic_job)
    for forbidden in (
        "docker login",
        "--push",
        "cosign",
        "write_image_release_manifest.py",
        "render_release_deployment.py",
        "--promotion-environments",
        "--format cyclonedx",
    ):
        assert forbidden not in diagnostic_text
    for required in (
        "--load",
        "--evidence-posture diagnostic",
        "--expected-evidence-posture diagnostic",
    ):
        assert required in diagnostic_text


def test_image_matrix_has_one_source_owned_generator() -> None:
    workflow = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
    prepare = workflow["jobs"]["prepare-image-matrix"]

    assert prepare["outputs"]["matrix"] == "${{ steps.matrix.outputs.matrix }}"
    assert "write_image_build_matrix" in str(prepare["steps"])


def test_one_vulnerability_authority_is_bound_and_uploaded_per_attempt() -> None:
    workflow = _workflow()
    authority = workflow["jobs"]["prepare-vulnerability-authority"]
    steps = authority["steps"]
    prepare = next(
        step
        for step in steps
        if step.get("name") == "Fetch and bind workflow vulnerability authority"
    )
    upload = next(
        step for step in steps if step.get("name") == "Upload workflow vulnerability authority"
    )
    command = str(prepare["run"])

    assert command.count("known_exploited_vulnerabilities.json") == 1
    assert command.count("vulnerability-exception-register.schema.json") >= 2
    assert "vulnerability_authority_bundle create" in command
    assert "vulnerability_authority_bundle unavailable" in command
    for reason in (
        "cisa_kev_fetch_failed",
        "exception_schema_fetch_failed",
        "authority_validation_failed",
    ):
        assert reason in command
    assert upload["if"] == "${{ always() }}"
    assert upload["with"]["name"] == ("vulnerability-authority-attempt-${{ github.run_attempt }}")
    assert upload["with"]["if-no-files-found"] == "error"


def test_all_image_jobs_consume_the_same_attempt_authority() -> None:
    workflow = _workflow()
    for job_name in ("publish-images", "diagnose-images"):
        job = workflow["jobs"][job_name]
        assert job["needs"] == ["prepare-image-matrix", "prepare-vulnerability-authority"]
        download = next(
            step
            for step in job["steps"]
            if step.get("name") == "Download workflow vulnerability authority"
        )
        assert download["uses"] == "actions/download-artifact@v8"
        assert download["with"] == {
            "name": "vulnerability-authority-attempt-${{ github.run_attempt }}",
            "path": "output/vulnerability-authority",
        }
        job_text = yaml.safe_dump(job)
        scan_step = next(
            step
            for step in job["steps"]
            if step.get("name")
            in {
                "Generate image vulnerability and secret policy receipt",
                "Generate diagnostic image scan receipt",
            }
        )
        assert "vulnerability_authority_bundle verify" in str(scan_step["run"])
        assert "output/vulnerability-authority/cisa-kev.json" in job_text
        assert (
            "output/vulnerability-authority/vulnerability-exception-register.schema.json"
            in job_text
        )
        assert "curl --fail" not in job_text


def test_image_scan_generates_receipt_before_policy_enforcement() -> None:
    steps = _steps()
    names = [step.get("name") for step in steps]

    generate_index = names.index("Generate image vulnerability and secret policy receipt")
    upload_index = names.index("Upload image scan policy receipt")
    enforce_index = names.index("Enforce image vulnerability and secret policy")
    sign_index = names.index("Sign image digest")

    assert generate_index < upload_index < enforce_index < sign_index
    generate = str(steps[generate_index]["run"])
    assert "--exit-code 0" in generate
    assert "--scanners vuln,secret" in generate
    assert "vulnerability_authority_bundle verify" in generate
    assert "--severity UNKNOWN,LOW,MEDIUM,HIGH,CRITICAL" in generate
    assert "--kev-catalog" in generate
    assert "--authority-bundle" in generate
    assert "--kev-fetched-at" in generate
    assert "--exception-register" in generate
    assert "--exception-schema" in generate
    assert "python -m scripts.release.image_scan_policy evaluate" in generate
    assert "python -m scripts.release.image_scan_policy unavailable" in generate
    for reason_code in (
        "trivy_scan_failed",
        "evidence_evaluation_failed",
    ):
        assert reason_code in generate
    assert "python -m scripts.release.image_scan_policy enforce" in str(steps[enforce_index]["run"])
    assert '--report "output/build-evidence/${{ matrix.service }}-trivy.json"' in str(
        steps[enforce_index]["run"]
    )
    assert '--kev-catalog "output/vulnerability-authority/cisa-kev.json"' in str(
        steps[enforce_index]["run"]
    )
    assert "--exception-register" in str(steps[enforce_index]["run"])
    assert "--authority-bundle" in str(steps[enforce_index]["run"])
    assert (
        '--exception-schema "output/vulnerability-authority/'
        'vulnerability-exception-register.schema.json"' in str(steps[enforce_index]["run"])
    )
    assert "--enforced-at" in str(steps[enforce_index]["run"])


def test_manifest_consumes_verified_same_artifact_evidence() -> None:
    steps = _steps()
    names = [step.get("name") for step in steps]
    ordered = [
        "Enforce image vulnerability and secret policy",
        "Export image SBOM",
        "Sign image digest",
        "Verify image signature identity",
        "Attest source-bound SLSA provenance",
        "Verify signed provenance identity",
        "Re-verify scan receipt at manifest boundary",
        "Write image release manifest",
    ]

    assert [names.index(name) for name in ordered] == sorted(names.index(name) for name in ordered)
    manifest = str(_step("Write image release manifest")["run"])
    boundary_enforcement = str(_step("Re-verify scan receipt at manifest boundary")["run"])
    assert "python -m scripts.release.image_scan_policy enforce" in boundary_enforcement
    assert '--report "output/build-evidence/${{ matrix.service }}-trivy.json"' in (
        boundary_enforcement
    )
    assert '--expected-image-digest "${{ steps.digest.outputs.image_digest }}"' in (
        boundary_enforcement
    )
    for required in (
        "--scan-receipt",
        "--authority-bundle",
        "--sbom",
        "--signature-verification",
        "--provenance-verification",
        "--base-lifecycle-inventory",
        "--base-manifest-evidence",
        "--dockerfile",
    ):
        assert required in manifest
    for removed_assertion in (
        "--sbom-generated",
        "--vulnerability-scan-status",
        "--image-signed",
        "--provenance-attestation-generated",
        "--promotion-environments",
    ):
        assert removed_assertion not in manifest


def test_candidate_workflow_does_not_claim_unperformed_environment_promotion() -> None:
    names = [step.get("name") for step in _steps()]
    workflow_text = WORKFLOW_PATH.read_text(encoding="utf-8")

    assert "Render immutable Kubernetes release" not in names
    assert "--promotion-environments dev uat prod" not in workflow_text
    assert "${{ matrix.service }}-kubernetes.yaml" not in workflow_text


def test_scan_receipt_upload_is_fail_closed_and_runs_after_failed_generation() -> None:
    upload = _step("Upload image scan policy receipt")

    assert upload["if"] == "${{ always() }}"
    assert upload["uses"] == "actions/upload-artifact@v7"
    assert upload["with"] == {
        "name": "image-scan-policy-${{ matrix.service }}-attempt-${{ github.run_attempt }}",
        "path": "output/build-evidence/${{ matrix.service }}-image-scan-policy.json",
        "if-no-files-found": "error",
        "retention-days": 90,
    }


def test_successful_release_evidence_does_not_duplicate_policy_receipt() -> None:
    final_upload = _step("Upload image release evidence")
    paths = str(final_upload["with"]["path"])

    assert "${{ matrix.service }}-image-scan-policy.json" not in paths
    assert "${{ matrix.service }}-trivy.json" not in paths
    assert "${{ matrix.service }}-cisa-kev.json" not in paths
