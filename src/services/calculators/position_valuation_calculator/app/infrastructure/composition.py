"""Compose the production position valuation processor."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from portfolio_common.db import get_async_db_session

from ..valuation_processor import (
    ValuationJobProcessor,
    ValuationProcessorDependencyFactory,
)
from .valuation_dependencies import SqlAlchemyValuationProcessorDependencyFactory


def build_valuation_job_processor(
    *,
    session_provider: Callable[[], Any] | None = None,
    dependency_factory: ValuationProcessorDependencyFactory | None = None,
) -> ValuationJobProcessor:
    """Build valuation processing with explicit runtime infrastructure dependencies."""
    resolved_session_provider = (
        session_provider if session_provider is not None else get_async_db_session
    )
    resolved_dependency_factory = (
        dependency_factory
        if dependency_factory is not None
        else SqlAlchemyValuationProcessorDependencyFactory()
    )
    return ValuationJobProcessor(
        session_provider=resolved_session_provider,
        dependency_factory=resolved_dependency_factory,
    )
