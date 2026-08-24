"""Tests for exact-current-source runtime image-set verification orchestration."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import Mock

import pytest

from scripts.release.runtime_image_set import RuntimeImageSetError
from scripts.release.verify_runtime_image_set import verify_runtime_image_set_for_current_source

SOURCE_SHA = "a" * 40


def test_local_verification_without_an_image_set_removes_a_stale_receipt(tmp_path: Path) -> None:
    runtime_directory = tmp_path / "output" / "runtime-image-set"
    runtime_directory.mkdir(parents=True)
    receipt_path = runtime_directory / "verified-source-sha"
    receipt_path.write_text("stale\n", encoding="utf-8")
    verifier = Mock()
    messages: list[str] = []

    verified = verify_runtime_image_set_for_current_source(
        environment={},
        workspace=tmp_path,
        verifier=verifier,
        output=messages.append,
    )

    assert verified is False
    assert not receipt_path.exists()
    assert messages == ["No runtime image set present; controls build from source."]
    verifier.assert_not_called()


def test_explicit_false_ci_without_an_image_set_builds_from_source(tmp_path: Path) -> None:
    assert (
        verify_runtime_image_set_for_current_source(
            environment={"CI": "false"},
            workspace=tmp_path,
            output=lambda _message: None,
        )
        is False
    )


def test_ci_verification_requires_the_exact_github_sha(tmp_path: Path) -> None:
    with pytest.raises(RuntimeImageSetError, match="GITHUB_SHA is required in CI"):
        verify_runtime_image_set_for_current_source(
            environment={"CI": "true"},
            workspace=tmp_path,
        )


def test_ci_verification_writes_receipt_only_after_exact_source_verification(
    tmp_path: Path,
) -> None:
    runtime_directory = tmp_path / "output" / "runtime-image-set"
    runtime_directory.mkdir(parents=True)
    (runtime_directory / "manifest.json").write_text("{}\n", encoding="utf-8")
    verifier = Mock(return_value={})
    runner = Mock()

    verified = verify_runtime_image_set_for_current_source(
        environment={"CI": "true", "GITHUB_SHA": SOURCE_SHA},
        workspace=tmp_path,
        runner=runner,
        verifier=verifier,
    )

    assert verified is True
    verifier.assert_called_once_with(
        manifest_path=runtime_directory / "manifest.json",
        bundle_path=runtime_directory / "images.tar",
        expected_commit_sha=SOURCE_SHA,
        runner=runner,
    )
    assert (runtime_directory / "verified-source-sha").read_text(encoding="utf-8") == (
        f"{SOURCE_SHA}\n"
    )


def test_local_verification_resolves_the_current_git_head(tmp_path: Path) -> None:
    runtime_directory = tmp_path / "output" / "runtime-image-set"
    runtime_directory.mkdir(parents=True)
    (runtime_directory / "manifest.json").write_text("{}\n", encoding="utf-8")
    verifier = Mock(return_value={})

    def runner(*args, **kwargs):  # noqa: ANN002, ANN003
        assert args[0] == ["git", "rev-parse", "HEAD"]
        assert kwargs["cwd"] == tmp_path
        return subprocess.CompletedProcess(args[0], 0, stdout=f"{SOURCE_SHA}\n")

    assert verify_runtime_image_set_for_current_source(
        environment={},
        workspace=tmp_path,
        runner=runner,
        verifier=verifier,
    )
    assert verifier.call_args.kwargs["expected_commit_sha"] == SOURCE_SHA


def test_failed_verification_does_not_publish_a_receipt(tmp_path: Path) -> None:
    runtime_directory = tmp_path / "output" / "runtime-image-set"
    runtime_directory.mkdir(parents=True)
    (runtime_directory / "manifest.json").write_text("{}\n", encoding="utf-8")
    verifier = Mock(side_effect=RuntimeImageSetError("tampered bundle"))

    with pytest.raises(RuntimeImageSetError, match="tampered bundle"):
        verify_runtime_image_set_for_current_source(
            environment={"CI": "true", "GITHUB_SHA": SOURCE_SHA},
            workspace=tmp_path,
            verifier=verifier,
        )

    assert not (runtime_directory / "verified-source-sha").exists()
