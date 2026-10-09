"""Isolated TCP host for native source routes; no worker or production lifespan claim."""

import asyncio
import json
import logging
import os
import socket
import sys


async def serve(inputs):
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
    asyncio.run(serve(json.loads(sys.stdin.readline())))
