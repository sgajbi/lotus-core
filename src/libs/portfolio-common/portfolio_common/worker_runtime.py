import logging

from prometheus_fastapi_instrumentator import Instrumentator


def _has_metrics_route(web_app) -> bool:
    return any(
        getattr(route, "path", None) == "/metrics" for route in getattr(web_app, "routes", ())
    )


def _ensure_worker_metrics(web_app, logger: logging.Logger) -> None:
    if _has_metrics_route(web_app):
        logger.info("Prometheus metrics already exposed at /metrics")
        return

    Instrumentator().instrument(web_app).expose(web_app)
    logger.info("Prometheus metrics exposed at /metrics")


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

    try:
        _ensure_worker_metrics(web_app, logger)
        await manager.run()
    except Exception:
        logger.critical("%s encountered a critical error", service_name, exc_info=True)
        raise
    finally:
        logger.info("%s has shut down.", service_name)
