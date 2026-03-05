# tests/unit/libs/portfolio-common/test_reprocessing.py
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from portfolio_common.database_models import PositionState
from portfolio_common.position_state_repository import PositionStateRepository

# The module and class we are about to create
from portfolio_common.reprocessing import EpochFencer, FencedEvent
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_dependencies():
    """Mocks all dependencies for the EpochFencer tests."""
    mock_state_repo = AsyncMock(spec=PositionStateRepository)

    mock_db_session = AsyncMock(spec=AsyncSession)

    with patch(
        "portfolio_common.reprocessing.PositionStateRepository", return_value=mock_state_repo
    ):
        yield {
            "db_session": mock_db_session,
            "state_repo": mock_state_repo,
        }


@pytest.fixture
def sample_event() -> FencedEvent:
    """Provides a sample event object that conforms to the FencedEvent protocol."""
    event = MagicMock()
    event.portfolio_id = "P1"
    event.security_id = "S1"
    event.epoch = 1
    return event


async def test_fencer_returns_true_for_current_epoch(mock_dependencies, sample_event):
    """
    GIVEN an event with an epoch matching the current state
    WHEN the fencer checks the event
    THEN it should return True.
    """
    # ARRANGE
    mock_state_repo = mock_dependencies["state_repo"]
    mock_state_repo.get_or_create_state.return_value = PositionState(epoch=1)

    fencer = EpochFencer(mock_dependencies["db_session"])

    # ACT
    is_valid = await fencer.check(sample_event)

    # ASSERT
    assert is_valid is True
    mock_state_repo.get_or_create_state.assert_awaited_once_with("P1", "S1")


async def test_fencer_returns_false_and_logs_for_stale_epoch(
    mock_dependencies, sample_event, caplog
):
    """
    GIVEN an event with an epoch older than the current state
    WHEN the fencer checks the event
    THEN it should return False and log a warning.
    """
    # ARRANGE
    mock_state_repo = mock_dependencies["state_repo"]
    mock_state_repo.get_or_create_state.return_value = PositionState(
        epoch=2
    )  # Current epoch is newer

    fencer = EpochFencer(mock_dependencies["db_session"])

    # ACT
    # Patch the Prometheus metric to avoid global state issues in tests
    with patch("portfolio_common.reprocessing.EPOCH_MISMATCH_DROPPED_TOTAL") as mock_metric:
        is_valid = await fencer.check(sample_event)

    # ASSERT
    assert is_valid is False
    mock_metric.labels.assert_called_once_with(
        service_name="<not-set>",  # Default, can be overridden
        portfolio_id="P1",
        security_id="S1",
    )
    mock_metric.labels.return_value.inc.assert_called_once()
    assert "Message has stale epoch. Discarding." in caplog.text


async def test_fencer_can_be_configured_with_service_name(mock_dependencies, sample_event, caplog):
    """
    GIVEN an EpochFencer initialized with a service name
    WHEN it drops a stale event
    THEN the metric should be labeled with the correct service name.
    """
    # ARRANGE
    mock_state_repo = mock_dependencies["state_repo"]
    mock_state_repo.get_or_create_state.return_value = PositionState(epoch=2)

    fencer = EpochFencer(mock_dependencies["db_session"], service_name="TestService")

    # ACT
    with patch("portfolio_common.reprocessing.EPOCH_MISMATCH_DROPPED_TOTAL") as mock_metric:
        is_valid = await fencer.check(sample_event)

    # ASSERT
    assert is_valid is False
    mock_metric.labels.assert_called_once_with(
        service_name="TestService", portfolio_id="P1", security_id="S1"
    )
