"""Tests for signature-preserving shared instrumentation helpers."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from portfolio_common.utils import async_timed


@pytest.mark.asyncio
async def test_async_timed_preserves_result_metadata_and_metric_labels() -> None:
    @async_timed(repository="TypedRepository", method="load_value")
    async def load_value(value: int, *, suffix: str) -> str:
        """Return a typed value."""

        return f"{value}{suffix}"

    histogram = MagicMock()
    with patch("portfolio_common.utils.DB_OPERATION_LATENCY_SECONDS", histogram):
        result = await load_value(7, suffix="-ok")

    assert result == "7-ok"
    assert load_value.__name__ == "load_value"
    assert load_value.__doc__ == "Return a typed value."
    histogram.labels.assert_called_once_with(
        repository="TypedRepository",
        method="load_value",
    )
    histogram.labels.return_value.observe.assert_called_once()
    assert histogram.labels.return_value.observe.call_args.args[0] >= 0


@pytest.mark.asyncio
async def test_async_timed_observes_failure_latency_and_preserves_exception() -> None:
    expected_error = RuntimeError("database unavailable")

    @async_timed(repository="TypedRepository", method="fail")
    async def fail() -> None:
        raise expected_error

    histogram = MagicMock()
    with (
        patch("portfolio_common.utils.DB_OPERATION_LATENCY_SECONDS", histogram),
        pytest.raises(RuntimeError) as raised,
    ):
        await fail()

    assert raised.value is expected_error
    histogram.labels.assert_called_once_with(repository="TypedRepository", method="fail")
    histogram.labels.return_value.observe.assert_called_once()
