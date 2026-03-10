# src/libs/portfolio-common/portfolio_common/reprocessing.py
import logging
from typing import Optional, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from .monitoring import EPOCH_MISMATCH_DROPPED_TOTAL
from .position_state_repository import PositionStateRepository

logger = logging.getLogger(__name__)


class FencedEvent(Protocol):
    """A protocol defining the required attributes for an event to be checked by the fencer."""

    portfolio_id: str
    security_id: str
    epoch: Optional[int]
    topic: Optional[str]


class EpochFencer:
    """
    A reusable utility to perform epoch fencing for consumers. It ensures that
    stale messages from a previous, now-obsolete history are safely ignored.
    """

    def __init__(self, db: AsyncSession, service_name: str = "<not-set>"):
        self.db = db
        self.state_repo = PositionStateRepository(db)
        self.service_name = service_name

    async def check(self, event: FencedEvent) -> bool:
        """
        Checks if the event's epoch is current.

        Args:
            event: An object conforming to the FencedEvent protocol.

        Returns:
            False if the event is stale and should be discarded, True otherwise.
        """
        current_state = await self.state_repo.get_or_create_state(
            event.portfolio_id, event.security_id
        )

        message_epoch = event.epoch if event.epoch is not None else current_state.epoch

        if message_epoch < current_state.epoch:
            EPOCH_MISMATCH_DROPPED_TOTAL.labels(
                service_name=self.service_name,
                topic=getattr(event, "topic", "<unknown>") or "<unknown>",
                portfolio_id=event.portfolio_id,
                security_id=event.security_id,
            ).inc()
            logger.warning(
                "Message has stale epoch. Discarding.",
                extra={
                    "portfolio_id": event.portfolio_id,
                    "security_id": event.security_id,
                    "message_epoch": message_epoch,
                    "current_epoch": current_state.epoch,
                },
            )
            return False

        return True
