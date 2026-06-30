from scripts.architecture_boundary_guard import (
    DirectImportBoundaryRule,
    _scan_for_disallowed_imports,
    _scan_for_service_runtime_imports,
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


def test_direct_import_boundary_flags_event_replay_router_kafka_import(
    tmp_path, monkeypatch
) -> None:
    repo_root = tmp_path
    router = (
        repo_root
        / "src"
        / "services"
        / "event_replay_service"
        / "app"
        / "routers"
        / "ingestion_operations.py"
    )
    router.parent.mkdir(parents=True)
    router.write_text(
        "from portfolio_common.kafka_utils import KafkaProducer, get_kafka_producer\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("scripts.architecture_boundary_guard.ROOT", repo_root)

    findings = _scan_for_disallowed_imports(
        [router],
        rules=(
            DirectImportBoundaryRule(
                name="event-replay routers must not import concrete Kafka utilities",
                source_path_prefixes=("src/services/event_replay_service/app/routers/",),
                forbidden_module_prefixes=("portfolio_common.kafka_utils",),
            ),
        ),
    )

    assert findings == [
        "src/services/event_replay_service/app/routers/ingestion_operations.py:1: "
        "event-replay routers must not import concrete Kafka utilities: "
        "disallowed direct import 'portfolio_common.kafka_utils'"
    ]


def test_direct_import_boundary_flags_valuation_scheduler_kafka_import(
    tmp_path, monkeypatch
) -> None:
    repo_root = tmp_path
    scheduler = (
        repo_root
        / "src"
        / "services"
        / "valuation_orchestrator_service"
        / "app"
        / "core"
        / "valuation_scheduler.py"
    )
    scheduler.parent.mkdir(parents=True)
    scheduler.write_text(
        "from portfolio_common.kafka_utils import KafkaProducer, get_kafka_producer\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("scripts.architecture_boundary_guard.ROOT", repo_root)

    findings = _scan_for_disallowed_imports(
        [scheduler],
        rules=(
            DirectImportBoundaryRule(
                name="valuation scheduler must not import concrete Kafka utilities",
                source_path_prefixes=(
                    "src/services/valuation_orchestrator_service/app/core/valuation_scheduler.py",
                ),
                forbidden_module_prefixes=("portfolio_common.kafka_utils",),
            ),
        ),
    )

    assert findings == [
        "src/services/valuation_orchestrator_service/app/core/valuation_scheduler.py:1: "
        "valuation scheduler must not import concrete Kafka utilities: "
        "disallowed direct import 'portfolio_common.kafka_utils'"
    ]


def test_direct_import_boundary_flags_reconciliation_runtime_provider_bypass(
    tmp_path, monkeypatch
) -> None:
    repo_root = tmp_path
    service = (
        repo_root
        / "src"
        / "services"
        / "financial_reconciliation_service"
        / "app"
        / "services"
        / "reconciliation_service.py"
    )
    service.parent.mkdir(parents=True)
    service.write_text(
        "from time import perf_counter\nfrom uuid import uuid4\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("scripts.architecture_boundary_guard.ROOT", repo_root)

    findings = _scan_for_disallowed_imports(
        [service],
        rules=(
            DirectImportBoundaryRule(
                name="financial reconciliation service must use runtime provider ports",
                source_path_prefixes=(
                    "src/services/financial_reconciliation_service/app/services/"
                    "reconciliation_service.py",
                ),
                forbidden_module_prefixes=("time", "uuid"),
            ),
        ),
    )

    assert findings == [
        "src/services/financial_reconciliation_service/app/services/"
        "reconciliation_service.py:1: "
        "financial reconciliation service must use runtime provider ports: "
        "disallowed direct import 'time'",
        "src/services/financial_reconciliation_service/app/services/"
        "reconciliation_service.py:2: "
        "financial reconciliation service must use runtime provider ports: "
        "disallowed direct import 'uuid'",
    ]


def test_service_runtime_import_guard_flags_own_repo_root_import(tmp_path, monkeypatch) -> None:
    repo_root = tmp_path
    service_module = (
        repo_root
        / "src"
        / "services"
        / "query_service"
        / "app"
        / "advisory_simulation"
        / "valuation.py"
    )
    service_module.parent.mkdir(parents=True)
    service_module.write_text(
        "from src.services.query_service.app.advisory_simulation.models import "
        "ProposalSimulateRequest\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("scripts.architecture_boundary_guard.ROOT", repo_root)

    assert _scan_for_service_runtime_imports([service_module]) == [
        "src/services/query_service/app/advisory_simulation/valuation.py:1: "
        "service runtime packages must not import their own app through repo-root module "
        "path 'services.query_service.app.advisory_simulation.models'; use package-local "
        "'app...' or relative imports"
    ]


def test_service_runtime_import_guard_allows_package_local_import(tmp_path, monkeypatch) -> None:
    repo_root = tmp_path
    service_module = (
        repo_root
        / "src"
        / "services"
        / "query_service"
        / "app"
        / "advisory_simulation"
        / "valuation.py"
    )
    service_module.parent.mkdir(parents=True)
    service_module.write_text(
        "from app.advisory_simulation.models import ProposalSimulateRequest\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("scripts.architecture_boundary_guard.ROOT", repo_root)

    assert _scan_for_service_runtime_imports([service_module]) == []
