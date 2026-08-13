import pytest

from scripts.release.write_slsa_provenance_predicate import (
    SLSA_BUILD_TYPE,
    build_predicate,
)


def _predicate(**overrides):
    values = {
        "repository": "sgajbi/lotus-core",
        "repository_url": "https://github.com/sgajbi/lotus-core",
        "git_commit_sha": "a" * 40,
        "workflow_ref": (
            "https://github.com/sgajbi/lotus-core/.github/workflows/image-release.yml@refs/heads/main"
        ),
        "service": "query_service",
        "dockerfile": "src/services/query_service/Dockerfile",
        "ci_run_id": "123",
        "ci_run_attempt": "1",
        "buildx_metadata": {"containerimage.digest": "sha256:" + "b" * 64},
    }
    values.update(overrides)
    return build_predicate(**values)


def test_predicate_binds_source_workflow_build_and_result() -> None:
    predicate = _predicate()

    assert predicate["buildDefinition"]["buildType"] == SLSA_BUILD_TYPE
    assert predicate["buildDefinition"]["resolvedDependencies"][0]["digest"] == {
        "gitCommit": "a" * 40
    }
    assert predicate["runDetails"]["metadata"]["invocationId"].endswith("/123/attempts/1")
    assert predicate["runDetails"]["byproducts"][0]["content"] == {
        "containerimage.digest": "sha256:" + "b" * 64
    }


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"git_commit_sha": "short"}, "full lowercase SHA"),
        ({"workflow_ref": ""}, "workflow ref is required"),
        ({"ci_run_attempt": "no"}, "must be numeric"),
        ({"buildx_metadata": {}}, "container image digest"),
    ],
)
def test_predicate_rejects_incomplete_identity(overrides, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        _predicate(**overrides)
