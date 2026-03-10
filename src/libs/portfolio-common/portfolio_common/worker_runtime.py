import logging

from prometheus_fastapi_instrumentator import Instrumentator


async def run_instrumented_worker_service(
    *,
    service_name: str,
    logger: logging.Logger,
    manager,
    web_app,
) -> None:
    """
    Run a web-backed worker service with a consistent startup/shutdown contract.
    """
    logger.info("%s starting up...", service_name)

    Instrumentator().instrument(web_app).expose(web_app)
    logger.info("Prometheus metrics exposed at /metrics")

    try:
        await manager.run()
    except Exception:
        logger.critical("%s encountered a critical error", service_name, exc_info=True)
        raise
    finally:
        logger.info("%s has shut down.", service_name)
