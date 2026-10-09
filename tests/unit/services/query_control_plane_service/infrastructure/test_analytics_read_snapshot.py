from unittest.mock import AsyncMock

import pytest

from src.services.query_control_plane_service.app.infrastructure import analytics_read_snapshot


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [None, "acquisition", "consumer"])
async def test_read_snapshot_owns_session_on_success_and_failure(monkeypatch, failure):
    events = []
    session = AsyncMock()

    async def execute(statement):
        events.append(str(statement))
        if failure == "acquisition":
            raise RuntimeError("snapshot setup failed")

    session.execute.side_effect = execute

    class OwnedSession:
        async def __aenter__(self):
            events.append("open")
            return session

        async def __aexit__(self, *_):
            events.append("close")

    monkeypatch.setattr(
        analytics_read_snapshot.database_provider, "AsyncSessionLocal", OwnedSession
    )
    dependency = analytics_read_snapshot.get_analytics_read_session()
    if failure == "acquisition":
        with pytest.raises(RuntimeError, match="snapshot setup"):
            await anext(dependency)
    else:
        assert await anext(dependency) is session
        assert events == ["open", "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"]
        if failure == "consumer":
            with pytest.raises(RuntimeError, match="consumer failed"):
                await dependency.athrow(RuntimeError("consumer failed"))
        else:
            await dependency.aclose()
    assert events == ["open", "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY", "close"]
