"""Verify governed test-suite composition and runtime-mode contracts."""

from __future__ import annotations

from pathlib import Path

from scripts.quality.test_manifest import (
    SUITE_ENV_PROFILE,
    SUITE_PYTEST_ARGS,
    SUITE_RUNTIME_MODE,
    SUITES,
    get_suite,
    suite_pytest_command,
    validate_suite_paths,
)


def test_integration_lite_suite_includes_lookup_contract_router() -> None:
    integration_suite = get_suite("integration-lite")
    assert (
        "tests/integration/services/query_service/test_lookup_contract_router.py"
        in integration_suite
    )


def test_unit_suite_excludes_integration_db_marker() -> None:
    assert SUITE_PYTEST_ARGS["unit"] == [
        "-m",
        "not integration_db and not db_direct and not live_worker and not e2e",
    ]


def test_unit_db_suite_tracks_db_dependent_tests() -> None:
    unit_db_suite = get_suite("unit-db")
    assert "tests/unit/libs/portfolio-common/test_position_state_repository.py" in unit_db_suite
    assert (
        "tests/unit/services/calculators/position_valuation_calculator/repositories/test_unit_valuation_repo.py"
        in unit_db_suite
    )


def test_critical_db_coverage_includes_changed_outbox_delivery_hot_path() -> None:
    assert "tests/integration/libs/portfolio-common/test_outbox_dispatcher.py" in get_suite(
        "critical-db-coverage"
    )


def test_critical_lifecycle_suite_is_marker_selected_and_db_direct() -> None:
    assert get_suite("critical-lifecycle-db") == ["tests/integration"]
    assert SUITE_PYTEST_ARGS["critical-lifecycle-db"] == ["-m", "lifecycle"]
    assert SUITE_ENV_PROFILE["critical-lifecycle-db"] == "integration"
    assert SUITE_RUNTIME_MODE["critical-lifecycle-db"] == "db_direct"


def test_critical_lifecycle_suite_has_repository_native_make_target() -> None:
    assert "test-critical-lifecycle-db:" in Path("Makefile").read_text(encoding="utf-8")


def test_integration_all_suite_tracks_full_integration_tree() -> None:
    assert get_suite("integration-all") == ["tests/integration"]


def test_transaction_processing_contract_tracks_complete_combined_integration_pack() -> None:
    assert get_suite("transaction-processing-contract") == [
        "tests/integration/services/portfolio_transaction_processing_service"
    ]


def test_sell_contract_suite_includes_sell_query_contract_tests() -> None:
    sell_suite = get_suite("transaction-sell-contract")
    assert "tests/integration/services/query_service/test_sell_state_router.py" in sell_suite


def test_dividend_contract_suite_includes_independent_settlement_oracle() -> None:
    assert "tests/unit/transaction_specs/test_dividend_settlement_golden_vectors.py" in get_suite(
        "transaction-dividend-contract"
    )


def test_fx_contract_suite_includes_fx_contract_surfaces() -> None:
    fx_suite = get_suite("transaction-fx-contract")
    assert (
        "tests/unit/services/portfolio_transaction_processing_service/domain/transaction/fx/"
        "test_validation.py"
    ) in fx_suite
    retired_prefix = "tests/unit/services/portfolio_transaction_processing_service/transaction/fx/"
    assert all(not path.startswith(retired_prefix) for path in fx_suite)
    assert "tests/integration/services/query_service/test_transactions_router.py" in fx_suite
    assert (
        "tests/integration/services/persistence_service/repositories/test_repositories.py"
        in fx_suite
    )


def test_e2e_all_suite_tracks_full_end_to_end_tree() -> None:
    assert get_suite("e2e-all") == ["tests/e2e"]


def test_manifest_runtime_modes_keep_db_direct_and_live_worker_explicit() -> None:
    assert SUITE_RUNTIME_MODE["integration-all"] == "db_direct"
    assert SUITE_RUNTIME_MODE["transaction-processing-contract"] == "db_direct"
    assert SUITE_RUNTIME_MODE["e2e-all"] == "live_worker"


def test_manifest_paths_exist_for_all_suites() -> None:
    for suite_name in SUITES:
        validate_suite_paths(suite_name)
        for path in get_suite(suite_name):
            assert Path(path).exists()


def test_manifest_collection_command_uses_suite_definition() -> None:
    command = suite_pytest_command("integration-lite", collect_only=True, quiet=True)

    assert "--collect-only" in command
    assert "-q" in command
    assert "tests/integration/services/query_service/test_main_app.py" in command


def test_manifest_coverage_command_accepts_multiple_source_targets() -> None:
    command = suite_pytest_command(
        "integration-lite",
        with_coverage=True,
        coverage_sources=(
            "src.services.query_service.app",
            "src.services.portfolio_transaction_processing_service.app.domain.cost_basis",
            "src.services.query_service.app",
        ),
    )

    assert command[-3:] == [
        "--cov=src.services.query_service.app",
        "--cov=src.services.portfolio_transaction_processing_service.app.domain.cost_basis",
        "--cov-report=",
    ]
