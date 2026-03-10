from datetime import UTC, date, datetime
from unittest.mock import MagicMock

import httpx
import pytest
import pytest_asyncio

from src.services.query_control_plane_service.app.main import app
from src.services.query_control_plane_service.app.routers.capabilities import (
    get_capabilities_service,
)
from src.services.query_service.app.services.capabilities_service import CapabilitiesService

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def async_test_client():
    mock_service = MagicMock()
    mock_service.get_integration_capabilities.return_value = {
        "contract_version": "v1",
        "source_service": "lotus-core",
        "consumer_system": "lotus-manage",
        "tenant_id": "tenant-1",
        "generated_at": datetime(2026, 2, 23, tzinfo=UTC),
        "as_of_date": date(2026, 2, 23),
        "policy_version": "tenant-1-v2",
        "supported_input_modes": ["lotus_core_ref", "inline_bundle"],
        "features": [],
        "workflows": [],
    }
    app.dependency_overrides[get_capabilities_service] = lambda: mock_service
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, mock_service
    app.dependency_overrides.pop(get_capabilities_service, None)


async def test_capabilities_success(async_test_client):
    client, mock_service = async_test_client
    response = await client.get(
        "/integration/capabilities?consumer_system=lotus-manage&tenant_id=tenant-1"
    )
    assert response.status_code == 200
    body = response.json()
    assert body["consumer_system"] == "lotus-manage"
    assert body["policy_version"] == "tenant-1-v2"
    mock_service.get_integration_capabilities.assert_called_once_with(
        consumer_system="lotus-manage",
        tenant_id="tenant-1",
    )


async def test_get_capabilities_service_returns_service_instance():
    service = get_capabilities_service()
    assert isinstance(service, CapabilitiesService)
