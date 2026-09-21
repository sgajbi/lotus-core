"""Cheap proof for the live retired-route E2E compatibility policy."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from tests.e2e.test_concentration_pipeline import (
    test_concentration_endpoint_is_disabled as assert_concentration_disabled,
)


def test_retired_route_accepts_explicit_410_without_a_get_shim() -> None:
    client = Mock()
    client.post_query.return_value = SimpleNamespace(status_code=410)

    assert_concentration_disabled(client)

    client.query.assert_not_called()


def test_retired_route_rejects_portfolio_404_from_restored_post_route() -> None:
    client = Mock()
    client.post_query.return_value = SimpleNamespace(status_code=404)
    client.query.return_value = SimpleNamespace(status_code=405)

    with pytest.raises(AssertionError):
        assert_concentration_disabled(client)
