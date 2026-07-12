import re
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
BASE_MANIFEST = (
    REPO_ROOT / "deployment" / "kubernetes" / "base" / "portfolio-transaction-processing.yaml"
)
KEDA_MANIFEST = REPO_ROOT / "deployment" / "kubernetes" / "keda" / "processing-scaledobjects.yaml"
LEGACY_WORKER_NAMES = {
    "cost-calculator",
    "cashflow-calculator",
    "position-calculator",
}


def _documents(path: Path) -> list[dict[str, Any]]:
    return [document for document in yaml.safe_load_all(path.read_text(encoding="utf-8"))]


def _resource(documents: list[dict[str, Any]], kind: str) -> dict[str, Any]:
    return next(document for document in documents if document["kind"] == kind)


def test_transaction_processing_deployment_is_digest_pinned_and_hardened() -> None:
    documents = _documents(BASE_MANIFEST)
    assert {document["kind"] for document in documents} == {
        "ServiceAccount",
        "Deployment",
        "Service",
        "PodDisruptionBudget",
    }
    deployment = _resource(documents, "Deployment")
    pod_spec = deployment["spec"]["template"]["spec"]
    container = pod_spec["containers"][0]

    assert deployment["metadata"]["name"] == "portfolio-transaction-processing"
    assert deployment["metadata"]["annotations"]["lotus.io/image-promotion-policy"] == (
        "same-digest"
    )
    assert re.fullmatch(r".+@sha256:[0-9a-f]{64}", container["image"])
    assert ":latest" not in container["image"]
    assert pod_spec["automountServiceAccountToken"] is False
    assert pod_spec["terminationGracePeriodSeconds"] >= 60
    assert pod_spec["securityContext"]["runAsNonRoot"] is True
    assert pod_spec["securityContext"]["seccompProfile"]["type"] == "RuntimeDefault"
    assert container["securityContext"] == {
        "allowPrivilegeEscalation": False,
        "readOnlyRootFilesystem": True,
        "capabilities": {"drop": ["ALL"]},
    }
    assert container["startupProbe"]["httpGet"]["path"] == "/health/live"
    assert container["livenessProbe"]["httpGet"]["path"] == "/health/live"
    assert container["readinessProbe"]["httpGet"]["path"] == "/health/ready"
    assert container["resources"]["requests"]
    assert container["resources"]["limits"]


def test_transaction_processing_deployment_uses_external_runtime_configuration() -> None:
    deployment = _resource(_documents(BASE_MANIFEST), "Deployment")
    container = deployment["spec"]["template"]["spec"]["containers"][0]
    environment = {item["name"]: item for item in container["env"]}

    assert environment["DATABASE_URL"]["valueFrom"]["secretKeyRef"] == {
        "name": "lotus-core-database",
        "key": "database-url",
    }
    assert environment["KAFKA_BOOTSTRAP_SERVERS"]["valueFrom"]["configMapKeyRef"] == {
        "name": "lotus-core-runtime",
        "key": "kafka-bootstrap-servers",
    }


def test_keda_scales_one_transaction_runtime_from_live_and_replay_lag() -> None:
    scaled_objects = _documents(KEDA_MANIFEST)
    transaction_scaler = next(
        item
        for item in scaled_objects
        if item["metadata"]["name"] == "portfolio-transaction-processing"
    )
    metadata = [trigger["metadata"] for trigger in transaction_scaler["spec"]["triggers"]]

    assert transaction_scaler["spec"]["scaleTargetRef"]["name"] == (
        "portfolio-transaction-processing"
    )
    assert transaction_scaler["spec"]["minReplicaCount"] >= 2
    assert {
        (item["consumerGroup"], item["topic"], item["offsetResetPolicy"]) for item in metadata
    } == {
        (
            "portfolio_transaction_processing_group",
            "transactions.persisted",
            "earliest",
        ),
        (
            "portfolio_transaction_replay_request_group",
            "transactions.reprocessing.requested",
            "earliest",
        ),
    }


def test_kubernetes_scaling_inventory_contains_no_legacy_transaction_worker() -> None:
    manifest_text = "\n".join(
        path.read_text(encoding="utf-8") for path in (BASE_MANIFEST, KEDA_MANIFEST)
    )

    assert not any(name in manifest_text for name in LEGACY_WORKER_NAMES)
