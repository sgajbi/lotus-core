from scripts.architecture_boundary_guard import (
    DirectImportBoundaryRule,
    _scan_for_disallowed_imports,
)


def test_direct_import_boundary_flags_forbidden_absolute_import(tmp_path, monkeypatch) -> None:
    repo_root = tmp_path
    router = (
        repo_root
        / "src"
        / "services"
        / "query_control_plane_service"
        / "app"
        / "routers"
        / "integration.py"
    )
    router.parent.mkdir(parents=True)
    router.write_text(
        "from src.services.query_service.app.repositories.transaction_repository "
        "import TransactionRepository\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("scripts.architecture_boundary_guard.ROOT", repo_root)

    findings = _scan_for_disallowed_imports(
        [router],
        rules=(
            DirectImportBoundaryRule(
                name="test rule",
                source_path_prefixes=("src/services/query_control_plane_service/app/routers/",),
                forbidden_module_prefixes=("services.query_service.app.repositories",),
            ),
        ),
    )

    assert findings == [
        "src/services/query_control_plane_service/app/routers/integration.py:1: "
        "test rule: disallowed direct import "
        "'services.query_service.app.repositories.transaction_repository'"
    ]


def test_direct_import_boundary_ignores_allowed_dto_import(tmp_path, monkeypatch) -> None:
    repo_root = tmp_path
    router = (
        repo_root
        / "src"
        / "services"
        / "query_control_plane_service"
        / "app"
        / "routers"
        / "integration.py"
    )
    router.parent.mkdir(parents=True)
    router.write_text(
        "from src.services.query_service.app.dtos.integration_dto import IntegrationResponse\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("scripts.architecture_boundary_guard.ROOT", repo_root)

    assert (
        _scan_for_disallowed_imports(
            [router],
            rules=(
                DirectImportBoundaryRule(
                    name="test rule",
                    source_path_prefixes=("src/services/query_control_plane_service/app/routers/",),
                    forbidden_module_prefixes=("services.query_service.app.repositories",),
                ),
            ),
        )
        == []
    )
