"""Tests for query-control-plane business-date infrastructure."""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

from src.services.query_control_plane_service.app.infrastructure import (
    SqlAlchemyBusinessDateProvider,
)


class _Result:
    @staticmethod
    def scalar_one_or_none() -> date:
        return date(2026, 2, 27)


class _Session:
    def __enter__(self) -> _Session:
        return self

    def __exit__(self, *_args: object) -> bool:
        return False

    @staticmethod
    def execute(_statement: object) -> _Result:
        return _Result()


def test_provider_reads_latest_default_calendar_business_date(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://dummy")
    with patch(
        "src.services.query_control_plane_service.app.infrastructure.business_dates.SessionLocal",
        return_value=_Session(),
    ):
        resolved = SqlAlchemyBusinessDateProvider().latest_business_date()

    assert resolved == date(2026, 2, 27)


def test_provider_returns_none_when_database_access_fails(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://dummy")
    with patch(
        "src.services.query_control_plane_service.app.infrastructure.business_dates.SessionLocal",
        side_effect=RuntimeError("database unavailable"),
    ):
        resolved = SqlAlchemyBusinessDateProvider().latest_business_date()

    assert resolved is None


def test_provider_avoids_session_creation_without_database_configuration(
    monkeypatch,
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("HOST_DATABASE_URL", raising=False)
    with patch(
        "src.services.query_control_plane_service.app.infrastructure.business_dates.SessionLocal"
    ) as session_factory:
        resolved = SqlAlchemyBusinessDateProvider().latest_business_date()

    assert resolved is None
    session_factory.assert_not_called()
