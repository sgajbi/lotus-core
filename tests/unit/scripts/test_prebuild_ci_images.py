import json
from argparse import Namespace
from pathlib import Path

from scripts.release.prebuild_ci_images import (
    main,
    provenance_build_args,
    resolve_build_metadata,
)


def test_prebuild_group_expands_to_named_services(
    monkeypatch,
    tmp_path: Path,
) -> None:
    built: list[tuple[str, Path]] = []
    tagged: list[tuple[str, str]] = []

    monkeypatch.setattr(
        "scripts.release.prebuild_ci_images.parse_args",
        lambda: Namespace(
            cache_dir=str(tmp_path / ".buildx-cache"),
            services=None,
            group="performance-gate",
            metrics_output=None,
        ),
    )
    monkeypatch.setattr(
        "scripts.release.prebuild_ci_images._build",
        lambda service, cache_dir: (
            built.append((service, cache_dir))
            or {"service": service, "image_tag": service, "duration_seconds": 0.0}
        ),
    )
    monkeypatch.setattr(
        "scripts.release.prebuild_ci_images._tag_existing_image",
        lambda source_service, target_service: (
            tagged.append((source_service, target_service))
            or {"service": target_service, "image_tag": target_service, "duration_seconds": 0.0}
        ),
    )

    assert main() == 0
    assert [service for service, _ in built] == [
        "kafka-topic-creator",
        "ingestion_service",
        "query_service",
        "event_replay_service",
        "portfolio_transaction_processing_service",
    ]
    assert tagged == [
        ("kafka-topic-creator", "migration-runner"),
        ("kafka-topic-creator", "persistence_service"),
    ]


def test_prebuild_services_and_group_are_deduplicated(
    monkeypatch,
    tmp_path: Path,
) -> None:
    built: list[str] = []

    monkeypatch.setattr(
        "scripts.release.prebuild_ci_images.parse_args",
        lambda: Namespace(
            cache_dir=str(tmp_path / ".buildx-cache"),
            services=["query_service"],
            group="query-only",
            metrics_output=None,
        ),
    )
    monkeypatch.setattr(
        "scripts.release.prebuild_ci_images._build",
        lambda service, cache_dir: (
            built.append(service)
            or {"service": service, "image_tag": service, "duration_seconds": 0.0}
        ),
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


def test_ci_image_version_prefers_exact_commit_over_ref_name(monkeypatch) -> None:
    source_sha = "a" * 40
    monkeypatch.delenv("LOTUS_IMAGE_VERSION", raising=False)
    monkeypatch.setenv("GITHUB_SHA", source_sha)
    monkeypatch.setenv("GITHUB_REF_NAME", "123/merge")
    monkeypatch.setenv("GITHUB_HEAD_REF", "feat/runtime-image-set")
    monkeypatch.setenv("GITHUB_REPOSITORY", "sgajbi/lotus-core")
    monkeypatch.setenv("GITHUB_RUN_ID", "12345")

    metadata = resolve_build_metadata()

    assert metadata["LOTUS_IMAGE_VERSION"] == source_sha
    assert metadata["LOTUS_GIT_COMMIT_SHA"] == source_sha
    assert metadata["LOTUS_GIT_BRANCH"] == "feat/runtime-image-set"


def test_prebuild_writes_machine_readable_timing_evidence(
    monkeypatch,
    tmp_path: Path,
) -> None:
    metrics_path = tmp_path / "runtime-image-build-metrics.json"
    monkeypatch.setattr(
        "scripts.release.prebuild_ci_images.parse_args",
        lambda: Namespace(
            cache_dir=str(tmp_path / ".buildx-cache"),
            services=["query_service"],
            group=None,
            metrics_output=metrics_path,
        ),
    )
    monkeypatch.setattr(
        "scripts.release.prebuild_ci_images._build",
        lambda service, cache_dir: {
            "service": service,
            "image_tag": "lotus-core/query-service:local",
            "build_mode": "built",
            "duration_seconds": 1.25,
        },
    )

    assert main() == 0

    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    assert metrics["schema_version"] == "lotus-core.runtime-image-build-metrics.v1"
    assert metrics["service_count"] == 1
    assert metrics["total_build_seconds"] == 1.25
    assert metrics["services"] == [
        {
            "service": "query_service",
            "image_tag": "lotus-core/query-service:local",
            "build_mode": "built",
            "duration_seconds": 1.25,
        }
    ]
