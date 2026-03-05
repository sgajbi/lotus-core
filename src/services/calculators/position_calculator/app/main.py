# services/calculators/position_calculator/app/main.py
import asyncio
import logging

from app.consumer_manager import ConsumerManager
from portfolio_common.logging_utils import setup_logging
from prometheus_fastapi_instrumentator import Instrumentator

from .web import app as web_app

setup_logging()
logger = logging.getLogger(__name__)


async def main():
    """
    Initializes and runs the ConsumerManager.
    """
    logger.info("Position Calculation Service starting up...")
    
    # Instrument the web app before starting the server
    Instrumentator().instrument(web_app).expose(web_app)
    logger.info("Prometheus metrics exposed at /metrics")

    manager = ConsumerManager()
    try:
        await manager.run()
    except Exception as e:
        logger.critical(f"Position Calculation Service encountered a critical error: {e}", exc_info=True)
    finally:
        logger.info("Position Calculation Service has shut down.")

if __name__ == "__main__":
    asyncio.run(main())
