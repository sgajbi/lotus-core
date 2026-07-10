import asyncio
import logging
from collections.abc import Callable, Sequence
from typing import Any

from prometheus_fastapi_instrumentator import Instrumentator

from portfolio_common.health_server import health_probe_bind_host
from portfolio_common.http_app_bootstrap import (
    configure_metrics_access_policy,
    resolve_metrics_access_policy,
)
from portfolio_common.runtime_supervision import (
    shutdown_runtime_components,
    wait_for_shutdown_or_task_failure,
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


async def run_kafka_worker_runtime(
    *,
    consumers: Sequence[Any],
    dispatcher: Any,
    web_app: Any,
    web_port: int,
    readiness_service_name: str,
    shutdown_event: asyncio.Event,
    signal_handler: Callable[[int, object], None],
    tasks: list[asyncio.Task[Any]],
    logger: logging.Logger,
    ensure_topics: Callable[[list[str]], None],
    signal_module: Any,
    server_config_factory: Callable[..., Any],
    server_factory: Callable[[Any], Any],
) -> None:
    """Run Kafka consumers, one outbox dispatcher, and the worker health server."""
    required_topics = [str(getattr(consumer, "topic")) for consumer in consumers]
    ensure_topics(required_topics)

    signal_module.signal(signal_module.SIGINT, signal_handler)
    signal_module.signal(signal_module.SIGTERM, signal_handler)

    config = server_config_factory(
        web_app,
        host=health_probe_bind_host(),
        port=web_port,
        log_config=None,
    )
    server = server_factory(config)

    logger.info(
        "Starting Kafka worker runtime.",
        extra={"consumer_count": len(consumers), "web_port": web_port},
    )
    tasks.clear()
    tasks.extend(
        asyncio.create_task(
            consumer.run(),
            name=_consumer_task_name(consumer, index=index),
        )
        for index, consumer in enumerate(consumers)
    )
    tasks.append(asyncio.create_task(dispatcher.run(), name="outbox-dispatcher"))
    tasks.append(asyncio.create_task(server.serve(), name="health-server"))

    runtime_error = await wait_for_shutdown_or_task_failure(
        tasks=tasks,
        shutdown_event=shutdown_event,
        logger=logger,
        readiness_service_name=readiness_service_name,
    )

    await shutdown_runtime_components(
        tasks=tasks,
        consumers=consumers,
        stop_callbacks=[dispatcher.stop],
        server=server,
        logger=logger,
    )
    if runtime_error is not None:
        raise runtime_error


def _consumer_task_name(consumer: Any, *, index: int) -> str:
    group_id = _task_name_component(getattr(consumer, "group_id", None))
    topic = _task_name_component(getattr(consumer, "topic", None))
    if group_id and topic:
        return f"kafka-consumer:{group_id}:{topic}"[:128]
    return f"kafka-consumer:{index}"


def _task_name_component(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    if not normalized:
        return None
    return "".join(
        character if character.isalnum() or character in {"-", "_", "."} else "_"
        for character in normalized
    )[:64]
