from __future__ import annotations

import pytest

from tests.test_support.runtime_modes import classify_runtime_mode, detect_runtime_modes


@pytest.mark.parametrize(
    ("nodeid", "markers", "expected"),
    [
        ("tests/unit/test_case.py::test_guard[tests/integration/fixture.py]", (), None),
        ("tests/unit/test_case.py::test_guard[tests/e2e/fixture.py]", (), None),
        (
            "tests/integration/test_case.py::test_guard[tests/unit/fixture.py]",
            (),
            "db_direct",
        ),
        ("tests/e2e/test_case.py::test_guard[tests/unit/fixture.py]", (), "live_worker"),
        (
            "tests/unit/test_case.py::test_guard[tests/e2e/fixture.py]",
            ("integration_db",),
            "db_direct",
        ),
        (r"tests\unit\test_case.py::test_guard[tests\integration\fixture.py]", (), None),
        (
            r"C:\repo\tests\integration\test_case.py::test_guard[tests/e2e/fixture.py]",
            (),
            "db_direct",
        ),
        (
            "/repo/tests/e2e/test_case.py::test_guard[tests/integration/fixture.py]",
            (),
            "live_worker",
        ),
    ],
    ids=[
        "unit-integration-parameter",
        "unit-e2e-parameter",
        "integration-file",
        "e2e-file",
        "explicit-database-marker",
        "windows-unit-parameter",
        "windows-integration-file",
        "absolute-e2e-file",
    ],
)
def test_runtime_mode_uses_test_file_not_parameter_content(
    nodeid: str, markers: tuple[str, ...], expected: str | None
) -> None:
    assert classify_runtime_mode(nodeid, markers) == expected


def test_classify_runtime_mode_identifies_live_worker_paths() -> None:
    assert (
        classify_runtime_mode("tests/e2e/test_timeseries_pipeline.py::test_case") == "live_worker"
    )


def test_classify_runtime_mode_identifies_db_direct_paths() -> None:
    assert (
        classify_runtime_mode(
            "tests/integration/services/query_service/test_main_app.py::test_case"
        )
        == "db_direct"
    )
    assert (
        classify_runtime_mode("tests/unit/test_case.py::test_db", {"integration_db"}) == "db_direct"
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
