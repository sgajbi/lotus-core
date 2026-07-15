"""Start the supervised portfolio derived-state worker runtime."""

import asyncio
import logging

from portfolio_common.logging_utils import setup_logging
from portfolio_common.worker_runtime import run_instrumented_worker_service

from .runtime import PortfolioDerivedStateRuntime
from .web import app as web_app

setup_logging()
logger = logging.getLogger(__name__)


async def main() -> None:
    await run_instrumented_worker_service(
        service_name="Portfolio Derived State Service",
        logger=logger,
        manager=PortfolioDerivedStateRuntime(),
        web_app=web_app,
    )


if __name__ == "__main__":
    asyncio.run(main())
