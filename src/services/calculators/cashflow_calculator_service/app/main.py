import asyncio
import logging

from portfolio_common.kafka_utils import get_kafka_producer
from portfolio_common.logging_utils import setup_logging
from portfolio_common.outbox_dispatcher import OutboxDispatcher
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

    producer = get_kafka_producer()
    dispatcher = OutboxDispatcher(producer, poll_interval=2, batch_size=100)
    dispatcher_task = asyncio.create_task(dispatcher.run(), name="outbox-dispatcher")

    try:
        await manager.run()
    except Exception as e:
        logger.critical(f"Cashflow Calculation Service encountered a critical error: {e}", exc_info=True)
        raise
    finally:
        dispatcher.stop()
        try:
            await asyncio.wait_for(dispatcher_task, timeout=5)
        except asyncio.TimeoutError:
            dispatcher_task.cancel()
            with contextlib.suppress(Exception):
                await dispatcher_task
        logger.info("Cashflow Calculation Service has shut down.")


if __name__ == "__main__":
    import contextlib
    asyncio.run(main())