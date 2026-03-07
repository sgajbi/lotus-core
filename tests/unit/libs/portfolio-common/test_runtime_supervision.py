import asyncio
import logging

import pytest
from portfolio_common.runtime_supervision import wait_for_shutdown_or_task_failure

pytestmark = pytest.mark.asyncio


async def test_returns_none_on_explicit_shutdown():
    shutdown_event = asyncio.Event()
    shutdown_event.set()
    logger = logging.getLogger("test-runtime-supervision")

    result = await wait_for_shutdown_or_task_failure(
        tasks=[],
        shutdown_event=shutdown_event,
        logger=logger,
    )

    assert result is None


async def test_returns_runtime_error_when_task_fails():
    shutdown_event = asyncio.Event()
    logger = logging.getLogger("test-runtime-supervision")

    async def _failing():
        raise ValueError("boom")

    failing_task = asyncio.create_task(_failing(), name="failing-task")
    result = await wait_for_shutdown_or_task_failure(
        tasks=[failing_task],
        shutdown_event=shutdown_event,
        logger=logger,
    )

    assert isinstance(result, RuntimeError)
    assert "Critical service task 'failing-task' failed." in str(result)
    assert isinstance(result.__cause__, ValueError)
    assert shutdown_event.is_set() is True
