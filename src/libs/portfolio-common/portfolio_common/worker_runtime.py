import logging

from prometheus_fastapi_instrumentator import Instrumentator

from portfolio_common.http_app_bootstrap import (
    configure_metrics_access_policy,
    resolve_metrics_access_policy,
)


def _has_metrics_route(web_app) -> bool:
    return any(
        getattr(route, "path", None) == "/metrics" for route in getattr(web_app, "routes", ())
    )


def _ensure_worker_metrics(
    web_app,
    logger: logging.Logger,
    *,
    metrics_access_token: str | None = None,
) -> None:
    metrics_access_policy = resolve_metrics_access_policy(metrics_access_token)
    if _has_metrics_route(web_app):
        logger.info(
            "Prometheus metrics already exposed at /metrics",
            extra={"metrics_access_mode": metrics_access_policy.mode},
        )
        configure_metrics_access_policy(web_app, metrics_access_policy=metrics_access_policy)
        return

    Instrumentator().instrument(web_app).expose(web_app)
    configure_metrics_access_policy(web_app, metrics_access_policy=metrics_access_policy)
    logger.info(
        "Prometheus metrics exposed at /metrics",
        extra={"metrics_access_mode": metrics_access_policy.mode},
    )


async def run_instrumented_worker_service(
    *,
    service_name: str,
    logger: logging.Logger,
    manager,
    web_app,
    metrics_access_token: str | None = None,
) -> None:
    """
    Run a web-backed worker service with a consistent startup/shutdown contract.
    """
    logger.info("%s starting up...", service_name)

    try:
        _ensure_worker_metrics(
            web_app,
            logger,
            metrics_access_token=metrics_access_token,
        )
        await manager.run()
    except Exception:
        logger.critical("%s encountered a critical error", service_name, exc_info=True)
        raise
    finally:
        logger.info("%s has shut down.", service_name)
