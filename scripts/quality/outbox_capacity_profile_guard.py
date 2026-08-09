"""Validate governed outbox capacity profiles and their runtime bindings."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, cast

import yaml
from portfolio_common.kafka_producer_policy import DEFAULT_DELIVERY_TIMEOUT_MS
from portfolio_common.outbox_dispatcher import (
    CLAIM_LEASE_SAFETY_SECONDS,
    SHUTDOWN_DRAIN_SAFETY_SECONDS,
)
from portfolio_common.runtime_supervision import RUNTIME_TERMINATION_GRACE_SAFETY_SECONDS

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = Path("docs/standards/outbox-capacity-profile.v1.json")
SCHEMA_VERSION = "lotus-core.outbox-capacity-profile.v1"
REQUIRED_ENVIRONMENT_KEYS = {
    "OUTBOX_DISPATCHER_POLL_INTERVAL_SECONDS",
    "OUTBOX_DISPATCHER_BATCH_SIZE",
    "OUTBOX_DISPATCHER_CLAIM_LEASE_SECONDS",
    "OUTBOX_DISPATCHER_TERMINATION_GRACE_SECONDS",
    "OUTBOX_DISPATCHER_MAX_RETRIES",
    "OUTBOX_DISPATCHER_RETRY_MAX_ELAPSED_SECONDS",
    "OUTBOX_DISPATCHER_RETRY_INITIAL_DELAY_SECONDS",
    "OUTBOX_DISPATCHER_RETRY_MAX_DELAY_SECONDS",
    "OUTBOX_DISPATCHER_RETRY_JITTER_SECONDS",
}
REQUIRED_BINDINGS = {"development", "ci", "production_safe_baseline"}


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Outbox capacity profile must be an object: {path}")
    return cast(dict[str, Any], payload)


def _positive_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _non_negative_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _compose_defaults(path: Path) -> dict[str, int]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    environment = payload.get("x-shared-python-env", {}) if isinstance(payload, dict) else {}
    defaults: dict[str, int] = {}
    for name in REQUIRED_ENVIRONMENT_KEYS:
        raw_value = environment.get(name)
        match = re.fullmatch(rf"\$\{{{re.escape(name)}:-(\d+)\}}", str(raw_value))
        if match:
            defaults[name] = int(match.group(1))
    return defaults


def _kubernetes_literals(path: Path) -> list[dict[str, int]]:
    deployments: list[dict[str, int]] = []
    for document in yaml.safe_load_all(path.read_text(encoding="utf-8")):
        if not isinstance(document, dict) or document.get("kind") != "Deployment":
            continue
        containers = (
            document.get("spec", {}).get("template", {}).get("spec", {}).get("containers", [])
        )
        for container in containers:
            values: dict[str, int] = {}
            for item in container.get("env", []):
                name = item.get("name")
                value = item.get("value")
                if name in REQUIRED_ENVIRONMENT_KEYS and str(value).isdigit():
                    values[str(name)] = int(value)
            deployments.append(values)
    return deployments


def _validate_profile(profile_name: str, profile: object) -> list[dict[str, Any]]:
    if not isinstance(profile, dict):
        return [{"profile": profile_name, "invalid": "profile must be an object"}]
    findings: list[dict[str, Any]] = []
    if profile.get("certification_status") not in {
        "candidate_pending_exact_source",
        "certified_exact_source",
    }:
        findings.append({"profile": profile_name, "invalid": "certification_status"})
    environment = profile.get("environment")
    if not isinstance(environment, dict):
        return [{"profile": profile_name, "missing": "environment"}]
    missing_keys = sorted(REQUIRED_ENVIRONMENT_KEYS - environment.keys())
    extra_keys = sorted(environment.keys() - REQUIRED_ENVIRONMENT_KEYS)
    if missing_keys:
        findings.append({"profile": profile_name, "missing_environment_keys": missing_keys})
    if extra_keys:
        findings.append({"profile": profile_name, "unexpected_environment_keys": extra_keys})
    positive_names = REQUIRED_ENVIRONMENT_KEYS - {
        "OUTBOX_DISPATCHER_RETRY_MAX_ELAPSED_SECONDS",
        "OUTBOX_DISPATCHER_RETRY_JITTER_SECONDS",
    }
    invalid_positive = sorted(
        name for name in positive_names if not _positive_int(environment.get(name))
    )
    invalid_non_negative = sorted(
        name
        for name in REQUIRED_ENVIRONMENT_KEYS - positive_names
        if not _non_negative_int(environment.get(name))
    )
    if invalid_positive:
        findings.append({"profile": profile_name, "invalid_positive_values": invalid_positive})
    if invalid_non_negative:
        findings.append(
            {"profile": profile_name, "invalid_non_negative_values": invalid_non_negative}
        )
    if findings:
        return findings

    delivery_timeout_ms = profile.get("kafka_delivery_timeout_ms")
    if not _positive_int(delivery_timeout_ms):
        return [{"profile": profile_name, "invalid": "kafka_delivery_timeout_ms"}]
    delivery_fence_seconds = ((cast(int, delivery_timeout_ms) + 999) // 1000) + 1
    minimum_claim_lease = delivery_fence_seconds + CLAIM_LEASE_SAFETY_SECONDS
    if environment["OUTBOX_DISPATCHER_CLAIM_LEASE_SECONDS"] < minimum_claim_lease:
        findings.append(
            {
                "profile": profile_name,
                "claim_lease_below_delivery_fence": minimum_claim_lease,
            }
        )
    minimum_termination_grace = (
        delivery_fence_seconds
        + SHUTDOWN_DRAIN_SAFETY_SECONDS
        + RUNTIME_TERMINATION_GRACE_SAFETY_SECONDS
    )
    if environment["OUTBOX_DISPATCHER_TERMINATION_GRACE_SECONDS"] < minimum_termination_grace:
        findings.append(
            {
                "profile": profile_name,
                "termination_grace_below_shutdown_fence": minimum_termination_grace,
            }
        )
    if (
        environment["OUTBOX_DISPATCHER_RETRY_MAX_DELAY_SECONDS"]
        < environment["OUTBOX_DISPATCHER_RETRY_INITIAL_DELAY_SECONDS"]
    ):
        findings.append({"profile": profile_name, "invalid": "retry delay ordering"})
    return findings


def validate_outbox_capacity_contract(
    contract: dict[str, Any], *, repo_root: Path = REPO_ROOT
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    if contract.get("schema_version") != SCHEMA_VERSION:
        findings.append({"invalid_schema_version": contract.get("schema_version")})
    if contract.get("issue") != "sgajbi/lotus-core#794":
        findings.append({"invalid_issue": contract.get("issue")})
    expected_safety_invariants = {
        "delivery_fence_rounding_seconds": 1,
        "claim_lease_safety_seconds": CLAIM_LEASE_SAFETY_SECONDS,
        "shutdown_drain_safety_seconds": SHUTDOWN_DRAIN_SAFETY_SECONDS,
        "runtime_termination_grace_safety_seconds": (RUNTIME_TERMINATION_GRACE_SAFETY_SECONDS),
        "retry_max_elapsed_zero_means_disabled": True,
    }
    if contract.get("safety_invariants") != expected_safety_invariants:
        findings.append(
            {
                "invalid_safety_invariants": contract.get("safety_invariants"),
                "expected": expected_safety_invariants,
            }
        )
    profiles = contract.get("profiles")
    if not isinstance(profiles, dict) or not profiles:
        return [*findings, {"missing": "profiles"}]
    for profile_name, profile in profiles.items():
        findings.extend(_validate_profile(str(profile_name), profile))
        if isinstance(profile, dict) and profile.get("kafka_delivery_timeout_ms") != (
            DEFAULT_DELIVERY_TIMEOUT_MS
        ):
            findings.append(
                {
                    "profile": profile_name,
                    "kafka_delivery_timeout_drift": profile.get("kafka_delivery_timeout_ms"),
                    "expected": DEFAULT_DELIVERY_TIMEOUT_MS,
                }
            )

    bindings = contract.get("environment_bindings")
    if not isinstance(bindings, dict):
        return [*findings, {"missing": "environment_bindings"}]
    missing_bindings = sorted(REQUIRED_BINDINGS - bindings.keys())
    if missing_bindings:
        findings.append({"missing_environment_bindings": missing_bindings})
    for binding_name, binding in bindings.items():
        if not isinstance(binding, dict):
            findings.append({"binding": binding_name, "invalid": "binding must be an object"})
            continue
        profile_name = binding.get("profile")
        profile = profiles.get(profile_name)
        if not isinstance(profile, dict) or not isinstance(profile.get("environment"), dict):
            findings.append({"binding": binding_name, "unknown_profile": profile_name})
            continue
        expected = cast(dict[str, int], profile["environment"])
        kind = binding.get("kind")
        paths = binding.get("paths")
        if not isinstance(paths, list) or not paths:
            findings.append({"binding": binding_name, "missing": "paths"})
            continue
        for relative_path in paths:
            path = repo_root / str(relative_path)
            if not path.is_file():
                findings.append({"binding": binding_name, "missing_path": str(relative_path)})
                continue
            if kind == "compose_defaults":
                actual_sets = [_compose_defaults(path)]
            elif kind == "kubernetes_literals":
                actual_sets = _kubernetes_literals(path)
            else:
                findings.append({"binding": binding_name, "invalid_kind": kind})
                continue
            if not actual_sets:
                findings.append({"binding": binding_name, "missing_runtime": str(relative_path)})
            for actual in actual_sets:
                if actual != expected:
                    findings.append(
                        {
                            "binding": binding_name,
                            "path": str(relative_path),
                            "expected": expected,
                            "actual": actual,
                        }
                    )
    return findings


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, default=CONTRACT_PATH)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    findings = validate_outbox_capacity_contract(
        _load_json(REPO_ROOT / args.contract), repo_root=REPO_ROOT
    )
    if findings:
        print("Outbox capacity profile guard failed:")
        print(json.dumps(findings, indent=2, sort_keys=True))
        return 1
    print(f"Outbox capacity profile guard passed: {args.contract.as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
