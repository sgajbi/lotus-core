"""Validate the governed Kafka/outbox event contract test pack."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Any

from portfolio_common.event_supportability import (
    DIRECT_KAFKA_TOPIC_DEFINITIONS,
    EVENT_FAMILY_DEFINITIONS,
)
from portfolio_common.events import GOVERNED_EVENT_SCHEMA_VERSION

REPO_ROOT = Path(__file__).resolve().parents[1]
PACK_PATH = Path("docs/standards/event-contract-test-pack.v1.json")
SCHEMA_VERSION = "lotus-core.event-contract-test-pack.v1"
REQUIRED_EVIDENCE_KEYS = {
    "producer_evidence",
    "consumer_evidence",
    "header_and_lineage_evidence",
    "dlq_replay_evidence",
}


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _normalize(path: str) -> str:
    return path.replace("\\", "/").strip()


def _make_targets(repo_root: Path) -> set[str]:
    makefile = repo_root / "Makefile"
    target_pattern = re.compile(r"^([A-Za-z0-9_.-]+):(?:\s|$)")
    targets: set[str] = set()
    for line in makefile.read_text(encoding="utf-8").splitlines():
        match = target_pattern.match(line)
        if match and not line.startswith("\t"):
            targets.add(match.group(1))
    return targets


def _repo_files(repo_root: Path) -> set[str]:
    completed = subprocess.run(
        ["git", "ls-files"],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if completed.returncode == 0:
        return {_normalize(line) for line in completed.stdout.splitlines() if line.strip()}
    return {
        path.relative_to(repo_root).as_posix()
        for path in repo_root.rglob("*")
        if path.is_file() and ".git" not in path.parts
    }


def _ref_exists(
    ref: str,
    *,
    repo_root: Path,
    repo_files: set[str],
    make_targets: set[str],
) -> bool:
    normalized = _normalize(ref)
    if normalized.startswith("make "):
        return normalized.removeprefix("make ").split()[0] in make_targets
    return normalized in repo_files or (repo_root / normalized).exists()


def _validate_evidence_profiles(
    pack: dict[str, Any],
    *,
    repo_root: Path,
    repo_files: set[str],
    make_targets: set[str],
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    profiles = pack.get("evidence_profiles")
    if not isinstance(profiles, dict) or not profiles:
        return [{"missing": "evidence_profiles"}]

    for profile_name, profile in profiles.items():
        if not isinstance(profile, dict):
            findings.append({"profile": profile_name, "invalid": "profile must be an object"})
            continue
        missing_keys = sorted(REQUIRED_EVIDENCE_KEYS - set(profile))
        if missing_keys:
            findings.append({"profile": profile_name, "missing_evidence_keys": missing_keys})
        for evidence_key in REQUIRED_EVIDENCE_KEYS:
            refs = profile.get(evidence_key)
            if not isinstance(refs, list) or not refs:
                findings.append({"profile": profile_name, "missing": evidence_key})
                continue
            missing_refs = [
                ref
                for ref in refs
                if not _ref_exists(
                    str(ref),
                    repo_root=repo_root,
                    repo_files=repo_files,
                    make_targets=make_targets,
                )
            ]
            if missing_refs:
                findings.append(
                    {
                        "profile": profile_name,
                        "evidence_key": evidence_key,
                        "missing_refs": missing_refs,
                    }
                )
    return findings


def _validate_event_families(pack: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    entries = pack.get("event_families")
    if not isinstance(entries, list) or not entries:
        return [{"missing": "event_families"}]

    expected_by_type = {
        definition.event_type: definition for definition in EVENT_FAMILY_DEFINITIONS
    }
    actual_by_type = {
        str(entry.get("event_type", "")): entry for entry in entries if isinstance(entry, dict)
    }
    missing = sorted(set(expected_by_type) - set(actual_by_type))
    extra = sorted(set(actual_by_type) - set(expected_by_type))
    if missing:
        findings.append({"event_families_missing_from_pack": missing})
    if extra:
        findings.append({"event_families_unknown_to_catalog": extra})

    for event_type, definition in expected_by_type.items():
        entry = actual_by_type.get(event_type)
        if entry is None:
            continue
        for field_name, expected_value in {
            "topic": definition.topic,
            "schema_model": definition.schema_model,
        }.items():
            if entry.get(field_name) != expected_value:
                findings.append(
                    {
                        "event_type": event_type,
                        "field": field_name,
                        "actual": entry.get(field_name),
                        "expected": expected_value,
                    }
                )
        if not entry.get("evidence_profile"):
            findings.append({"event_type": event_type, "missing": "evidence_profile"})
        if not entry.get("partition_key_policy"):
            findings.append({"event_type": event_type, "missing": "partition_key_policy"})
    return findings


def _validate_direct_topics(pack: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    entries = pack.get("direct_kafka_topics")
    if not isinstance(entries, list) or not entries:
        return [{"missing": "direct_kafka_topics"}]

    expected_by_name = {
        definition.name: definition for definition in DIRECT_KAFKA_TOPIC_DEFINITIONS
    }
    actual_by_name = {
        str(entry.get("name", "")): entry for entry in entries if isinstance(entry, dict)
    }
    missing = sorted(set(expected_by_name) - set(actual_by_name))
    extra = sorted(set(actual_by_name) - set(expected_by_name))
    if missing:
        findings.append({"direct_topics_missing_from_pack": missing})
    if extra:
        findings.append({"direct_topics_unknown_to_catalog": extra})

    for name, definition in expected_by_name.items():
        entry = actual_by_name.get(name)
        if entry is None:
            continue
        for field_name, expected_value in {
            "topic": definition.topic,
            "payload_contract": definition.payload_contract,
        }.items():
            if entry.get(field_name) != expected_value:
                findings.append(
                    {
                        "direct_topic": name,
                        "field": field_name,
                        "actual": entry.get(field_name),
                        "expected": expected_value,
                    }
                )
        if not entry.get("evidence_profile"):
            findings.append({"direct_topic": name, "missing": "evidence_profile"})
        if not entry.get("partition_key_policy"):
            findings.append({"direct_topic": name, "missing": "partition_key_policy"})
    return findings


def validate_event_contract_test_pack(
    pack: dict[str, Any],
    *,
    repo_root: Path = REPO_ROOT,
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    if pack.get("schema_version") != SCHEMA_VERSION:
        findings.append({"invalid_schema_version": pack.get("schema_version")})
    if pack.get("owning_repository") != "lotus-core":
        findings.append({"invalid_owning_repository": pack.get("owning_repository")})
    if GOVERNED_EVENT_SCHEMA_VERSION not in pack.get("accepted_event_schema_versions", []):
        findings.append({"missing_schema_version": GOVERNED_EVENT_SCHEMA_VERSION})
    if pack.get("gate_command") != "make event-contract-test-pack-guard":
        findings.append({"invalid_gate_command": pack.get("gate_command")})
    if not pack.get("compatibility_policy", {}).get("breaking_change"):
        findings.append({"missing": "compatibility_policy.breaking_change"})

    repo_files = _repo_files(repo_root)
    make_targets = _make_targets(repo_root)
    findings.extend(
        _validate_evidence_profiles(
            pack,
            repo_root=repo_root,
            repo_files=repo_files,
            make_targets=make_targets,
        )
    )
    findings.extend(_validate_event_families(pack))
    findings.extend(_validate_direct_topics(pack))
    return findings


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack", type=Path, default=PACK_PATH)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    findings = validate_event_contract_test_pack(
        _load_json(REPO_ROOT / args.pack),
        repo_root=REPO_ROOT,
    )
    if findings:
        print("Event contract test pack guard failed:")
        print(json.dumps(findings, indent=2, sort_keys=True))
        return 1
    print(f"Event contract test pack guard passed: {args.pack.as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
