from importlib.metadata import PackageNotFoundError
from pathlib import Path

import pytest

from scripts.development import bootstrap_dev


class _Distribution:
    def __init__(self, direct_url: str | None) -> None:
        self._direct_url = direct_url

    def read_text(self, filename: str) -> str | None:
        assert filename == "direct_url.json"
        return self._direct_url


def _resolver(direct_url: str | None):
    return lambda _name: _Distribution(direct_url)


def test_editable_origin_accepts_invoking_worktree(tmp_path: Path) -> None:
    project = tmp_path / "lotus-core-current" / "src" / "libs" / "portfolio-common"
    project.mkdir(parents=True)
    direct_url = '{"dir_info":{"editable":true},"url":"' + project.resolve().as_uri() + '"}'

    assert (
        bootstrap_dev.require_portfolio_common_editable_origin(
            expected_project=project,
            distribution_resolver=_resolver(direct_url),
        )
        == project.resolve()
    )


def test_editable_origin_rejects_another_worktree(tmp_path: Path) -> None:
    expected = tmp_path / "lotus-core-current" / "src" / "libs" / "portfolio-common"
    foreign = tmp_path / "lotus-core-other" / "src" / "libs" / "portfolio-common"
    expected.mkdir(parents=True)
    foreign.mkdir(parents=True)
    direct_url = '{"dir_info":{"editable":true},"url":"' + foreign.resolve().as_uri() + '"}'

    with pytest.raises(RuntimeError) as raised:
        bootstrap_dev.require_portfolio_common_editable_origin(
            expected_project=expected,
            distribution_resolver=_resolver(direct_url),
        )

    message = str(raised.value)
    assert str(expected.resolve()) in message
    assert str(foreign.resolve()) in message
    assert "make install" in message


@pytest.mark.parametrize(
    "direct_url",
    [
        None,
        '{"dir_info":{"editable":false},"url":"file:///tmp/package"}',
        '{"dir_info":{"editable":true},"url":"https://example.com/package"}',
    ],
)
def test_editable_origin_rejects_missing_or_untrusted_provenance(
    tmp_path: Path,
    direct_url: str | None,
) -> None:
    with pytest.raises(RuntimeError):
        bootstrap_dev.require_portfolio_common_editable_origin(
            expected_project=tmp_path,
            distribution_resolver=_resolver(direct_url),
        )


def test_editable_origin_reports_missing_distribution(tmp_path: Path) -> None:
    def _missing(_name: str):
        raise PackageNotFoundError("portfolio-common")

    with pytest.raises(RuntimeError, match="not installed"):
        bootstrap_dev.require_portfolio_common_editable_origin(
            expected_project=tmp_path,
            distribution_resolver=_missing,
        )
