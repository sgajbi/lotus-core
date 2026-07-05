from argparse import Namespace
from pathlib import Path

from scripts.prebuild_ci_images import main
from scripts.prebuild_ci_images import provenance_build_args


def test_prebuild_group_expands_to_named_services(
    monkeypatch,
    tmp_path: Path,
) -> None:
    built: list[tuple[str, Path]] = []

    monkeypatch.setattr(
        "scripts.prebuild_ci_images.parse_args",
        lambda: Namespace(
            cache_dir=str(tmp_path / ".buildx-cache"),
            services=None,
            group="performance-gate",
        ),
    )
    monkeypatch.setattr(
        "scripts.prebuild_ci_images._build",
        lambda service, cache_dir: built.append((service, cache_dir)),
    )

    assert main() == 0
    assert [service for service, _ in built] == [
        "kafka-topic-creator",
        "migration-runner",
        "ingestion_service",
        "query_service",
        "event_replay_service",
        "persistence_service",
        "position_calculator_service",
        "pipeline_orchestrator_service",
    ]


def test_prebuild_services_and_group_are_deduplicated(
    monkeypatch,
    tmp_path: Path,
) -> None:
    built: list[str] = []

    monkeypatch.setattr(
        "scripts.prebuild_ci_images.parse_args",
        lambda: Namespace(
            cache_dir=str(tmp_path / ".buildx-cache"),
            services=["query_service"],
            group="query-only",
        ),
    )
    monkeypatch.setattr(
        "scripts.prebuild_ci_images._build",
        lambda service, cache_dir: built.append(service),
    )

    assert main() == 0
    assert built == ["query_service"]


def test_provenance_build_args_include_required_image_metadata() -> None:
    build_args = provenance_build_args(
        {
            "LOTUS_GIT_COMMIT_SHA": "abc123",
            "LOTUS_GIT_BRANCH": "feature/provenance",
            "LOTUS_BUILD_TIMESTAMP": "2026-07-05T12:34:56Z",
            "LOTUS_REPO_URL": "https://github.com/example/lotus-core",
            "LOTUS_IMAGE_VERSION": "abc123",
            "LOTUS_IMAGE_DIGEST": "sha256:123",
            "LOTUS_CI_RUN_ID": "987654",
        }
    )

    assert build_args == [
        "--build-arg",
        "LOTUS_GIT_COMMIT_SHA=abc123",
        "--build-arg",
        "LOTUS_GIT_BRANCH=feature/provenance",
        "--build-arg",
        "LOTUS_BUILD_TIMESTAMP=2026-07-05T12:34:56Z",
        "--build-arg",
        "LOTUS_REPO_URL=https://github.com/example/lotus-core",
        "--build-arg",
        "LOTUS_IMAGE_VERSION=abc123",
        "--build-arg",
        "LOTUS_IMAGE_DIGEST=sha256:123",
        "--build-arg",
        "LOTUS_CI_RUN_ID=987654",
    ]
