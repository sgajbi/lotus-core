import ast
import json
from pathlib import Path

from src.services.event_replay_service.app.routers.ingestion_operations_examples import (
    INGESTION_OPERATION_EXAMPLES,
)

REPO_ROOT = Path(__file__).resolve().parents[4]
ROUTER_PATH = (
    REPO_ROOT / "src" / "services" / "event_replay_service" / "app" / "routers"
) / "ingestion_operations.py"


def test_ingestion_operations_examples_are_json_serializable() -> None:
    assert len(INGESTION_OPERATION_EXAMPLES) >= 34

    for name, example in INGESTION_OPERATION_EXAMPLES.items():
        assert name.endswith(("_EXAMPLE", "_EXAMPLES"))
        json.dumps(example)


def test_ingestion_operations_router_does_not_own_openapi_example_catalog() -> None:
    module = ast.parse(ROUTER_PATH.read_text(encoding="utf-8"))

    router_owned_examples = [
        node.targets[0].id
        for node in module.body
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id.endswith(("_EXAMPLE", "_EXAMPLES"))
    ]

    assert router_owned_examples == []
