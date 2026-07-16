"""Keep Kafka autoscaling identities and limits aligned with governed topics."""

from pathlib import Path

import yaml
from portfolio_common.config import KAFKA_TOPIC_PARTITION_COUNTS

REPO_ROOT = Path(__file__).resolve().parents[3]
KEDA_MANIFEST = REPO_ROOT / "deployment/kubernetes/keda/processing-scaledobjects.yaml"


def _scaled_objects() -> list[dict[str, object]]:
    return [
        document
        for document in yaml.safe_load_all(KEDA_MANIFEST.read_text(encoding="utf-8"))
        if document
    ]


def test_kafka_scalers_use_current_consumer_groups_and_topics() -> None:
    resources = {resource["metadata"]["name"]: resource for resource in _scaled_objects()}

    valuation_trigger = resources["valuation-calculator-scaledobject"]["spec"]["triggers"][0][
        "metadata"
    ]
    assert valuation_trigger["consumerGroup"] == "position_valuation_worker_group"
    assert valuation_trigger["topic"] == "valuation.job.requested"


def test_kafka_scaler_replica_limits_do_not_exceed_topic_partitions() -> None:
    for resource in _scaled_objects():
        max_replicas = resource["spec"]["maxReplicaCount"]
        for trigger in resource["spec"]["triggers"]:
            topic = trigger["metadata"]["topic"]
            assert max_replicas <= KAFKA_TOPIC_PARTITION_COUNTS[topic]
