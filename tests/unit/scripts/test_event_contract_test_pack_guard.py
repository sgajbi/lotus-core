from __future__ import annotations

import copy
import json
from pathlib import Path

from scripts import event_contract_test_pack_guard as guard


def _write_repo(tmp_path: Path) -> None:
    (tmp_path / "tests/unit").mkdir(parents=True)
    for filename in (
        "producer.py",
        "consumer.py",
        "headers.py",
        "dlq.py",
    ):
        (tmp_path / "tests/unit" / filename).write_text(
            "def test_placeholder():\n    assert True\n",
            encoding="utf-8",
        )
    (tmp_path / "Makefile").write_text(
        "event-contract-test-pack-guard:\n\tpython scripts/event_contract_test_pack_guard.py\n",
        encoding="utf-8",
    )


def _minimal_pack() -> dict[str, object]:
    return {
        "schema_version": "lotus-core.event-contract-test-pack.v1",
        "owning_repository": "lotus-core",
        "gate_command": "make event-contract-test-pack-guard",
        "accepted_event_schema_versions": ["1.0.0"],
        "compatibility_policy": {"breaking_change": "new version required"},
        "evidence_profiles": {
            "profile": {
                "producer_evidence": ["tests/unit/producer.py"],
                "consumer_evidence": ["tests/unit/consumer.py"],
                "header_and_lineage_evidence": ["tests/unit/headers.py"],
                "dlq_replay_evidence": ["tests/unit/dlq.py"],
            }
        },
        "event_families": [
            {
                "event_type": definition.event_type,
                "topic": definition.topic,
                "schema_model": definition.schema_model,
                "evidence_profile": "profile",
                "partition_key_policy": "test",
            }
            for definition in guard.EVENT_FAMILY_DEFINITIONS
        ],
        "direct_kafka_topics": [
            {
                "name": definition.name,
                "topic": definition.topic,
                "payload_contract": definition.payload_contract,
                "evidence_profile": "profile",
                "partition_key_policy": "test",
            }
            for definition in guard.DIRECT_KAFKA_TOPIC_DEFINITIONS
        ],
    }


def test_current_event_contract_test_pack_is_valid() -> None:
    pack = json.loads((guard.REPO_ROOT / guard.PACK_PATH).read_text(encoding="utf-8"))

    assert guard.validate_event_contract_test_pack(pack) == []


def test_guard_accepts_minimal_valid_pack(tmp_path: Path) -> None:
    _write_repo(tmp_path)

    assert guard.validate_event_contract_test_pack(_minimal_pack(), repo_root=tmp_path) == []


def test_guard_rejects_event_family_missing_from_pack(tmp_path: Path) -> None:
    _write_repo(tmp_path)
    pack = _minimal_pack()
    pack["event_families"] = pack["event_families"][1:]

    findings = guard.validate_event_contract_test_pack(pack, repo_root=tmp_path)

    assert {
        "event_families_missing_from_pack": [guard.EVENT_FAMILY_DEFINITIONS[0].event_type]
    } in findings


def test_guard_rejects_direct_topic_contract_drift(tmp_path: Path) -> None:
    _write_repo(tmp_path)
    pack = _minimal_pack()
    direct_topics = pack["direct_kafka_topics"]
    direct_topics[0] = {**direct_topics[0], "topic": "wrong.topic"}

    findings = guard.validate_event_contract_test_pack(pack, repo_root=tmp_path)

    assert {
        "direct_topic": guard.DIRECT_KAFKA_TOPIC_DEFINITIONS[0].name,
        "field": "topic",
        "actual": "wrong.topic",
        "expected": guard.DIRECT_KAFKA_TOPIC_DEFINITIONS[0].topic,
    } in findings


def test_guard_rejects_missing_evidence_refs(tmp_path: Path) -> None:
    _write_repo(tmp_path)
    pack = copy.deepcopy(_minimal_pack())
    pack["evidence_profiles"]["profile"]["producer_evidence"] = ["tests/unit/missing.py"]

    findings = guard.validate_event_contract_test_pack(pack, repo_root=tmp_path)

    assert {
        "profile": "profile",
        "evidence_key": "producer_evidence",
        "missing_refs": ["tests/unit/missing.py"],
    } in findings
