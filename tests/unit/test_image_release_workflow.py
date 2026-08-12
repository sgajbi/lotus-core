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


def test_manual_dispatch_can_certify_an_exact_feature_sha() -> None:
    workflow = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
    release_job = workflow["jobs"]["publish-images"]

    assert "workflow_dispatch" in workflow[True]
    assert " ".join(str(release_job["if"]).split()) == (
        "${{ github.event_name == 'workflow_dispatch' || "
        "github.ref == 'refs/heads/main' || startsWith(github.ref, 'refs/tags/') }}"
    )


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
    assert "known_exploited_vulnerabilities.json" in generate
    assert "curl --fail --location --silent --show-error" in generate
    assert "--proto '=https' --proto-redir '=https' --max-redirs 3" in generate
    assert "--retry 3 --retry-all-errors --connect-timeout 10 --max-time 60" in generate
    assert "--severity UNKNOWN,LOW,MEDIUM,HIGH,CRITICAL" in generate
    assert "--kev-catalog" in generate
    assert "--kev-fetched-at" in generate
    assert "image_scan_policy.py evaluate" in generate
    assert "image_scan_policy.py unavailable" in generate
    for reason_code in (
        "cisa_kev_fetch_failed",
        "trivy_scan_failed",
        "evidence_evaluation_failed",
    ):
        assert reason_code in generate
    assert "image_scan_policy.py enforce" in str(steps[enforce_index]["run"])
    assert '--report "output/build-evidence/${{ matrix.service }}-trivy.json"' in str(
        steps[enforce_index]["run"]
    )
    assert '--kev-catalog "output/build-evidence/${{ matrix.service }}-cisa-kev.json"' in str(
        steps[enforce_index]["run"]
    )
    assert "--enforced-at" in str(steps[enforce_index]["run"])


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
