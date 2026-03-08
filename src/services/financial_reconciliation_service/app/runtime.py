import asyncio
import logging

from portfolio_common.logging_utils import setup_logging

from .consumer_manager import ConsumerManager

setup_logging()
logger = logging.getLogger(__name__)


async def main():
    logger.info("Financial Reconciliation Service starting up...")

    manager = ConsumerManager()
    try:
        await manager.run()
    except Exception:
        logger.critical(
            "Financial Reconciliation Service encountered a critical error",
            exc_info=True,
        )
        raise
    finally:
        logger.info("Financial Reconciliation Service has shut down.")


if __name__ == "__main__":
    asyncio.run(main())
