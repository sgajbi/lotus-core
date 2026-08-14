from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.quality import synthetic_fixture_leakage_guard as guard
from scripts.release.cisa_kev import (
    DEFAULT_COMPLETENESS_POLICY_PATH,
    load_cisa_kev_catalog,
)
from scripts.release.vulnerability_authority_bundle import (
    SCHEMA_VERSION as VULNERABILITY_AUTHORITY_SCHEMA_VERSION,
)

RUN_ID = "31758759912"
RUN_ATTEMPT = "1"
FULL_SHA = "a" * 40


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _minimal_standard(repo_root: Path) -> dict[str, object]:
    fixture_path = repo_root / "tests/fixtures/private-banking-portfolio-fixture.v1.json"
    _write(
        fixture_path,
        json.dumps(
            {
                "schema_version": "private-banking-portfolio-fixture.v1",
                "fixture_id": "private_banking_portfolio_fixture.v1",
                "synthetic_data": True,
                "safe_for_committed_tests": True,
                "relationships": {key: {} for key in guard.REQUIRED_RELATIONSHIPS},
            }
        ),
    )
    return {
        "schema_version": guard.SCHEMA_VERSION,
        "owning_repository": "lotus-core",
        "guard_command": guard.GUARD_COMMAND,
        "leakage_guard": {
            "scanned_path_globs": [
                "tests/fixtures/**/*",
                "docs/standards/synthetic-test-data-governance.v1.json",
            ],
            "optional_generated_evidence_globs": ["output/**/*.json"],
            "allowed_service_emails": ["support.ops@lotus.local"],
        },
        "canonical_synthetic_identifiers": [
            {
                "identifier": "CIF_SG_000184",
                "kind": "client_id",
                "synthetic_evidence": "test fixture",
            }
        ],
        "fixture_catalog": [
            {
                "fixture_id": "private_banking_portfolio_fixture.v1",
                "path": "tests/fixtures/private-banking-portfolio-fixture.v1.json",
                "synthetic_data": True,
                "relationship_coverage": sorted(guard.REQUIRED_RELATIONSHIPS),
                "safe_for_committed_tests": True,
            }
        ],
    }


def _write_standard(repo_root: Path, standard: dict[str, object]) -> Path:
    standard_path = repo_root / guard.STANDARD_PATH.relative_to(guard.REPO_ROOT)
    _write(standard_path, json.dumps(standard))
    return standard_path


def _canonical_sha256(value: dict[str, object]) -> str:
    content = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(content).hexdigest()


def _write_verified_cisa_authority(repo_root: Path) -> tuple[Path, Path]:
    authority_dir = (
        repo_root
        / "output"
        / "ci-evidence"
        / RUN_ID
        / f"vulnerability-authority-attempt-{RUN_ATTEMPT}"
    )
    kev_path = authority_dir / "cisa-kev.json"
    bundle_path = authority_dir / "vulnerability-authority-bundle.json"
    completeness_policy = json.loads(DEFAULT_COMPLETENESS_POLICY_PATH.read_text(encoding="utf-8"))
    entry_count = completeness_policy["minimum_entry_count"]
    vulnerabilities = [{"cveID": f"CVE-2026-{10000 + index}"} for index in range(entry_count)]
    vulnerabilities[0]["notes"] = (
        "https://lore.kernel.org/linux-cve-announce/20240610090330.1347021-2-lee@kernel.org/T/#u"
    )
    _write(
        kev_path,
        json.dumps(
            {
                "title": "CISA Catalog of Known Exploited Vulnerabilities",
                "catalogVersion": completeness_policy["baseline_catalog_version"],
                "dateReleased": completeness_policy["baseline_date_released_utc"],
                "count": entry_count,
                "vulnerabilities": vulnerabilities,
            }
        ),
    )
    cisa_kev_identity = load_cisa_kev_catalog(
        kev_path,
        fetched_at="2026-08-14T00:00:30Z",
    ).receipt_identity()
    payload: dict[str, object] = {
        "schema_version": VULNERABILITY_AUTHORITY_SCHEMA_VERSION,
        "generated_at_utc": "2026-08-14T00:01:00Z",
        "repository": guard.CORE_REPOSITORY_IDENTITY,
        "git_commit_sha": FULL_SHA,
        "ci_run_id": RUN_ID,
        "ci_run_attempt": RUN_ATTEMPT,
        "cisa_kev": cisa_kev_identity,
        "exception_schema": {
            "source_repository": "sgajbi/lotus-platform",
            "source_commit": "b" * 40,
            "source_path": "platform-contracts/vulnerability-exceptions/schema.json",
            "source_schema_id": "https://lotus-platform.local/schema.json",
            "source_schema_version": "lotus-platform.vulnerability-exception-register.v1",
            "source_git_blob_sha1": "c" * 40,
            "source_sha256": "sha256:" + "d" * 64,
        },
    }
    bundle = {**payload, "bundle_sha256": _canonical_sha256(payload)}
    _write(bundle_path, json.dumps(bundle))
    return kev_path, bundle_path


