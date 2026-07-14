from pathlib import Path

from scripts.quality import repository_output_shape_guard as guard


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_repository_output_shape_guard_accepts_current_truth() -> None:
    assert guard.evaluate_repository_output_shapes() == []


def test_cashflow_rule_repository_exception_tracks_domain_owned_package() -> None:
    exception_keys = set(guard.TRANSITIONAL_ORM_RETURN_EXCEPTIONS)

    assert (
        "src/services/portfolio_transaction_processing_service/app/infrastructure/"
        "cashflow/rule_repository.py:get_all_rules" in exception_keys
    )
    assert not any("cashflow_rules_repository.py" in key for key in exception_keys)


def test_repository_output_shape_guard_rejects_unregistered_orm_return(
    tmp_path: Path,
) -> None:
    repository_path = (
        tmp_path / "src" / "services" / "demo_service" / "app" / "repositories" / "demo.py"
    )
    _write(
        repository_path,
        "\n".join(
            [
                "from portfolio_common.database_models import Transaction",
                "",
                "class DemoRepository:",
                "    async def list_transactions(self) -> list[Transaction]:",
                "        return []",
            ]
        ),
    )

    findings = guard.evaluate_repository_output_shapes(
        repo_root=tmp_path,
        source_roots=(tmp_path / "src" / "services",),
        orm_model_names={"Transaction"},
        transitional_exceptions={},
    )

    assert findings == [
        {
            "id": "src/services/demo_service/app/repositories/demo.py:list_transactions",
            "file": "src/services/demo_service/app/repositories/demo.py",
            "line": 4,
            "function": "list_transactions",
            "orm_models": ["Transaction"],
            "violation": (
                "repository method exposes ORM return annotation without a transitional "
                "exception; map to an explicit read/domain record"
            ),
        }
    ]


def test_repository_output_shape_guard_rejects_stale_exception(tmp_path: Path) -> None:
    findings = guard.evaluate_repository_output_shapes(
        repo_root=tmp_path,
        source_roots=(tmp_path / "src",),
        orm_model_names={"Transaction"},
        transitional_exceptions={
            "src/services/demo_service/app/repositories/demo.py:list_transactions": ("Transaction",)
        },
    )

    assert findings == [
        {
            "id": "src/services/demo_service/app/repositories/demo.py:list_transactions",
            "registered_models": ["Transaction"],
            "violation": (
                "stale transitional exception; remove it after the repository output was mapped "
                "to an explicit record"
            ),
        }
    ]


def test_repository_output_shape_guard_accepts_explicit_read_record_return(
    tmp_path: Path,
) -> None:
    repository_path = (
        tmp_path / "src" / "services" / "demo_service" / "app" / "repositories" / "demo.py"
    )
    _write(
        repository_path,
        "\n".join(
            [
                "from portfolio_common.database_models import Transaction",
                "from demo_service.read_models import TransactionReadRecord",
                "",
                "class DemoRepository:",
                "    async def list_transactions(self) -> list[TransactionReadRecord]:",
                "        return []",
            ]
        ),
    )

    assert (
        guard.evaluate_repository_output_shapes(
            repo_root=tmp_path,
            source_roots=(tmp_path / "src" / "services",),
            orm_model_names={"Transaction"},
            transitional_exceptions={},
        )
        == []
    )
