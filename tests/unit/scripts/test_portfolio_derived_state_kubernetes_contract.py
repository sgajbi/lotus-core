"""Protect the immutable deployment contract for portfolio derived-state workers."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
BASE_MANIFEST = REPO_ROOT / "deployment/kubernetes/base/portfolio-derived-state.yaml"
KEDA_MANIFEST = REPO_ROOT / "deployment/kubernetes/keda/processing-scaledobjects.yaml"
RETIRED_DEPLOYMENT_IDENTITIES = {
    "timeseries-generator",
    "portfolio-aggregation",
}


def _documents(path: Path) -> list[dict[str, Any]]:
    """Load all non-empty Kubernetes resources from a YAML manifest."""

    return [document for document in yaml.safe_load_all(path.read_text(encoding="utf-8"))]


def _resource(documents: list[dict[str, Any]], kind: str) -> dict[str, Any]:
    """Return the only resource of the requested kind."""

    return next(document for document in documents if document["kind"] == kind)


def test_portfolio_derived_state_deployment_is_digest_pinned_and_hardened() -> None:
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

    assert deployment["metadata"]["name"] == "portfolio-derived-state"
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


def test_portfolio_derived_state_deployment_uses_external_runtime_configuration() -> None:
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
    optional_tuning_keys = {
        "PORTFOLIO_AGGREGATION_WORKER_COUNT": "portfolio-aggregation-worker-count",
        "AGGREGATION_JOB_LEASE_DURATION_SECONDS": "aggregation-job-lease-duration-seconds",
        "AGGREGATION_SCHEDULER_POLL_INTERVAL_SECONDS": (
            "aggregation-scheduler-poll-interval-seconds"
        ),
        "AGGREGATION_SCHEDULER_BATCH_SIZE": "aggregation-scheduler-batch-size",
    }
    assert {
        name: environment[name]["valueFrom"]["configMapKeyRef"] for name in optional_tuning_keys
    } == {
        name: {
            "name": "lotus-core-runtime",
            "key": key,
            "optional": True,
        }
        for name, key in optional_tuning_keys.items()
    }


def test_keda_scales_one_derived_state_runtime_from_preserved_position_group() -> None:
    scaled_objects = _documents(KEDA_MANIFEST)
    scaler = next(
        item for item in scaled_objects if item["metadata"]["name"] == "portfolio-derived-state"
    )

    assert scaler["spec"]["scaleTargetRef"]["name"] == "portfolio-derived-state"
    assert scaler["spec"]["minReplicaCount"] >= 1
    assert [trigger["metadata"] for trigger in scaler["spec"]["triggers"]] == [
        {
            "bootstrapServers": "kafka:9092",
            "consumerGroup": "timeseries_generator_group_positions",
            "topic": "valuation.snapshot.persisted",
            "lagThreshold": "400",
            "offsetResetPolicy": "latest",
        }
    ]


def test_deployment_inventory_contains_no_retired_derived_state_runtime() -> None:
    resources = _documents(BASE_MANIFEST) + _documents(KEDA_MANIFEST)
    deployed_identities = {resource["metadata"]["name"] for resource in resources}
    deployed_identities.update(
        resource["spec"]["scaleTargetRef"]["name"]
        for resource in resources
        if resource["kind"] == "ScaledObject"
    )
    deployed_images = {
        container["image"]
        for resource in resources
        if resource["kind"] == "Deployment"
        for container in resource["spec"]["template"]["spec"]["containers"]
    }

    assert RETIRED_DEPLOYMENT_IDENTITIES.isdisjoint(deployed_identities)
    assert not any(
        identity in image for identity in RETIRED_DEPLOYMENT_IDENTITIES for image in deployed_images
    )
