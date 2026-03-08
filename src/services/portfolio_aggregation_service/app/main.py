import asyncio
import logging

from portfolio_common.logging_utils import setup_logging
from prometheus_fastapi_instrumentator import Instrumentator

from .consumer_manager import ConsumerManager
from .web import app as web_app

setup_logging()
logger = logging.getLogger(__name__)


async def main():
    logger.info("Portfolio Aggregation Service starting up...")
    Instrumentator().instrument(web_app).expose(web_app)
    logger.info("Prometheus metrics exposed at /metrics")

    manager = ConsumerManager()
    try:
        await manager.run()
    except Exception:
        logger.critical("Portfolio Aggregation Service encountered a critical error", exc_info=True)
        raise
    finally:
        logger.info("Portfolio Aggregation Service has shut down.")


if __name__ == "__main__":
    asyncio.run(main())
