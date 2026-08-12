"""Load and validate a freshly fetched CISA Known Exploited Vulnerabilities catalog."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

CISA_KEV_SOURCE_URL = (
    "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
)
CVE_PATTERN = re.compile(r"^CVE-[0-9]{4}-[0-9]{4,}$")
EXPECTED_CATALOG_TITLE = "CISA Catalog of Known Exploited Vulnerabilities"
DEFAULT_COMPLETENESS_POLICY_PATH = (
    Path(__file__).resolve().parents[2]
    / "contracts"
    / "security"
    / "cisa-kev-authority-policy.v1.json"
)


class CisaKevError(ValueError):
    """Raised when CISA KEV evidence cannot support a release decision."""


@dataclass(frozen=True)
class CisaKevCatalog:
    catalog_version: str
    date_released_utc: datetime
    fetched_at_utc: datetime
    source_sha256: str
    cve_ids: frozenset[str]

    def receipt_identity(self) -> dict[str, object]:
        return {
            "source_url": CISA_KEV_SOURCE_URL,
            "catalog_version": self.catalog_version,
            "date_released_utc": self.date_released_utc.isoformat().replace("+00:00", "Z"),
            "fetched_at_utc": self.fetched_at_utc.isoformat().replace("+00:00", "Z"),
            "source_sha256": self.source_sha256,
            "entry_count": len(self.cve_ids),
        }


def _utc_timestamp(value: str) -> datetime:
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CisaKevError("CISA KEV fetched-at must be an ISO-8601 timestamp") from exc
    if timestamp.tzinfo is None or timestamp.utcoffset() != UTC.utcoffset(timestamp):
        raise CisaKevError("CISA KEV fetched-at must include an explicit UTC offset")
    return timestamp.astimezone(UTC)


def _release_timestamp(value: object) -> datetime:
    if not isinstance(value, str):
        raise CisaKevError("CISA KEV dateReleased must be a string")
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        timestamp = None
    if timestamp is not None and timestamp.tzinfo is not None:
        return timestamp.astimezone(UTC)
    for format_string in ("%Y.%m.%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, format_string).replace(tzinfo=UTC)
        except ValueError:
            continue
    raise CisaKevError("CISA KEV dateReleased has an unsupported format")


def _json_object(path: Path) -> tuple[bytes, dict[str, Any]]:
    try:
        content = path.read_bytes()
        value = json.loads(content.decode("utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CisaKevError(f"cannot read CISA KEV catalog {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise CisaKevError("CISA KEV catalog must contain a JSON object")
    return content, value


def _catalog_version(value: object, *, field: str) -> tuple[int, int, int]:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{4}\.[0-9]{2}\.[0-9]{2}", value):
        raise CisaKevError(f"{field} must use YYYY.MM.DD")
    return tuple(int(part) for part in value.split("."))  # type: ignore[return-value]


def _completeness_boundary(policy_path: Path) -> tuple[int, tuple[int, int, int], datetime]:
    _, policy = _json_object(policy_path)
    if policy.get("schema_version") != "lotus-core.cisa-kev-authority-policy.v1":
        raise CisaKevError("CISA KEV completeness policy has an unsupported schema version")
    if policy.get("source_url") != CISA_KEV_SOURCE_URL:
        raise CisaKevError("CISA KEV completeness policy has an unsupported source")
    minimum = policy.get("minimum_entry_count")
    observed = policy.get("baseline_entry_count")
    if (
        not isinstance(minimum, int)
        or minimum < 1
        or not isinstance(observed, int)
        or observed < minimum
    ):
        raise CisaKevError("CISA KEV completeness policy has invalid entry-count bounds")
    for field in (
        "baseline_catalog_version",
        "baseline_date_released_utc",
        "baseline_observed_at_utc",
        "review_owner",
    ):
        if not isinstance(policy.get(field), str) or not policy[field].strip():
            raise CisaKevError(f"CISA KEV completeness policy requires {field}")
    baseline_version = _catalog_version(
        policy["baseline_catalog_version"], field="baseline catalog version"
    )
    baseline_release = _utc_timestamp(str(policy["baseline_date_released_utc"]))
    _utc_timestamp(str(policy["baseline_observed_at_utc"]))
    return minimum, baseline_version, baseline_release


def load_cisa_kev_catalog(
    path: Path,
    *,
    fetched_at: str,
    completeness_policy_path: Path | None = None,
) -> CisaKevCatalog:
    content, value = _json_object(path)
    if value.get("title") != EXPECTED_CATALOG_TITLE:
        raise CisaKevError("CISA KEV catalog has an unexpected title")
    catalog_version = value.get("catalogVersion")
    parsed_catalog_version = _catalog_version(catalog_version, field="CISA KEV catalogVersion")
    release_timestamp = _release_timestamp(value.get("dateReleased"))
    fetched_timestamp = _utc_timestamp(fetched_at)
    if release_timestamp > fetched_timestamp:
        raise CisaKevError("CISA KEV dateReleased cannot be after fetched-at")

    vulnerabilities = value.get("vulnerabilities")
    if not isinstance(vulnerabilities, list):
        raise CisaKevError("CISA KEV vulnerabilities must be an array")
    if not vulnerabilities:
        raise CisaKevError("CISA KEV vulnerabilities must not be empty")
    declared_count = value.get("count")
    if not isinstance(declared_count, int) or declared_count != len(vulnerabilities):
        raise CisaKevError("CISA KEV count does not match vulnerabilities")
    minimum_entry_count, baseline_version, baseline_release = _completeness_boundary(
        completeness_policy_path or DEFAULT_COMPLETENESS_POLICY_PATH
    )
    if declared_count < minimum_entry_count:
        raise CisaKevError(
            "CISA KEV catalog is below the governed completeness floor "
            f"({declared_count} < {minimum_entry_count})"
        )
    if parsed_catalog_version < baseline_version or release_timestamp < baseline_release:
        raise CisaKevError("CISA KEV catalog predates the governed anti-rollback boundary")

    cve_ids: list[str] = []
    for entry in vulnerabilities:
        if not isinstance(entry, dict):
            raise CisaKevError("CISA KEV vulnerability entries must be objects")
        cve_id = entry.get("cveID")
        if not isinstance(cve_id, str) or not CVE_PATTERN.fullmatch(cve_id):
            raise CisaKevError(f"CISA KEV entry has invalid cveID: {cve_id!r}")
        cve_ids.append(cve_id)
    if len(set(cve_ids)) != len(cve_ids):
        raise CisaKevError("CISA KEV catalog contains duplicate CVE identities")

    return CisaKevCatalog(
        catalog_version=str(catalog_version),
        date_released_utc=release_timestamp,
        fetched_at_utc=fetched_timestamp,
        source_sha256="sha256:" + hashlib.sha256(content).hexdigest(),
        cve_ids=frozenset(cve_ids),
    )