def _rewrite_bundle_digest(bundle_path: Path, bundle: dict[str, object]) -> None:
    payload = {key: value for key, value in bundle.items() if key != "bundle_sha256"}
    bundle["bundle_sha256"] = _canonical_sha256(payload)
    _write(bundle_path, json.dumps(bundle))


def test_synthetic_fixture_guard_accepts_current_repo_truth() -> None:
    assert guard.evaluate_synthetic_fixture_governance() == []


def test_synthetic_fixture_guard_accepts_minimal_valid_repo(tmp_path: Path) -> None:
    standard_path = _write_standard(tmp_path, _minimal_standard(tmp_path))

    assert (
        guard.evaluate_synthetic_fixture_governance(
            repo_root=tmp_path,
            standard_path=standard_path,
        )
        == []
    )


def test_synthetic_fixture_guard_accepts_digest_bound_cisa_source(tmp_path: Path) -> None:
    standard_path = _write_standard(tmp_path, _minimal_standard(tmp_path))
    _write_verified_cisa_authority(tmp_path)

    assert (
        guard.evaluate_synthetic_fixture_governance(
            repo_root=tmp_path,
            standard_path=standard_path,
        )
        == []
    )


def test_synthetic_fixture_guard_rejects_self_consistent_non_kev_pair(tmp_path: Path) -> None:
    standard_path = _write_standard(tmp_path, _minimal_standard(tmp_path))
    kev_path, bundle_path = _write_verified_cisa_authority(tmp_path)
    _write(kev_path, '{"contact":"forged@example.com"}')
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    bundle["cisa_kev"]["source_sha256"] = (
        "sha256:" + hashlib.sha256(kev_path.read_bytes()).hexdigest()
    )
    _rewrite_bundle_digest(bundle_path, bundle)

    findings = guard.evaluate_synthetic_fixture_governance(
        repo_root=tmp_path,
        standard_path=standard_path,
    )

    assert any(finding.rule == "personal-email-address" for finding in findings)


def test_verified_cisa_source_still_scans_non_email_leakage_rules(tmp_path: Path) -> None:
    standard_path = _write_standard(tmp_path, _minimal_standard(tmp_path))
    kev_path, bundle_path = _write_verified_cisa_authority(tmp_path)
    catalog = json.loads(kev_path.read_text(encoding="utf-8"))
    catalog["password"] = "concrete-secret"
    _write(kev_path, json.dumps(catalog))
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    bundle["cisa_kev"]["source_sha256"] = (
        "sha256:" + hashlib.sha256(kev_path.read_bytes()).hexdigest()
    )
    _rewrite_bundle_digest(bundle_path, bundle)

    findings = guard.evaluate_synthetic_fixture_governance(
        repo_root=tmp_path,
        standard_path=standard_path,
    )

    assert {finding.rule for finding in findings} == {"concrete-secret-field"}


def test_verified_cisa_source_rejects_arbitrary_added_email(tmp_path: Path) -> None:
    standard_path = _write_standard(tmp_path, _minimal_standard(tmp_path))
    kev_path, bundle_path = _write_verified_cisa_authority(tmp_path)
    catalog = json.loads(kev_path.read_text(encoding="utf-8"))
    catalog["contact"] = "client@example.com"
    _write(kev_path, json.dumps(catalog))
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    bundle["cisa_kev"]["source_sha256"] = (
        "sha256:" + hashlib.sha256(kev_path.read_bytes()).hexdigest()
    )
    _rewrite_bundle_digest(bundle_path, bundle)

    findings = guard.evaluate_synthetic_fixture_governance(
        repo_root=tmp_path,
        standard_path=standard_path,
    )

    assert {finding.rule for finding in findings} == {"personal-email-address"}


