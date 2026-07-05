from scripts.generated_artifact_tracking_guard import (
    find_forbidden_tracked_artifacts,
    is_forbidden_tracked_artifact,
)


def test_generated_artifact_tracking_guard_flags_build_outputs() -> None:
    assert is_forbidden_tracked_artifact("src/services/query_service/build/lib/app/main.py")
    assert is_forbidden_tracked_artifact("src/services/query_service/app/__pycache__/main.pyc")
    assert is_forbidden_tracked_artifact("output/documentation-evidence/evidence.json")


def test_generated_artifact_tracking_guard_allows_authored_source_and_docs() -> None:
    assert not is_forbidden_tracked_artifact("src/services/query_service/app/main.py")
    assert not is_forbidden_tracked_artifact("scripts/clean_generated_artifacts.py")
    assert not is_forbidden_tracked_artifact(
        "docs/architecture/CR-1272-CLEAN-GENERATED-ARTIFACTS-POLICY.md"
    )


def test_find_forbidden_tracked_artifacts_normalizes_paths() -> None:
    findings = find_forbidden_tracked_artifacts(
        [
            "src\\services\\query_service\\build\\lib\\app\\settings.py",
            "src/services/query_service/app/settings.py",
            "dist/package.whl",
        ]
    )

    assert findings == [
        "dist/package.whl",
        "src/services/query_service/build/lib/app/settings.py",
    ]
