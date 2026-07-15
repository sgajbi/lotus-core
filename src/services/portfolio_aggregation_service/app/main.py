import asyncio
import logging

from portfolio_common.logging_utils import setup_logging
from portfolio_common.worker_runtime import run_instrumented_worker_service

from .runtime import PortfolioAggregationRuntime
from .web import app as web_app

setup_logging()
logger = logging.getLogger(__name__)


async def main():
    await run_instrumented_worker_service(
        service_name="Portfolio Aggregation Service",
        logger=logger,
        manager=PortfolioAggregationRuntime(),
        web_app=web_app,
    )


if __name__ == "__main__":
    asyncio.run(main())