def test_synthetic_fixture_guard_rejects_path_only_authority_spoof(tmp_path: Path) -> None:
    standard_path = _write_standard(tmp_path, _minimal_standard(tmp_path))
    spoof_path = (
        tmp_path
        / "output"
        / "ci-evidence"
        / RUN_ID
        / f"vulnerability-authority-attempt-{RUN_ATTEMPT}"
        / "cisa-kev.json"
    )
    _write(spoof_path, '{"contact":"personal@example.com"}')

    findings = guard.evaluate_synthetic_fixture_governance(
        repo_root=tmp_path,
        standard_path=standard_path,
    )

    assert any(finding.rule == "personal-email-address" for finding in findings)


def test_synthetic_fixture_guard_rejects_tampered_authority_bytes(tmp_path: Path) -> None:
    standard_path = _write_standard(tmp_path, _minimal_standard(tmp_path))
    kev_path, _ = _write_verified_cisa_authority(tmp_path)
    _write(kev_path, '{"contact":"tampered@example.com"}')

    findings = guard.evaluate_synthetic_fixture_governance(
        repo_root=tmp_path,
        standard_path=standard_path,
    )

    assert any(finding.rule == "personal-email-address" for finding in findings)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("repository", "sgajbi/other"),
        ("ci_run_id", "999"),
        ("ci_run_attempt", "2"),
        ("git_commit_sha", "short"),
    ],
)
def test_synthetic_fixture_guard_rejects_authority_identity_drift(
    tmp_path: Path, field: str, value: str
) -> None:
    standard_path = _write_standard(tmp_path, _minimal_standard(tmp_path))
    _, bundle_path = _write_verified_cisa_authority(tmp_path)
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    bundle[field] = value
    _rewrite_bundle_digest(bundle_path, bundle)

    findings = guard.evaluate_synthetic_fixture_governance(
        repo_root=tmp_path,
        standard_path=standard_path,
    )

    assert any(finding.rule == "personal-email-address" for finding in findings)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("source_url", "https://example.com/cisa-kev.json"),
        ("fetched_at_utc", "2026-08-13T22:00:00Z"),
        ("fetched_at_utc", "2026-08-14T00:02:00Z"),
    ],
)
def test_synthetic_fixture_guard_rejects_unverified_cisa_metadata(
    tmp_path: Path, field: str, value: str
) -> None:
    standard_path = _write_standard(tmp_path, _minimal_standard(tmp_path))
    _, bundle_path = _write_verified_cisa_authority(tmp_path)
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    bundle["cisa_kev"][field] = value
    _rewrite_bundle_digest(bundle_path, bundle)

    findings = guard.evaluate_synthetic_fixture_governance(
        repo_root=tmp_path,
        standard_path=standard_path,
    )

    assert any(finding.rule == "personal-email-address" for finding in findings)


def test_synthetic_fixture_guard_rejects_mismatched_bundle_digest(tmp_path: Path) -> None:
    standard_path = _write_standard(tmp_path, _minimal_standard(tmp_path))
    _, bundle_path = _write_verified_cisa_authority(tmp_path)
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    bundle["repository"] = "sgajbi/other"
    _write(bundle_path, json.dumps(bundle))

    findings = guard.evaluate_synthetic_fixture_governance(
        repo_root=tmp_path,
        standard_path=standard_path,
    )

    assert any(finding.rule == "personal-email-address" for finding in findings)


def test_synthetic_fixture_guard_rejects_concrete_credentials(tmp_path: Path) -> None:
    standard = _minimal_standard(tmp_path)
    standard_path = _write_standard(tmp_path, standard)
    _write(
        tmp_path / "tests/fixtures/leaky.json",
        '{"headers":{"Authorization":"Bearer abc123456789"},"url":"postgresql://user:secret@db:5432/core"}',
    )

    findings = guard.evaluate_synthetic_fixture_governance(
        repo_root=tmp_path,
        standard_path=standard_path,
    )

    assert {finding.rule for finding in findings} >= {
        "concrete-bearer-token",
        "credentialed-database-url",
    }


