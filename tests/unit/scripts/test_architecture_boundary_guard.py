from scripts.quality.architecture_boundary_guard import (
    DIRECT_IMPORT_BOUNDARY_RULES,
    ApiRouterBoundaryViolation,
    DirectImportBoundaryRule,
    _evaluate_api_router_boundary,
    _scan_api_router_boundary_violations,
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
    monkeypatch.setattr("scripts.quality.architecture_boundary_guard.ROOT", repo_root)

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


def test_calculator_boundary_rejects_orchestrator_internal_import(tmp_path, monkeypatch) -> None:
    source = (
        tmp_path
        / "src"
        / "services"
        / "calculators"
        / "cost_calculator_service"
        / "app"
        / "consumer.py"
    )
    source.parent.mkdir(parents=True)
    source.write_text(
        "from src.services.valuation_orchestrator_service.app.core "
        "import valuation_scheduler\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("scripts.quality.architecture_boundary_guard.ROOT", tmp_path)

    findings = _scan_for_disallowed_imports(
        [source],
        rules=DIRECT_IMPORT_BOUNDARY_RULES,
    )

    assert findings == [
        "src/services/calculators/cost_calculator_service/app/consumer.py:1: "
        "calculator modules must not import orchestrator or query internals: disallowed direct "
        "import 'services.valuation_orchestrator_service.app.core'"
    ]


def test_transaction_processing_boundary_rejects_orchestrator_internal_import(
    tmp_path, monkeypatch
) -> None:
    source = (
        tmp_path
        / "src"
        / "services"
        / "portfolio_transaction_processing_service"
        / "app"
        / "application"
        / "process_transaction.py"
    )
    source.parent.mkdir(parents=True)
    source.write_text(
        "from src.services.valuation_orchestrator_service.app.core "
        "import valuation_scheduler\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("scripts.quality.architecture_boundary_guard.ROOT", tmp_path)

    findings = _scan_for_disallowed_imports(
        [source],
        rules=DIRECT_IMPORT_BOUNDARY_RULES,
    )

    assert findings == [
        "src/services/portfolio_transaction_processing_service/app/application/"
        "process_transaction.py:1: transaction processing must not import orchestrator or query "
        "internals: disallowed direct import "
        "'services.valuation_orchestrator_service.app.core'"
    ]


def test_orchestrator_boundary_rejects_calculator_internal_import(tmp_path, monkeypatch) -> None:
    source = (
        tmp_path
        / "src"
        / "services"
        / "valuation_orchestrator_service"
        / "app"
        / "core"
        / "valuation_scheduler.py"
    )
    source.parent.mkdir(parents=True)
    source.write_text(
        "from src.services.calculators.cost_calculator_service.app.consumer "
        "import CostCalculatorConsumer\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("scripts.quality.architecture_boundary_guard.ROOT", tmp_path)

    findings = _scan_for_disallowed_imports(
        [source],
        rules=DIRECT_IMPORT_BOUNDARY_RULES,
    )

    assert findings == [
        "src/services/valuation_orchestrator_service/app/core/"
        "valuation_scheduler.py:1: valuation orchestrator must not import calculator or query "
        "internals: disallowed direct import "
        "'services.calculators.cost_calculator_service.app.consumer'"
    ]


def test_orchestrator_boundary_rejects_transaction_processing_internal_import(
    tmp_path, monkeypatch
) -> None:
    source = (
        tmp_path
        / "src"
        / "services"
        / "valuation_orchestrator_service"
        / "app"
        / "core"
        / "valuation_scheduler.py"
    )
    source.parent.mkdir(parents=True)
    source.write_text(
        "from src.services.portfolio_transaction_processing_service.app.application "
        "import ProcessTransactionUseCase\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("scripts.quality.architecture_boundary_guard.ROOT", tmp_path)

    findings = _scan_for_disallowed_imports(
        [source],
        rules=DIRECT_IMPORT_BOUNDARY_RULES,
    )

    assert findings == [
        "src/services/valuation_orchestrator_service/app/core/"
        "valuation_scheduler.py:1: valuation orchestrator must not import calculator or query "
        "internals: disallowed direct import "
        "'services.portfolio_transaction_processing_service.app.application'"
    ]


def test_transaction_processing_application_rejects_event_dto_import(tmp_path, monkeypatch) -> None:
    source = (
        tmp_path
        / "src"
        / "services"
        / "portfolio_transaction_processing_service"
        / "app"
        / "application"
        / "process_transaction.py"
    )
    source.parent.mkdir(parents=True)
    source.write_text(
        "from portfolio_common.events import TransactionEvent\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("scripts.quality.architecture_boundary_guard.ROOT", tmp_path)

    findings = _scan_for_disallowed_imports(
        [source],
        rules=DIRECT_IMPORT_BOUNDARY_RULES,
    )

    assert findings == [
        "src/services/portfolio_transaction_processing_service/app/application/"
        "process_transaction.py:1: transaction processing domain and application must not "
        "import event DTOs: disallowed direct import 'portfolio_common.events'"
    ]


def test_generic_simulation_rejects_absolute_advisory_decisioning_import(
    tmp_path, monkeypatch
) -> None:
    source = (
        tmp_path
        / "src"
        / "services"
        / "query_control_plane_service"
        / "app"
        / "application"
        / "simulation.py"
    )
    source.parent.mkdir(parents=True)
    source.write_text(
        "from src.services.query_control_plane_service.app.contracts."
        "advisory_simulation_models import SuitabilityResult\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("scripts.quality.architecture_boundary_guard.ROOT", tmp_path)

    findings = _scan_for_disallowed_imports([source], rules=DIRECT_IMPORT_BOUNDARY_RULES)

    assert findings == [
        "src/services/query_control_plane_service/app/application/simulation.py:1: "
        "generic simulation must not import advisory decisioning: disallowed direct import "
        "'services.query_control_plane_service.app.contracts.advisory_simulation_models'"
    ]


def test_generic_simulation_rejects_relative_advisory_decisioning_import(
    tmp_path, monkeypatch
) -> None:
    source = (
        tmp_path
        / "src"
        / "services"
        / "query_control_plane_service"
        / "app"
        / "application"
        / "simulation.py"
    )
    source.parent.mkdir(parents=True)
    source.write_text(
        "from .advisory_simulation_service import execute_advisory_simulation\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("scripts.quality.architecture_boundary_guard.ROOT", tmp_path)

    findings = _scan_for_disallowed_imports([source], rules=DIRECT_IMPORT_BOUNDARY_RULES)

    assert findings == [
        "src/services/query_control_plane_service/app/application/simulation.py:1: "
        "generic simulation must not import advisory decisioning: disallowed direct import "
        "'advisory_simulation_service'"
    ]


def test_advisory_compatibility_route_rejects_query_service_import(tmp_path, monkeypatch) -> None:
    source = (
        tmp_path
        / "src"
        / "services"
        / "query_control_plane_service"
        / "app"
        / "routers"
        / "advisory_simulation.py"
    )
    source.parent.mkdir(parents=True)
    source.write_text(
        "from src.services.query_service.app.services.advisory_simulation_service "
        "import execute_advisory_simulation\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("scripts.quality.architecture_boundary_guard.ROOT", tmp_path)

    assert _scan_for_disallowed_imports([source], rules=DIRECT_IMPORT_BOUNDARY_RULES) == [
        "src/services/query_control_plane_service/app/routers/advisory_simulation.py:1: "
        "advisory simulation compatibility must remain control-plane owned: disallowed direct "
        "import 'services.query_service.app.services.advisory_simulation_service'"
    ]


def test_advisory_application_rejects_direct_uuid_import(tmp_path, monkeypatch) -> None:
    source = (
        tmp_path
        / "src"
        / "services"
        / "query_control_plane_service"
        / "app"
        / "application"
        / "advisory_simulation"
        / "service.py"
    )
    source.parent.mkdir(parents=True)
    source.write_text("import uuid\n", encoding="utf-8")
    monkeypatch.setattr("scripts.quality.architecture_boundary_guard.ROOT", tmp_path)

    assert _scan_for_disallowed_imports([source], rules=DIRECT_IMPORT_BOUNDARY_RULES) == [
        "src/services/query_control_plane_service/app/application/advisory_simulation/"
        "service.py:1: advisory simulation application must use runtime identity ports: "
        "disallowed direct import 'uuid'"
    ]


def test_query_control_plane_capabilities_reject_query_service_import(
    tmp_path, monkeypatch
) -> None:
    source = (
        tmp_path
        / "src"
        / "services"
        / "query_control_plane_service"
        / "app"
        / "application"
        / "capabilities_service.py"
    )
    source.parent.mkdir(parents=True)
    source.write_text(
        "from src.services.query_service.app.settings import load_query_service_settings\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("scripts.quality.architecture_boundary_guard.ROOT", tmp_path)

    findings = _scan_for_disallowed_imports([source], rules=DIRECT_IMPORT_BOUNDARY_RULES)

    assert findings == [
        "src/services/query_control_plane_service/app/application/capabilities_service.py:1: "
        "query-control-plane capabilities must remain control-plane owned: disallowed direct "
        "import 'services.query_service.app.settings'"
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
    monkeypatch.setattr("scripts.quality.architecture_boundary_guard.ROOT", repo_root)

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
    monkeypatch.setattr("scripts.quality.architecture_boundary_guard.ROOT", repo_root)

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
    monkeypatch.setattr("scripts.quality.architecture_boundary_guard.ROOT", repo_root)

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
    monkeypatch.setattr("scripts.quality.architecture_boundary_guard.ROOT", repo_root)

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
        / "query_control_plane_service"
        / "app"
        / "application"
        / "advisory_simulation"
        / "valuation.py"
    )
    service_module.parent.mkdir(parents=True)
    service_module.write_text(
        "from src.services.query_control_plane_service.app.contracts.advisory_simulation_models "
        "import "
        "ProposalSimulateRequest\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("scripts.quality.architecture_boundary_guard.ROOT", repo_root)

    assert _scan_for_service_runtime_imports([service_module]) == [
        "src/services/query_control_plane_service/app/application/advisory_simulation/"
        "valuation.py:1: "
        "service runtime packages must not import their own app through repo-root module "
        "path 'services.query_control_plane_service.app.contracts.advisory_simulation_models'; "
        "use package-local "
        "'app...' or relative imports"
    ]


def test_service_runtime_import_guard_allows_package_local_import(tmp_path, monkeypatch) -> None:
    repo_root = tmp_path
    service_module = (
        repo_root
        / "src"
        / "services"
        / "query_control_plane_service"
        / "app"
        / "application"
        / "advisory_simulation"
        / "valuation.py"
    )
    service_module.parent.mkdir(parents=True)
    service_module.write_text(
        "from app.contracts.advisory_simulation_models import ProposalSimulateRequest\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("scripts.quality.architecture_boundary_guard.ROOT", repo_root)

    assert _scan_for_service_runtime_imports([service_module]) == []


def _write_router(tmp_path, monkeypatch, relative_path: str, content: str):
    repo_root = tmp_path
    router = repo_root / relative_path
    router.parent.mkdir(parents=True)
    router.write_text(content, encoding="utf-8")
    monkeypatch.setattr("scripts.quality.architecture_boundary_guard.ROOT", repo_root)
    return router


def _write_exceptions(tmp_path, content: str):
    path = tmp_path / "api-layer-router-boundary-exceptions.json"
    path.write_text(content, encoding="utf-8")
    return path


def test_api_router_boundary_flags_direct_db_session_dependency(tmp_path, monkeypatch) -> None:
    router = _write_router(
        tmp_path,
        monkeypatch,
        "src/services/query_service/app/routers/new_route.py",
        """
from fastapi import Depends
from portfolio_common.db import get_async_db_session
from sqlalchemy.ext.asyncio import AsyncSession

async def route(db: AsyncSession = Depends(get_async_db_session)):
    return {"ok": True}
""",
    )

    violations = _scan_api_router_boundary_violations([router])

    assert {violation.code for violation in violations} == {"router_db_session_dependency"}
    assert any(
        "imports database session dependency" in violation.detail for violation in violations
    )
    assert any(
        "injects AsyncSession/get_async_db_session" in violation.detail for violation in violations
    )


def test_api_router_boundary_flags_repository_construction(tmp_path, monkeypatch) -> None:
    router = _write_router(
        tmp_path,
        monkeypatch,
        "src/services/query_service/app/routers/new_route.py",
        """
from app.repositories.transaction_repository import TransactionRepository

def route(session):
    repository = TransactionRepository(session)
    return repository
""",
    )

    violations = _scan_api_router_boundary_violations([router])

    assert {violation.code for violation in violations} == {"router_repository_dependency"}
    assert any("imports repository" in violation.detail for violation in violations)
    assert any("constructs repository" in violation.detail for violation in violations)


def test_api_router_boundary_flags_external_client_and_file_access(tmp_path, monkeypatch) -> None:
    router = _write_router(
        tmp_path,
        monkeypatch,
        "src/services/query_service/app/routers/new_route.py",
        """
import requests

def route():
    payload = requests.get("https://example.invalid").json()
    with open("local.txt") as handle:
        return handle.read(), payload
""",
    )

    violations = _scan_api_router_boundary_violations([router])

    assert "router_external_client_dependency" in {violation.code for violation in violations}
    assert "router_file_access" in {violation.code for violation in violations}


def test_api_router_boundary_allows_http_delete_decorator(tmp_path, monkeypatch) -> None:
    router = _write_router(
        tmp_path,
        monkeypatch,
        "src/services/query_control_plane_service/app/routers/new_route.py",
        """
from fastapi import APIRouter

router = APIRouter()

@router.delete("/{resource_id}")
async def delete_resource(resource_id: str):
    return {"resource_id": resource_id}
""",
    )

    assert _scan_api_router_boundary_violations([router]) == []


def test_api_router_boundary_still_flags_direct_delete_call(tmp_path, monkeypatch) -> None:
    router = _write_router(
        tmp_path,
        monkeypatch,
        "src/services/query_control_plane_service/app/routers/new_route.py",
        """
async def delete_resource(db, resource):
    await db.delete(resource)
""",
    )

    violations = _scan_api_router_boundary_violations([router])

    assert {violation.code for violation in violations} == {"router_sqlalchemy_operation"}


def test_api_router_boundary_applies_transitional_exception(tmp_path, monkeypatch) -> None:
    router = _write_router(
        tmp_path,
        monkeypatch,
        "src/services/query_service/app/routers/cash_accounts.py",
        """
from portfolio_common.db import get_async_db_session
""",
    )
    exceptions = _write_exceptions(
        tmp_path,
        """
{
  "specVersion": "1.0.0",
  "application": "lotus-core",
  "transitionalExceptions": [
    {
      "path": "src/services/query_service/app/routers/cash_accounts.py",
      "violationCodes": ["router_db_session_dependency"],
      "issue": "#638",
      "rationale": "Existing route dependency awaiting composition-module extraction."
    }
  ]
}
""",
    )

    assert _evaluate_api_router_boundary([router], exceptions) == []


def test_api_router_boundary_rejects_unregistered_violation(tmp_path, monkeypatch) -> None:
    router = _write_router(
        tmp_path,
        monkeypatch,
        "src/services/query_service/app/routers/new_route.py",
        """
from portfolio_common.db import get_async_db_session
""",
    )
    exceptions = _write_exceptions(
        tmp_path,
        """
{
  "specVersion": "1.0.0",
  "application": "lotus-core",
  "transitionalExceptions": []
}
""",
    )

    findings = _evaluate_api_router_boundary([router], exceptions)

    assert len(findings) == 1
    assert "router_db_session_dependency" in findings[0]


def test_api_router_boundary_rejects_stale_exception(tmp_path, monkeypatch) -> None:
    router = _write_router(
        tmp_path,
        monkeypatch,
        "src/services/query_service/app/routers/cash_accounts.py",
        """
from fastapi import APIRouter

router = APIRouter()
""",
    )
    exceptions = _write_exceptions(
        tmp_path,
        """
{
  "specVersion": "1.0.0",
  "application": "lotus-core",
  "transitionalExceptions": [
    {
      "path": "src/services/query_service/app/routers/cash_accounts.py",
      "violationCodes": ["router_db_session_dependency"],
      "issue": "#638",
      "rationale": "Existing route dependency awaiting composition-module extraction."
    }
  ]
}
""",
    )

    findings = _evaluate_api_router_boundary([router], exceptions)

    assert findings == [
        "src/services/query_service/app/routers/cash_accounts.py: api-layer router boundary "
        "exception for router_db_session_dependency (#638) is stale"
    ]


def test_api_router_boundary_violation_format() -> None:
    violation = ApiRouterBoundaryViolation(
        path="src/services/query_service/app/routers/example.py",
        line_no=3,
        code="router_file_access",
        detail="router calls file access operation 'open' directly",
    )

    assert violation.format() == (
        "src/services/query_service/app/routers/example.py:3: router_file_access: "
        "router calls file access operation 'open' directly"
    )
