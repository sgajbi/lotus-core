import asyncio
import logging

from portfolio_common.logging_utils import setup_logging
from prometheus_fastapi_instrumentator import Instrumentator

from .consumer_manager import ConsumerManager
from .web import app as web_app

setup_logging()
logger = logging.getLogger(__name__)


async def main():
    """
    Initializes and runs the ConsumerManager and the OutboxDispatcher side-by-side.
    """
    logger.info("Cashflow Calculation Service starting up...")

    Instrumentator().instrument(web_app).expose(web_app)
    logger.info("Prometheus metrics exposed at /metrics")

    manager = ConsumerManager()

    try:
        await manager.run()
    except Exception as e:
        logger.critical(
            f"Cashflow Calculation Service encountered a critical error: {e}", exc_info=True
        )
        raise
    logger.info("Cashflow Calculation Service has shut down.")


if __name__ == "__main__":
    asyncio.run(main())
