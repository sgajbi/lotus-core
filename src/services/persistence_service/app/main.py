# services/persistence_service/app/main.py
import asyncio
import logging

from portfolio_common.logging_utils import setup_logging

from .consumer_manager import ConsumerManager

setup_logging()
logger = logging.getLogger(__name__)


async def main():
    """
    Initializes and runs the ConsumerManager.
    """
    logger.info("Persistence Service starting up...")
    manager = ConsumerManager()

    try:
        await manager.run()
    except Exception:
        logger.critical("Persistence Service encountered a critical error", exc_info=True)
        raise
    finally:
        logger.info("Persistence Service has shut down.")


if __name__ == "__main__":
    # local import to avoid unused in module context
    asyncio.run(main())
