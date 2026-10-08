"""Protect booked transaction replay infrastructure ownership."""

import ast
from importlib.util import resolve_name
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[6]
_REPLAY = (
    "src.services.portfolio_transaction_processing_service.app.infrastructure.transaction_replay"
)


def test_booked_transaction_replay_uses_domain_owned_package() -> None:
    source_root = (
        REPOSITORY_ROOT / "src/services/portfolio_transaction_processing_service/app/infrastructure"
    )
    root_exports = (source_root / "__init__.py").read_text(encoding="utf-8")

    assert (source_root / "transaction_replay/booked_transaction.py").is_file()
    assert not (source_root / "transaction_replay_adapter.py").exists()
    assert not (
        REPOSITORY_ROOT / "tests/unit/services/portfolio_transaction_processing_service/"
        "test_transaction_replay_adapter.py"
    ).exists()
    assert "SqlAlchemyBookedTransactionReplayAdapter" not in root_exports
    assert "CanonicalTransactionReplayer" not in root_exports


def _assert_fee_owner_dependencies(authority, repository, transport):
    package = (
        "src.services.portfolio_transaction_processing_serv"
        "ice.app.infrastructure.transaction_replay"
    )
    trees = [ast.parse(source) for source in [authority, repository, transport]]
    imports = []
    for tree in trees:
        dependencies = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                dependencies.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                base = (
                    resolve_name("." * node.level + (node.module or ""), package)
                    if node.level
                    else (node.module or "")
                )
                dependencies.add(base)
                dependencies.update(base + "." + alias.name for alias in node.names)
        imports.append(dependencies)
    repository_owner = package + ".fee_source_repository"
    transport_owner = package + ".booked_transaction"
    assert not any(
        name == owner or name.startswith(owner + ".")
        for name in imports[0]
        for owner in [
            "sqlalchemy",
            "portfolio_common.reprocessing_repository",
            repository_owner,
            transport_owner,
        ]
    )
    assert package + ".fee_authority" in imports[1]
    assert not any(
        name == transport_owner or name.startswith(transport_owner + ".") for name in imports[1]
    )
    assert repository_owner in imports[2]
    assert not any(isinstance(node, ast.AsyncFunctionDef) for node in ast.walk(trees[0]))


def test_fee_authority_repository_transport_dependencies_are_acyclic():
    source = REPOSITORY_ROOT / (
        "src/services/portfolio_transaction_processing_serv"
        "ice/app/infrastructure/transaction_replay"
    )
    modules = [
        (source / name).read_text(encoding="utf-8")
        for name in ["fee_authority.py", "fee_source_repository.py", "booked_transaction.py"]
    ]
    _assert_fee_owner_dependencies(*modules)


@pytest.mark.parametrize(
    "bad_import",
    [
        "import sqlalchemy",
        "from .fee_source_repository import load_qualified_transaction_fee_sources",
        "from . import fee_source_repository",
        (
            "from src.services.portfolio_transaction_processing_service.app.infrastructure."
            "transaction_replay import fee_source_repository"
        ),
        (
            "from src.services.portfolio_transaction_processing_service.app.infrastructure."
            "transaction_replay import booked_transaction as replay"
        ),
        (
            "from src.services.portfolio_transaction_processing"
            "_service.app.infrastructure.transaction_replay.fee"
            "_source_repository import load_qualified_transacti"
            "on_fee_sources"
        ),
        (
            "import src.services.portfolio_transaction_processi"
            "ng_service.app.infrastructure.transaction_replay.b"
            "ooked_transaction"
        ),
    ],
)
def test_fee_boundary_guard_rejects_database_and_reverse_dependencies(bad_import):
    with pytest.raises(AssertionError):
        _assert_fee_owner_dependencies(
            bad_import,
            "from .fee_authority import qualify_transaction_fee_source",
            ("from .fee_source_repository import load_qualified_transaction_fee_sources"),
        )


def test_fee_boundary_guard_accepts_domain_mapping_without_transport_alias():
    _assert_fee_owner_dependencies(
        ("from ..transaction_mapping.booked_transaction import to_booked_transaction"),
        "from .fee_authority import qualify_transaction_fee_source",
        ("from .fee_source_repository import load_qualified_transaction_fee_sources"),
    )


@pytest.mark.parametrize(
    "bad_repository_import",
    [
        "from .booked_transaction import SqlAlchemyQualifiedTransactionReplayReader",
        "from . import booked_transaction",
        f"from {_REPLAY}.booked_transaction import SqlAlchemyQualifiedTransactionReplayReader",
        (
            "from src.services.portfolio_transaction_processing_service.app.infrastructure."
            "transaction_replay import booked_transaction as replay"
        ),
    ],
)
def test_fee_repository_cannot_import_replay_transport(bad_repository_import):
    with pytest.raises(AssertionError):
        _assert_fee_owner_dependencies(
            "from ..transaction_mapping.booked_transaction import to_booked_transaction",
            "from .fee_authority import qualify_transaction_fee_source\n" + bad_repository_import,
            "from .fee_source_repository import load_qualified_transaction_fee_sources",
        )