def test_synthetic_fixture_guard_rejects_personal_and_account_data(tmp_path: Path) -> None:
    standard = _minimal_standard(tmp_path)
    standard_path = _write_standard(tmp_path, standard)
    _write(
        tmp_path / "tests/fixtures/client.json",
        (
            '{"client_name":"Jane Client","email":"jane.client@example.com",'
            '"account_number":"12345678"}'
        ),
    )

    findings = guard.evaluate_synthetic_fixture_governance(
        repo_root=tmp_path,
        standard_path=standard_path,
    )

    assert {finding.rule for finding in findings} >= {
        "real-looking-client-name",
        "personal-email-address",
        "concrete-account-number",
    }


def test_synthetic_fixture_guard_allows_only_exact_governed_service_email(
    tmp_path: Path,
) -> None:
    standard = _minimal_standard(tmp_path)
    standard_path = _write_standard(tmp_path, standard)
    _write(
        tmp_path / "output/openapi.json",
        '{"contact":"support.ops@lotus.local"}',
    )

    assert (
        guard.evaluate_synthetic_fixture_governance(
            repo_root=tmp_path,
            standard_path=standard_path,
        )
        == []
    )

    _write(
        tmp_path / "output/openapi.json",
        '{"contact":"support.admin@lotus.local"}',
    )
    findings = guard.evaluate_synthetic_fixture_governance(
        repo_root=tmp_path,
        standard_path=standard_path,
    )

    assert any(finding.rule == "personal-email-address" for finding in findings)


def test_synthetic_fixture_guard_rejects_external_service_email_allowlist(
    tmp_path: Path,
) -> None:
    standard = _minimal_standard(tmp_path)
    standard["leakage_guard"]["allowed_service_emails"] = ["support@example.com"]  # type: ignore[index]
    standard_path = _write_standard(tmp_path, standard)

    findings = guard.evaluate_synthetic_fixture_governance(
        repo_root=tmp_path,
        standard_path=standard_path,
    )

    assert any(finding.rule == "invalid-allowed-service-email" for finding in findings)


def test_synthetic_fixture_guard_ignores_java_identity_but_rejects_email(
    tmp_path: Path,
) -> None:
    standard = _minimal_standard(tmp_path)
    standard_path = _write_standard(tmp_path, standard)
    _write(
        tmp_path / "tests/fixtures/runtime.log",
        (
            "ServletContext@o.e.j.s.ServletContextHandler is starting\n"
            "unexpected contact operator@example.com\n"
        ),
    )

    findings = guard.evaluate_synthetic_fixture_governance(
        repo_root=tmp_path,
        standard_path=standard_path,
    )

    email_findings = [finding for finding in findings if finding.rule == "personal-email-address"]
    assert len(email_findings) == 1
    assert "operator" in email_findings[0].detail


def test_synthetic_fixture_guard_rejects_uncataloged_cif_identifier(tmp_path: Path) -> None:
    standard = _minimal_standard(tmp_path)
    standard_path = _write_standard(tmp_path, standard)
    _write(tmp_path / "tests/fixtures/cif.json", '{"client_id":"CIF_SG_999999"}')

    findings = guard.evaluate_synthetic_fixture_governance(
        repo_root=tmp_path,
        standard_path=standard_path,
    )

    assert any(finding.rule == "uncataloged-cif-client-id" for finding in findings)


def test_synthetic_fixture_guard_requires_representative_relationships(tmp_path: Path) -> None:
    standard = _minimal_standard(tmp_path)
    fixture_path = tmp_path / "tests/fixtures/private-banking-portfolio-fixture.v1.json"
    _write(
        fixture_path,
        json.dumps(
            {
                "schema_version": "private-banking-portfolio-fixture.v1",
                "fixture_id": "private_banking_portfolio_fixture.v1",
                "synthetic_data": True,
                "safe_for_committed_tests": True,
                "relationships": {"client": {}, "portfolio": {}},
            }
        ),
    )
    standard_path = _write_standard(tmp_path, standard)

    findings = guard.evaluate_synthetic_fixture_governance(
        repo_root=tmp_path,
        standard_path=standard_path,
    )

    assert any(finding.rule == "missing-representative-relationship" for finding in findings)
