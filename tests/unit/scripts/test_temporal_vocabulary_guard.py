from pathlib import Path

from scripts import temporal_vocabulary_guard as guard


def _occurrence(relative_path: str, field: str) -> guard.FieldOccurrence:
    return guard.FieldOccurrence(
        path=guard.REPO_ROOT / relative_path,
        line_number=10,
        field=field,
        line=f"{field}: date",
    )


def test_evaluate_occurrences_rejects_unallowlisted_temporal_field() -> None:
    errors = guard._evaluate_occurrences(
        [_occurrence("src/services/query_service/app/dtos/example.py", "date")],
        allowlist={},
    )

    assert len(errors) == 1
    assert "forbidden temporal field 'date'" in errors[0]


def test_evaluate_occurrences_requires_exact_allowlist_count() -> None:
    allowlist = {("src/services/query_service/app/dtos/example.py", "source_timestamp"): 2}

    errors = guard._evaluate_occurrences(
        [_occurrence("src/services/query_service/app/dtos/example.py", "source_timestamp")],
        allowlist=allowlist,
    )

    assert len(errors) == 1
    assert "occurs 1 times; allowlist expects 2" in errors[0]


def test_evaluate_occurrences_accepts_exact_allowlist_count() -> None:
    allowlist = {("src/services/query_service/app/dtos/example.py", "date"): 1}

    errors = guard._evaluate_occurrences(
        [_occurrence("src/services/query_service/app/dtos/example.py", "date")],
        allowlist=allowlist,
    )

    assert errors == []


def test_router_directories_are_in_guard_scan_scope() -> None:
    scanned_paths = {Path(path).as_posix() for path in guard.SCANNED_PATHS}

    assert any(path.endswith("query_service/app/routers") for path in scanned_paths)
    assert any(path.endswith("query_control_plane_service/app/routers") for path in scanned_paths)
    assert any(path.endswith("ingestion_service/app/routers") for path in scanned_paths)
