from __future__ import annotations

from tests.test_support.runtime_modes import classify_runtime_mode, detect_runtime_modes


def test_classify_runtime_mode_identifies_live_worker_paths() -> None:
    assert (
        classify_runtime_mode("tests/e2e/test_timeseries_pipeline.py::test_case")
        == "live_worker"
    )


def test_classify_runtime_mode_identifies_db_direct_paths() -> None:
    assert (
        classify_runtime_mode("tests/integration/services/query_service/test_main_app.py::test_case")
        == "db_direct"
    )
    assert (
        classify_runtime_mode("tests/unit/test_case.py::test_db", {"integration_db"})
        == "db_direct"
    )


def test_detect_runtime_modes_groups_nodeids_by_mode() -> None:
    runtime_modes = detect_runtime_modes(
        [
            ("tests/e2e/test_timeseries_pipeline.py::test_case", []),
            ("tests/integration/services/query_service/test_main_app.py::test_case", []),
            ("tests/unit/test_case.py::test_db", ["integration_db"]),
            ("tests/unit/test_case.py::test_unit", []),
        ]
    )

    assert runtime_modes == {
        "live_worker": ["tests/e2e/test_timeseries_pipeline.py::test_case"],
        "db_direct": [
            "tests/integration/services/query_service/test_main_app.py::test_case",
            "tests/unit/test_case.py::test_db",
        ],
    }
