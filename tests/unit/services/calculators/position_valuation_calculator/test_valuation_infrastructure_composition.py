"""Test explicit position valuation infrastructure composition."""

from __future__ import annotations

import inspect
from unittest.mock import MagicMock, patch

from services.calculators.position_valuation_calculator.app import valuation_processor
from services.calculators.position_valuation_calculator.app.infrastructure import (
    SqlAlchemyValuationProcessorDependencyFactory,
    build_valuation_job_processor,
    composition,
    valuation_dependencies,
)


def test_valuation_processor_requires_injected_runtime_dependencies() -> None:
    session_provider = MagicMock()
    dependency_factory = MagicMock()

    processor = build_valuation_job_processor(
        session_provider=session_provider,
        dependency_factory=dependency_factory,
    )

    assert processor._session_provider is session_provider
    assert processor._dependency_factory is dependency_factory


def test_sqlalchemy_dependency_factory_constructs_concrete_adapters() -> None:
    session = MagicMock()
    with (
        patch.object(valuation_dependencies, "ValuationRepository") as repository,
        patch.object(valuation_dependencies, "IdempotencyRepository") as idempotency_repository,
        patch.object(valuation_dependencies, "OutboxRepository") as outbox_repository,
    ):
        dependencies = SqlAlchemyValuationProcessorDependencyFactory().from_session(session)

    repository.assert_called_once_with(session)
    idempotency_repository.assert_called_once_with(session)
    outbox_repository.assert_called_once_with(session)
    assert dependencies.repo is repository.return_value
    assert dependencies.idempotency_repo is idempotency_repository.return_value
    assert dependencies.outbox_repo is outbox_repository.return_value


def test_valuation_processor_does_not_construct_infrastructure() -> None:
    source = inspect.getsource(valuation_processor)

    assert "get_async_db_session" not in source
    assert "ValuationRepository(" not in source
    assert "IdempotencyRepository(" not in source
    assert "OutboxRepository(" not in source


def test_new_valuation_infrastructure_modules_have_responsibility_docstrings() -> None:
    assert inspect.getdoc(composition)
    assert inspect.getdoc(valuation_dependencies)
