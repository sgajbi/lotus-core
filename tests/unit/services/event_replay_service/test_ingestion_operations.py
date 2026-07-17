import os
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.event_replay_service.app.application.replay_payload_dispatcher import (
    IngestionServiceReplayPayloadDispatcher,
)
from src.services.ingestion_service.app.domain import TransactionReprocessingTarget

REPO_ROOT = Path(__file__).resolve().parents[4]


def _dispatcher(
    ingestion_service: MagicMock,
    *,
    resolved_targets: tuple[TransactionReprocessingTarget, ...] = (),
) -> tuple[IngestionServiceReplayPayloadDispatcher, AsyncMock]:
    resolver = AsyncMock()
    resolver.execute.return_value = resolved_targets
    return IngestionServiceReplayPayloadDispatcher(ingestion_service, resolver), resolver


def _copy_package_tree(source: Path, destination: Path) -> None:
    shutil.copytree(
        source,
        destination,
        ignore=shutil.ignore_patterns("__pycache__", "*.egg-info"),
    )


def test_event_replay_app_imports_under_compose_runtime_layout(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    _copy_package_tree(
        REPO_ROOT / "src" / "services" / "event_replay_service" / "app",
        runtime_root / "app",
    )
    _copy_package_tree(
        REPO_ROOT / "src" / "services" / "ingestion_service" / "app",
        runtime_root / "src" / "services" / "ingestion_service" / "app",
    )

    python_path = os.pathsep.join(
        [
            str(runtime_root),
            str(REPO_ROOT / "src" / "libs" / "portfolio-common"),
        ]
    )
    env = {**os.environ, "PYTHONPATH": python_path}

    result = subprocess.run(
        [sys.executable, "-c", "import app.main"],
        cwd=runtime_root,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr


@pytest.mark.asyncio
async def test_replay_payload_dispatcher_dispatches_list_field_payload_with_idempotency_key() -> (
    None
):
    ingestion_service = MagicMock()
    ingestion_service.publish_business_dates = AsyncMock()

    dispatcher, _ = _dispatcher(ingestion_service)

    await dispatcher.replay_payload(
        endpoint="/ingest/business-dates",
        payload={"business_dates": [{"business_date": "2026-06-22"}]},
        idempotency_key="idem-001",
    )

    ingestion_service.publish_business_dates.assert_awaited_once()
    args, kwargs = ingestion_service.publish_business_dates.await_args
    assert [business_date.business_date for business_date in args[0]] == [date(2026, 6, 22)]
    assert kwargs == {"idempotency_key": "idem-001"}


@pytest.mark.asyncio
async def test_replay_payload_dispatcher_dispatches_whole_portfolio_bundle_request() -> None:
    ingestion_service = MagicMock()
    ingestion_service.publish_portfolio_bundle = AsyncMock()

    dispatcher, _ = _dispatcher(ingestion_service)

    await dispatcher.replay_payload(
        endpoint="/ingest/portfolio-bundle",
        payload={"business_dates": [{"business_date": "2026-06-22"}]},
        idempotency_key="idem-002",
    )

    ingestion_service.publish_portfolio_bundle.assert_awaited_once()
    args, kwargs = ingestion_service.publish_portfolio_bundle.await_args
    assert args[0].business_dates[0].business_date == date(2026, 6, 22)
    assert kwargs == {"idempotency_key": "idem-002"}


@pytest.mark.asyncio
async def test_replay_payload_dispatcher_rejects_unsupported_endpoint() -> None:
    dispatcher, _ = _dispatcher(MagicMock())

    with pytest.raises(ValueError, match="Retry not supported"):
        await dispatcher.replay_payload(
            endpoint="/ingest/not-supported",
            payload={},
            idempotency_key=None,
        )


@pytest.mark.asyncio
async def test_replay_payload_dispatcher_resolves_reprocessing_ordering_targets() -> None:
    ingestion_service = MagicMock()
    ingestion_service.publish_reprocessing_requests = AsyncMock()
    targets = (
        TransactionReprocessingTarget(transaction_id="TXN-1", portfolio_id="PORT-1"),
        TransactionReprocessingTarget(transaction_id="TXN-2", portfolio_id="PORT-2"),
    )
    dispatcher, resolver = _dispatcher(ingestion_service, resolved_targets=targets)

    await dispatcher.replay_payload(
        endpoint="/reprocess/transactions",
        payload={"transaction_ids": [" TXN-1 ", "TXN-2"]},
        idempotency_key="idem-reprocess",
    )

    resolver.execute.assert_awaited_once_with(["TXN-1", "TXN-2"])
    ingestion_service.publish_reprocessing_requests.assert_awaited_once_with(
        targets,
        idempotency_key="idem-reprocess",
    )
