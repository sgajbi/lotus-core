import json
from pathlib import Path

import pytest

from scripts.testability_architecture_guard import (
    find_testability_architecture_findings,
)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_contract(root: Path) -> None:
    _write(
        root / "docs/standards/testability-architecture-contract.json",
        json.dumps(
            {
                "protectedPathGlobs": [
                    "src/services/**/app/application/**/*.py",
                    "src/services/**/app/ports/**/*.py",
                    "src/services/**/app/domain/**/*.py",
                ],
                "forbiddenImportPrefixes": [
                    "fastapi",
                    "portfolio_common.db",
                    "portfolio_common.kafka_utils",
                    "sqlalchemy",
                ],
                "forbiddenImportParts": [
                    "dependencies",
                    "repositories",
                    "repository",
                ],
                "forbiddenSymbols": [
                    "AsyncSession",
                    "Depends",
                    "KafkaProducer",
                    "get_async_db_session",
                    "get_kafka_producer",
                ],
            },
            indent=2,
        ),
    )


def test_testability_architecture_guard_allows_ports_and_fakes(
    tmp_path: Path,
) -> None:
    _write_contract(tmp_path)
    _write(
        tmp_path / "src/services/example/app/ports/example_ports.py",
        "from typing import Protocol\n\n"
        "class ExampleReader(Protocol):\n"
        "    def read(self) -> str: ...\n",
    )
    _write(
        tmp_path / "src/services/example/app/application/example_use_case.py",
        "from ..ports.example_ports import ExampleReader\n\n"
        "class FakeReader:\n"
        "    def read(self) -> str:\n"
        "        return 'ok'\n",
    )

    assert find_testability_architecture_findings(tmp_path) == []


def test_testability_architecture_guard_rejects_runtime_imports(
    tmp_path: Path,
) -> None:
    _write_contract(tmp_path)
    _write(
        tmp_path / "src/services/example/app/application/example_use_case.py",
        "from fastapi import Depends\n"
        "from portfolio_common.db import get_async_db_session\n"
        "from sqlalchemy.ext.asyncio import AsyncSession\n"
        "from portfolio_common.kafka_utils import get_kafka_producer\n\n"
        "def build(db: AsyncSession = Depends(get_async_db_session)):\n"
        "    return get_kafka_producer()\n",
    )

    findings = find_testability_architecture_findings(tmp_path)

    assert [finding.rule for finding in findings] == [
        "forbidden-runtime-import",
        "forbidden-runtime-symbol",
        "forbidden-runtime-import",
        "forbidden-runtime-symbol",
        "forbidden-runtime-import",
        "forbidden-runtime-symbol",
        "forbidden-runtime-import",
        "forbidden-runtime-symbol",
        "forbidden-runtime-call",
        "forbidden-runtime-call",
    ]


def test_testability_architecture_guard_rejects_repository_layer_imports(
    tmp_path: Path,
) -> None:
    _write_contract(tmp_path)
    _write(
        tmp_path / "src/services/example/app/application/example_use_case.py",
        "from ..repositories.example_repository import ExampleRepository\n"
        "from ..dependencies import build_repository\n",
    )

    findings = find_testability_architecture_findings(tmp_path)

    assert [(finding.rule, finding.detail) for finding in findings] == [
        (
            "forbidden-layer-import",
            "imports '..repositories.example_repository' through layer 'repositories'",
        ),
        (
            "forbidden-layer-import",
            "imports '..dependencies' through layer 'dependencies'",
        ),
    ]


def test_testability_architecture_guard_rejects_invalid_contract(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path / "docs/standards/testability-architecture-contract.json",
        json.dumps({"protectedPathGlobs": "src/**/*.py"}),
    )

    with pytest.raises(ValueError, match="protectedPathGlobs must be a string list"):
        find_testability_architecture_findings(tmp_path)
