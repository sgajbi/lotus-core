"""Bounded source-capture worker supervised inside the existing persistence process."""

import asyncio

from .application.financial_source_cut_processing import FinancialSourceCutProcessor


def build_financial_source_cut_workers(session_factory, *, settings=None):
    from portfolio_common.runtime_settings import financial_source_cut_worker_settings

    from .infrastructure.financial_source_capture_client import NativeFinancialSourceCaptureClient
    from .repositories.financial_source_cut_work_repository import FinancialSourceCutWorkRepository

    policy = settings or financial_source_cut_worker_settings()
    return [
        FinancialSourceCutWorker(
            FinancialSourceCutProcessor(
                FinancialSourceCutWorkRepository(
                    session_factory,
                    lease_seconds=policy.lease_seconds,
                    retry_seconds=policy.retry_seconds,
                ),
                NativeFinancialSourceCaptureClient(session_factory),
            ),
            idle_seconds=policy.idle_milliseconds / 1000,
        )
        for _ in range(policy.worker_count)
    ]


class FinancialSourceCutWorker:
    def __init__(self, processor: FinancialSourceCutProcessor, *, idle_seconds: float = 0.5):
        if idle_seconds <= 0:
            raise ValueError("positive bounded idle interval required")
        self.processor = processor
        self.idle_seconds = idle_seconds
        self._stop = asyncio.Event()

    def stop(self) -> None:
        self._stop.set()

    async def run(self) -> None:
        try:
            while not self._stop.is_set():
                advanced = await self.processor.step()
                if not advanced:
                    try:
                        await asyncio.wait_for(self._stop.wait(), self.idle_seconds)
                    except TimeoutError:
                        pass
        finally:
            await self.processor.captures.close()
