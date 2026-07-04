from pathlib import Path

from scripts.application_layer_contract_guard import (
    find_application_layer_contract_findings,
)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_application_layer_contract_guard_allows_pure_application_modules(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path / "src/services/example_service/app/application/use_case.py",
        "from dataclasses import dataclass\n"
        "from ..ports.example_port import ExamplePort\n"
        "@dataclass\n"
        "class ExampleCommand:\n"
        "    identifier: str\n",
    )

    assert find_application_layer_contract_findings(tmp_path) == []


def test_application_layer_contract_guard_rejects_framework_and_infrastructure_imports(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path / "src/services/example_service/app/application/use_case.py",
        "from fastapi import Depends\n"
        "from sqlalchemy.ext.asyncio import AsyncSession\n"
        "from ..repositories.example_repository import ExampleRepository\n"
        "from ..producers.kafka import KafkaProducer, get_kafka_producer\n",
    )

    findings = find_application_layer_contract_findings(tmp_path)

    assert [finding.snippet for finding in findings] == [
        "from fastapi",
        "from sqlalchemy",
        "KafkaProducer",
        "get_kafka_producer",
        "from ..repositories",
        "from ..producers",
    ]
