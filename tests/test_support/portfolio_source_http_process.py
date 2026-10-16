"""Isolated TCP host for native source routes; no worker or production lifespan claim."""

import os
import sys


def profile_preflight():
    if os.environ.get("LOTUS_OPERATOR_SOURCE_RECEIPT"):
        if not (
            sys.flags.isolated
            and sys.flags.no_user_site
            and sys.dont_write_bytecode
            and globals().get("_SOURCE_RECEIPT_API_VERIFIED")
        ):
            raise ValueError("isolated profile startup required")


if __name__ == "__main__":
    try:
        profile_preflight()
    except Exception:
        raise SystemExit(2) from None

import asyncio  # noqa: E402
import json  # noqa: E402
import logging  # noqa: E402
import socket  # noqa: E402


async def serve(inputs):
    operator = None
    if os.environ.get("LOTUS_OPERATOR_SOURCE_RECEIPT"):
        from tests.test_support.operator_source_database import attach_api

        operator = attach_api(inputs)
    # Configure deployment-owned trust before importing either registered application.
    os.environ.update(inputs["environment"])
    # Only the source-safe readiness envelope crosses the subprocess output pipe.
    logging.disable(logging.CRITICAL)
    import uvicorn
    from portfolio_common.database_runtime_profile import DatabasePoolMode
    from portfolio_common.db import create_async_database_engine, get_async_db_session
    from portfolio_common.domain.portfolio_source_observations import ObservationFamily
    from portfolio_common.portfolio_source_observation_qualification import (
        ProducerSubmissionGrant,
        UnqualifiedProducerAuthority,
    )
    from sqlalchemy import event, text
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from sqlalchemy.orm import Session

    from src.services.ingestion_service.app import dependencies
    from src.services.ingestion_service.app.main import app as writer
    from src.services.ingestion_service.app.services import ingestion_job_service as jobs
    from src.services.query_control_plane_service.app.main import app as reader

    engine = create_async_database_engine(
        runtime_identity="lotus-core-test",
        database_url=inputs["database_url"],
        pool_mode=DatabasePoolMode.NULL,
    )

    class OwnedSession(Session):
        pass

    def bind_namespace(session, transaction, connection):
        if operator is not None:
            connection.execute(text("SET LOCAL lock_timeout='1000ms'"))
            operator.handshake(connection)
        connection.execute(text('SET LOCAL search_path TO "' + inputs["schema"] + '", pg_temp'))

    event.listen(OwnedSession, "after_begin", bind_namespace)
    factory = async_sessionmaker(engine, expire_on_commit=False, sync_session_class=OwnedSession)

    async def sessions():
        async with factory() as session:
            yield session

    grants = tuple(
        ProducerSubmissionGrant(inputs["tenant"], inputs["portfolio"], "synthetic-source", family)
        for family in ObservationFamily
    )
    writer.dependency_overrides[get_async_db_session] = sessions
    reader.dependency_overrides[get_async_db_session] = sessions
    writer.dependency_overrides[dependencies.get_portfolio_source_observation_authority] = lambda: (
        UnqualifiedProducerAuthority(grants)
    )
    # Native receipt creation and ops controls share exactly the leased namespace.
    dependencies.get_async_db_session = sessions
    jobs.get_async_db_session = sessions

    async def registered_apps(scope, receive, send):
        if operator is not None and scope["type"] == "http":
            from tests.test_support.operator_source_database import budget_event

            allowed = (
                "/ingest/portfolio-cash-availability-observations",
                "/ingest/portfolio-funding-investment-observations",
                f"/integration/portfolios/{inputs['portfolio']}/financial-source-observations/query",
            )
            if scope["method"] != "POST" or scope["path"] not in allowed:
                raise RuntimeError("SOURCE_RECEIPT_ROUTE_REFUSED")
            budget_event(inputs["schema"], "http_calls")
        app = writer if scope["path"].startswith("/ingest/") else reader
        await app(scope, receive, send)

    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(128)
    server = uvicorn.Server(
        uvicorn.Config(registered_apps, lifespan="off", log_level="critical", access_log=False)
    )
    task = asyncio.create_task(server.serve(sockets=[listener]))
    try:
        while not server.started:
            if task.done():
                await task
                raise RuntimeError("native HTTP host stopped before startup")
            await asyncio.sleep(0.01)
        if operator is not None:
            from tests.test_support.operator_source_database import budget_event

            budget_event(inputs["schema"], "ready", listener.getsockname()[1])
        print(
            "OWNED_HTTP=" + json.dumps({"pid": os.getpid(), "port": listener.getsockname()[1]}),
            flush=True,
        )
        # The parent requests actual process exit, then waits for it before restart.
        await asyncio.to_thread(sys.stdin.readline)
        server.should_exit = True
        await task
    finally:
        server.should_exit = True
        await task
        listener.close()
        await engine.dispose()
        event.remove(OwnedSession, "after_begin", bind_namespace)


if __name__ == "__main__":
    try:
        if os.environ.get("LOTUS_OPERATOR_SOURCE_RECEIPT"):
            from tests.test_support.source_receipt_process_custody import read_launch_bound_private

            descriptor = read_launch_bound_private(
                sys.stdin.buffer, size=globals()["_SOURCE_RECEIPT_PRIVATE_SIZE"]
            )
        else:
            descriptor = sys.stdin.readline(65537)
            if len(descriptor.encode()) > 65536 or not descriptor.endswith("\n"):
                raise ValueError("bounded private descriptor required")
        asyncio.run(serve(json.loads(descriptor)))
    except Exception:
        # In operator mode even startup/SQL failures must not print private DSNs/claims.
        if not os.environ.get("LOTUS_OPERATOR_SOURCE_RECEIPT"):
            raise
        raise SystemExit(2) from None
