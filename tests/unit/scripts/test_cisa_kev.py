from __future__ import annotations

import json
from pathlib import Path

import pytest

import scripts.release.cisa_kev as cisa_kev
from scripts.release.cisa_kev import CISA_KEV_SOURCE_URL, CisaKevError, load_cisa_kev_catalog


@pytest.fixture(autouse=True)
def _completeness_policy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "cisa-kev-authority-policy.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "lotus-core.cisa-kev-authority-policy.v1",
                "source_url": CISA_KEV_SOURCE_URL,
                "baseline_catalog_version": "2026.08.12",
                "baseline_date_released_utc": "2026-08-12T00:00:00Z",
                "baseline_entry_count": 2,
                "minimum_entry_count": 2,
                "baseline_observed_at_utc": "2026-08-12T02:00:00Z",
                "review_owner": "test",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(cisa_kev, "DEFAULT_COMPLETENESS_POLICY_PATH", path)


def _write_catalog(tmp_path: Path, **overrides: object) -> Path:
    value: dict[str, object] = {
        "title": "CISA Catalog of Known Exploited Vulnerabilities",
        "catalogVersion": "2026.08.12",
        "dateReleased": "2026.08.12",
        "count": 2,
        "vulnerabilities": [
            {"cveID": "CVE-2026-1000"},
            {"cveID": "CVE-2026-2000"},
        ],
    }
    value.update(overrides)
    path = tmp_path / "cisa-kev.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def test_catalog_binds_source_digest_and_cve_membership(tmp_path: Path) -> None:
    catalog = load_cisa_kev_catalog(_write_catalog(tmp_path), fetched_at="2026-08-12T02:00:00Z")

    assert catalog.cve_ids == frozenset({"CVE-2026-1000", "CVE-2026-2000"})
    assert catalog.receipt_identity() == {
        "source_url": CISA_KEV_SOURCE_URL,
        "catalog_version": "2026.08.12",
        "date_released_utc": "2026-08-12T00:00:00Z",
        "fetched_at_utc": "2026-08-12T02:00:00Z",
        "source_sha256": catalog.source_sha256,
        "entry_count": 2,
    }
    assert catalog.source_sha256.startswith("sha256:")


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"title": "untrusted"}, "unexpected title"),
        ({"catalogVersion": ""}, "catalogVersion"),
        ({"dateReleased": "tomorrow"}, "unsupported format"),
        ({"dateReleased": "2026.08.13"}, "cannot be after"),
        ({"count": 1}, "count does not match"),
        ({"count": 0, "vulnerabilities": []}, "must not be empty"),
        (
            {
                "vulnerabilities": [
                    {"cveID": "CVE-2026-1000"},
                    {"cveID": "CVE-2026-1000"},
                ]
            },
            "duplicate CVE",
        ),
        (
            {"vulnerabilities": [{"cveID": "GHSA-not-cisa"}, {"cveID": "CVE-2026-2000"}]},
            "invalid cveID",
        ),
    ],
)
def test_catalog_malformed_authority_fails_closed(
    tmp_path: Path, overrides: dict[str, object], message: str
) -> None:
    with pytest.raises(CisaKevError, match=message):
        load_cisa_kev_catalog(
            _write_catalog(tmp_path, **overrides),
            fetched_at="2026-08-12T02:00:00Z",
        )


def test_catalog_fetch_timestamp_requires_explicit_utc(tmp_path: Path) -> None:
    with pytest.raises(CisaKevError, match="explicit UTC"):
        load_cisa_kev_catalog(_write_catalog(tmp_path), fetched_at="2026-08-12T02:00:00")


def test_catalog_accepts_current_iso_timestamp_shape(tmp_path: Path) -> None:
    catalog = load_cisa_kev_catalog(
        _write_catalog(tmp_path, dateReleased="2026-08-12T00:00:00.0001Z"),
        fetched_at="2026-08-12T02:00:00Z",
    )

    assert catalog.receipt_identity()["date_released_utc"] == ("2026-08-12T00:00:00.000100Z")


def test_catalog_below_governed_completeness_floor_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(CisaKevError, match="completeness floor"):
        load_cisa_kev_catalog(
            _write_catalog(
                tmp_path,
                count=1,
                vulnerabilities=[{"cveID": "CVE-2026-1000"}],
            ),
            fetched_at="2026-08-12T02:00:00Z",
        )


@pytest.mark.parametrize(
    ("catalog_version", "date_released"),
    [("2026.08.11", "2026.08.12"), ("2026.08.12", "2026.08.11")],
)
def test_catalog_rollback_fails_closed_even_above_size_floor(
    tmp_path: Path, catalog_version: str, date_released: str
) -> None:
    with pytest.raises(CisaKevError, match="anti-rollback"):
        load_cisa_kev_catalog(
            _write_catalog(
                tmp_path,
                catalogVersion=catalog_version,
                dateReleased=date_released,
            ),
            fetched_at="2026-08-12T02:00:00Z",
        )
