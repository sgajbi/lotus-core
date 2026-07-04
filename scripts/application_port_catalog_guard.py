from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


CATALOG_PATH = Path("docs/architecture/application-port-capability-catalog.json")
EXPECTED_SCHEMA_VERSION = "lotus-core.application-port-capability-catalog.v1"
REQUIRED_ENTRY_FIELDS = {
    "capability_id",
    "capability_family",
    "owner_service",
    "port_module",
    "port_symbols",
    "adapter_modules",
    "consumer_modules",
    "guard_scripts",
    "standards",
    "status",
    "runtime_boundary",
}


@dataclass(frozen=True, slots=True)
class ApplicationPortCatalogFinding:
    capability_id: str
    reason: str


def _load_catalog(root: Path) -> dict[str, Any]:
    path = root / CATALOG_PATH
    if not path.exists():
        return {
            "schema_version": None,
            "capabilities": [],
            "_missing_catalog": True,
        }
    return json.loads(path.read_text(encoding="utf-8"))


def _path_exists(root: Path, relative_path: str) -> bool:
    return (root / relative_path).exists()


def _symbol_defined(source: str, symbol: str) -> bool:
    return re.search(rf"^(class|def)\s+{re.escape(symbol)}\b", source, re.MULTILINE) is not None


def find_application_port_catalog_findings(
    root: Path,
) -> list[ApplicationPortCatalogFinding]:
    findings: list[ApplicationPortCatalogFinding] = []
    catalog = _load_catalog(root)
    if catalog.get("_missing_catalog"):
        return [
            ApplicationPortCatalogFinding(
                capability_id="catalog",
                reason=f"missing catalog file {CATALOG_PATH.as_posix()}",
            )
        ]

    if catalog.get("schema_version") != EXPECTED_SCHEMA_VERSION:
        findings.append(
            ApplicationPortCatalogFinding(
                capability_id="catalog",
                reason="unexpected schema_version",
            )
        )

    catalog_guard = catalog.get("catalog_guard")
    if not isinstance(catalog_guard, str) or not _path_exists(root, catalog_guard):
        findings.append(
            ApplicationPortCatalogFinding(
                capability_id="catalog",
                reason="catalog_guard must reference an existing file",
            )
        )

    seen_ids: set[str] = set()
    for raw_entry in catalog.get("capabilities", []):
        if not isinstance(raw_entry, dict):
            findings.append(
                ApplicationPortCatalogFinding(
                    capability_id="catalog",
                    reason="capability entries must be objects",
                )
            )
            continue

        capability_id = str(raw_entry.get("capability_id") or "<missing>")
        missing_fields = sorted(REQUIRED_ENTRY_FIELDS.difference(raw_entry))
        if missing_fields:
            findings.append(
                ApplicationPortCatalogFinding(
                    capability_id=capability_id,
                    reason=f"missing required fields: {', '.join(missing_fields)}",
                )
            )
            continue

        if capability_id in seen_ids:
            findings.append(
                ApplicationPortCatalogFinding(
                    capability_id=capability_id,
                    reason="duplicate capability_id",
                )
            )
        seen_ids.add(capability_id)

        port_module = str(raw_entry["port_module"])
        if not _path_exists(root, port_module):
            findings.append(
                ApplicationPortCatalogFinding(
                    capability_id=capability_id,
                    reason=f"missing port_module {port_module}",
                )
            )
            continue

        owner_service = str(raw_entry["owner_service"])
        capability_family = str(raw_entry["capability_family"])
        provider_family_exception = capability_family == "clock-id-provider"
        if (
            owner_service != "portfolio_common"
            and "/app/ports/" not in port_module
            and not provider_family_exception
        ):
            findings.append(
                ApplicationPortCatalogFinding(
                    capability_id=capability_id,
                    reason="service-local ports must use src/services/<service>/app/ports/",
                )
            )

        source = (root / port_module).read_text(encoding="utf-8")
        port_symbols = raw_entry["port_symbols"]
        if not isinstance(port_symbols, list) or not port_symbols:
            findings.append(
                ApplicationPortCatalogFinding(
                    capability_id=capability_id,
                    reason="port_symbols must be a non-empty list",
                )
            )
        else:
            for symbol in port_symbols:
                if not isinstance(symbol, str) or not _symbol_defined(source, symbol):
                    findings.append(
                        ApplicationPortCatalogFinding(
                            capability_id=capability_id,
                            reason=f"missing port symbol {symbol}",
                        )
                    )

        for field in ("adapter_modules", "consumer_modules", "guard_scripts", "standards"):
            values = raw_entry[field]
            if not isinstance(values, list) or not values:
                findings.append(
                    ApplicationPortCatalogFinding(
                        capability_id=capability_id,
                        reason=f"{field} must be a non-empty list",
                    )
                )
                continue
            for relative_path in values:
                if not isinstance(relative_path, str) or not _path_exists(root, relative_path):
                    findings.append(
                        ApplicationPortCatalogFinding(
                            capability_id=capability_id,
                            reason=f"missing {field} file {relative_path}",
                        )
                    )

    if not seen_ids:
        findings.append(
            ApplicationPortCatalogFinding(
                capability_id="catalog",
                reason="catalog must include at least one capability",
            )
        )

    return findings


def main() -> int:
    findings = find_application_port_catalog_findings(Path.cwd())
    if findings:
        for finding in findings:
            print(f"{finding.capability_id}: {finding.reason}")
        return 1
    print("Application port catalog guard passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
