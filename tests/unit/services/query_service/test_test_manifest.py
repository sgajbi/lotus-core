from __future__ import annotations

from pathlib import Path

from scripts.test_manifest import SUITE_PYTEST_ARGS, SUITES, get_suite, validate_suite_paths


def test_integration_lite_suite_includes_lookup_contract_router() -> None:
    integration_suite = get_suite("integration-lite")
    assert (
        "tests/integration/services/query_service/test_lookup_contract_router.py"
        in integration_suite
    )


def test_unit_suite_excludes_integration_db_marker() -> None:
    assert SUITE_PYTEST_ARGS["unit"] == ["-m", "not integration_db"]


def test_unit_db_suite_tracks_db_dependent_tests() -> None:
    unit_db_suite = get_suite("unit-db")
    assert "tests/unit/libs/portfolio-common/test_position_state_repository.py" in unit_db_suite
    assert (
        "tests/unit/services/calculators/position_valuation_calculator/repositories/test_unit_valuation_repo.py"
        in unit_db_suite
    )


def test_sell_rfc_suite_includes_sell_query_contract_tests() -> None:
    sell_suite = get_suite("sell-rfc")
    assert "tests/integration/services/query_service/test_sell_state_router.py" in sell_suite


def test_manifest_paths_exist_for_all_suites() -> None:
    for suite_name in SUITES:
        validate_suite_paths(suite_name)
        for path in get_suite(suite_name):
            assert Path(path).exists()
