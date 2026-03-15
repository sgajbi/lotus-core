from argparse import Namespace
from pathlib import Path

from scripts.prebuild_ci_images import main


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
