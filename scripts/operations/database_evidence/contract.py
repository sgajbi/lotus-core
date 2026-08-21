"""Versioned contract and fail-closed evaluator for database hot-path plans."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping

CATALOG_SCHEMA_VERSION = "lotus-core.database-hot-path-scenarios.v1"
ARTIFACT_SCHEMA_VERSION = "lotus-core.database-hot-path-evidence.v1"
EVIDENCE_POSTURE = "report_only"

_CATALOG_KEYS = {
    "schema_version",
    "owning_repository",
    "evidence_posture",
    "scenarios",
}
_SCENARIO_KEYS = {
    "scenario_id",
    "repository_owner",
    "repository_method",
    "seed_cardinality",
    "prohibited_node_types",
    "requires_indexed_access",
    "max_root_actual_rows",
    "max_rows_examined",
    "rationale",
}
_SCENARIO_ID = re.compile(r"^[a-z][a-z0-9_]*$")
_GIT_SHA = re.compile(r"^[0-9a-f]{40}$")
_INDEX_NODE_TYPES = {"Index Scan", "Index Only Scan", "Bitmap Index Scan"}
_SENSITIVE_KEY_PARTS = {
    "dsn",
    "host",
    "parameter",
    "password",
    "portfolio",
    "security_id",
    "sql",
    "url",
    "username",
}
_SENSITIVE_VALUE_MARKERS = (
    "postgresql://",
    "postgres://",
    "password=",
    "database_url",
)


class DatabaseEvidenceContractError(ValueError):
    """Raised when catalog, plan, or artifact evidence is not trustworthy."""


@dataclass(frozen=True, slots=True)
class HotPathScenario:
    scenario_id: str
    repository_owner: str
    repository_method: str
    seed_cardinality: int
    prohibited_node_types: tuple[str, ...]
    requires_indexed_access: bool
    max_root_actual_rows: int
    max_rows_examined: int
    rationale: str


@dataclass(frozen=True, slots=True)
class HotPathScenarioCatalog:
    scenarios: tuple[HotPathScenario, ...]
    schema_version: str = CATALOG_SCHEMA_VERSION
    owning_repository: str = "lotus-core"
    evidence_posture: str = EVIDENCE_POSTURE

    def by_id(self) -> dict[str, HotPathScenario]:
        return {scenario.scenario_id: scenario for scenario in self.scenarios}


@dataclass(frozen=True, slots=True)
class HotPathPlanResult:
    scenario_id: str
    status: str
    root_actual_rows: int
    rows_examined: int
    node_types: tuple[str, ...]
    index_names: tuple[str, ...]
    violations: tuple[str, ...]


def load_hot_path_scenario_catalog(path: Path) -> HotPathScenarioCatalog:
    """Load the exact versioned catalog and reject ambiguous or stale shapes."""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DatabaseEvidenceContractError("catalog_unavailable_or_invalid") from exc
    if not isinstance(payload, dict) or set(payload) != _CATALOG_KEYS:
        raise DatabaseEvidenceContractError("catalog_shape_invalid")
    if payload["schema_version"] != CATALOG_SCHEMA_VERSION:
        raise DatabaseEvidenceContractError("catalog_schema_version_unsupported")
    if payload["owning_repository"] != "lotus-core":
        raise DatabaseEvidenceContractError("catalog_owner_invalid")
    if payload["evidence_posture"] != EVIDENCE_POSTURE:
        raise DatabaseEvidenceContractError("catalog_posture_invalid")
    raw_scenarios = payload["scenarios"]
    if not isinstance(raw_scenarios, list) or not raw_scenarios:
        raise DatabaseEvidenceContractError("catalog_scenarios_missing")

    scenarios = tuple(_load_scenario(item) for item in raw_scenarios)
    identifiers = [scenario.scenario_id for scenario in scenarios]
    if len(identifiers) != len(set(identifiers)):
        raise DatabaseEvidenceContractError("catalog_scenario_duplicate")
    if identifiers != sorted(identifiers):
        raise DatabaseEvidenceContractError("catalog_scenario_order_invalid")
    return HotPathScenarioCatalog(scenarios=scenarios)


def _load_scenario(raw: object) -> HotPathScenario:
    if not isinstance(raw, dict) or set(raw) != _SCENARIO_KEYS:
        raise DatabaseEvidenceContractError("catalog_scenario_shape_invalid")
    scenario_id = _required_string(raw, "scenario_id")
    if _SCENARIO_ID.fullmatch(scenario_id) is None:
        raise DatabaseEvidenceContractError("catalog_scenario_id_invalid")
    repository_owner = _required_string(raw, "repository_owner")
    repository_method = _required_string(raw, "repository_method")
    rationale = _required_string(raw, "rationale")
    seed_cardinality = _positive_integer(raw, "seed_cardinality")
    max_root_actual_rows = _positive_integer(raw, "max_root_actual_rows")
    max_rows_examined = _positive_integer(raw, "max_rows_examined")
    if max_root_actual_rows > max_rows_examined:
        raise DatabaseEvidenceContractError("catalog_row_bounds_invalid")
    prohibited = raw["prohibited_node_types"]
    if (
        not isinstance(prohibited, list)
        or not prohibited
        or any(not isinstance(item, str) or not item.strip() for item in prohibited)
        or len(prohibited) != len(set(prohibited))
    ):
        raise DatabaseEvidenceContractError("catalog_prohibited_nodes_invalid")
    requires_indexed_access = raw["requires_indexed_access"]
    if not isinstance(requires_indexed_access, bool):
        raise DatabaseEvidenceContractError("catalog_index_posture_invalid")
    return HotPathScenario(
        scenario_id=scenario_id,
        repository_owner=repository_owner,
        repository_method=repository_method,
        seed_cardinality=seed_cardinality,
        prohibited_node_types=tuple(sorted(prohibited)),
        requires_indexed_access=requires_indexed_access,
        max_root_actual_rows=max_root_actual_rows,
        max_rows_examined=max_rows_examined,
        rationale=rationale,
    )


def _required_string(raw: Mapping[str, object], field: str) -> str:
    value = raw[field]
    if not isinstance(value, str) or not value.strip():
        raise DatabaseEvidenceContractError(f"catalog_{field}_invalid")
    return value.strip()


def _positive_integer(raw: Mapping[str, object], field: str) -> int:
    value = raw[field]
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise DatabaseEvidenceContractError(f"catalog_{field}_invalid")
    return value


def evaluate_hot_path_plan(
    scenario: HotPathScenario,
    plan_payload: object,
) -> HotPathPlanResult:
    """Evaluate one PostgreSQL ANALYZE JSON plan against explicit invariants."""

    root = _plan_root(plan_payload)
    nodes = tuple(_walk_plan_nodes(root))
    node_types = tuple(sorted({_node_type(node) for node in nodes}))
    index_names = tuple(
        sorted(
            {
                value
                for node in nodes
                if isinstance((value := node.get("Index Name")), str) and value.strip()
            }
        )
    )
    root_actual_rows = _non_negative_plan_integer(root, "Actual Rows")
    rows_examined = sum(
        _non_negative_plan_integer(node, "Actual Rows")
        * _non_negative_plan_integer(node, "Actual Loops")
        for node in nodes
    )
    violations: list[str] = []
    prohibited = sorted(set(node_types).intersection(scenario.prohibited_node_types))
    if prohibited:
        violations.append("prohibited_node_type:" + ",".join(prohibited))
    if scenario.requires_indexed_access and not set(node_types).intersection(_INDEX_NODE_TYPES):
        violations.append("indexed_access_missing")
    if root_actual_rows > scenario.max_root_actual_rows:
        violations.append("root_actual_rows_exceeded")
    if rows_examined > scenario.max_rows_examined:
        violations.append("rows_examined_exceeded")
    return HotPathPlanResult(
        scenario_id=scenario.scenario_id,
        status="passed" if not violations else "failed",
        root_actual_rows=root_actual_rows,
        rows_examined=rows_examined,
        node_types=node_types,
        index_names=index_names,
        violations=tuple(violations),
    )


def _plan_root(payload: object) -> Mapping[str, object]:
    envelope: object = payload
    if isinstance(envelope, list) and len(envelope) == 1:
        envelope = envelope[0]
    if not isinstance(envelope, dict) or set(envelope).isdisjoint({"Plan"}):
        raise DatabaseEvidenceContractError("plan_envelope_invalid")
    root = envelope.get("Plan")
    if not isinstance(root, dict):
        raise DatabaseEvidenceContractError("plan_root_invalid")
    return root


def _walk_plan_nodes(root: Mapping[str, object]) -> Iterable[Mapping[str, object]]:
    pending = [root]
    while pending:
        node = pending.pop()
        yield node
        children = node.get("Plans", [])
        if not isinstance(children, list) or any(not isinstance(child, dict) for child in children):
            raise DatabaseEvidenceContractError("plan_children_invalid")
        pending.extend(reversed(children))


def _node_type(node: Mapping[str, object]) -> str:
    value = node.get("Node Type")
    if not isinstance(value, str) or not value.strip():
        raise DatabaseEvidenceContractError("plan_node_type_invalid")
    return value


def _non_negative_plan_integer(node: Mapping[str, object], field: str) -> int:
    value = node.get(field)
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
        raise DatabaseEvidenceContractError("plan_runtime_metric_invalid")
    if int(value) != value:
        raise DatabaseEvidenceContractError("plan_runtime_metric_invalid")
    return int(value)


def build_hot_path_evidence_artifact(
    *,
    catalog: HotPathScenarioCatalog,
    results: Iterable[HotPathPlanResult],
    git_sha: str,
    generated_at: datetime,
) -> dict[str, object]:
    """Build a complete, deterministic-identity, source-safe report artifact."""

    if _GIT_SHA.fullmatch(git_sha) is None:
        raise DatabaseEvidenceContractError("artifact_git_sha_invalid")
    if generated_at.tzinfo is None or generated_at.utcoffset() is None:
        raise DatabaseEvidenceContractError("artifact_generated_at_naive")
    result_list = tuple(results)
    expected_ids = tuple(scenario.scenario_id for scenario in catalog.scenarios)
    observed_ids = tuple(result.scenario_id for result in result_list)
    if observed_ids != expected_ids:
        raise DatabaseEvidenceContractError("artifact_scenario_set_or_order_invalid")
    serialized_results = [asdict(result) for result in result_list]
    identity_payload = {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "catalog_schema_version": catalog.schema_version,
        "owning_repository": catalog.owning_repository,
        "evidence_posture": catalog.evidence_posture,
        "git_sha": git_sha,
        "results": serialized_results,
    }
    content_hash = (
        "sha256:"
        + hashlib.sha256(
            json.dumps(identity_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
    )
    artifact: dict[str, object] = {
        **identity_payload,
        "generated_at_utc": generated_at.astimezone(timezone.utc).isoformat(),
        "status": (
            "passed" if all(result.status == "passed" for result in result_list) else "failed"
        ),
        "content_hash": content_hash,
    }
    _assert_source_safe(artifact)
    return artifact


def write_hot_path_evidence_artifact(path: Path, artifact: Mapping[str, object]) -> None:
    """Write a previously validated artifact without leaking partial output."""

    _assert_source_safe(artifact)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _assert_source_safe(value: object, *, path: tuple[str, ...] = ()) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized_key = str(key).lower()
            if any(part in normalized_key for part in _SENSITIVE_KEY_PARTS):
                raise DatabaseEvidenceContractError("artifact_sensitive_key_forbidden")
            _assert_source_safe(child, path=(*path, str(key)))
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _assert_source_safe(child, path=(*path, str(index)))
    elif isinstance(value, str):
        lowered = value.lower()
        if any(marker in lowered for marker in _SENSITIVE_VALUE_MARKERS):
            raise DatabaseEvidenceContractError("artifact_sensitive_value_forbidden")
