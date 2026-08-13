import logging.config
import os
import runpy
import sys
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import alembic.context as alembic_context
import dotenv
import pytest
import sqlalchemy
from alembic.autogenerate import render_python_code
from alembic.operations.ops import CreateTableOp, UpgradeOps
from portfolio_common.alembic_numeric import render_financial_numeric
from portfolio_common.financial_numeric import ExactNumeric
from portfolio_common.runtime_settings import RuntimeConfigurationError
from sqlalchemy import Column, Integer, MetaData, Table

ALEMBIC_ENV = Path("alembic/env.py")


def test_exact_numeric_autogeneration_uses_portable_sqlalchemy_type() -> None:
    table = Table(
        "financial_facts",
        MetaData(),
        Column("id", Integer, primary_key=True),
        Column("bounded", ExactNumeric(18, 10), nullable=False),
        Column("exact", ExactNumeric(), nullable=False),
    )

    generated = render_python_code(
        UpgradeOps(ops=[CreateTableOp.from_table(table)]),
        render_item=render_financial_numeric,
    )

    assert "sa.Numeric(precision=18, scale=10)" in generated
    assert "sa.Numeric()" in generated
    assert "portfolio_common" not in generated


def test_alembic_renderer_delegates_unowned_objects() -> None:
    assert render_financial_numeric("column", ExactNumeric(18, 10), object()) is False


def _configure_alembic_context(
    monkeypatch: pytest.MonkeyPatch,
    *,
    offline: bool,
    config_file_name: str | None = None,
) -> tuple[Mock, Mock]:
    configure = Mock()
    run_migrations = Mock()
    config = SimpleNamespace(
        config_file_name=config_file_name,
        config_ini_section="alembic",
        get_section=Mock(return_value={}),
    )
    monkeypatch.setattr(alembic_context, "config", config, raising=False)
    monkeypatch.setattr(alembic_context, "is_offline_mode", Mock(return_value=offline))
    monkeypatch.setattr(alembic_context, "configure", configure)
    monkeypatch.setattr(alembic_context, "begin_transaction", Mock(return_value=nullcontext()))
    monkeypatch.setattr(alembic_context, "run_migrations", run_migrations)
    return configure, run_migrations


def test_alembic_environment_wires_renderer_for_offline_migrations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure, run_migrations = _configure_alembic_context(
        monkeypatch,
        offline=True,
        config_file_name="alembic.ini",
    )
    file_config = Mock()
    load_dotenv = Mock()
    monkeypatch.setattr(logging.config, "fileConfig", file_config)
    monkeypatch.setattr(dotenv, "load_dotenv", load_dotenv)
    original_exists = os.path.exists
    monkeypatch.setattr(
        os.path,
        "exists",
        lambda path: True if path == str(Path.cwd() / ".env") else original_exists(path),
    )
    injected_paths = {
        str(Path.cwd() / "src"),
        str(Path.cwd() / "src" / "libs" / "portfolio-common"),
    }
    monkeypatch.setattr(sys, "path", [path for path in sys.path if path not in injected_paths])
    monkeypatch.setenv(
        "HOST_DATABASE_URL",
        "postgresql+asyncpg://lotus:secret@postgres/lotus",
    )

    runpy.run_path(str(ALEMBIC_ENV))

    file_config.assert_called_once_with("alembic.ini")
    load_dotenv.assert_called_once_with(str(Path.cwd() / ".env"))
    assert injected_paths.issubset(sys.path)
    configure.assert_called_once()
    options = configure.call_args.kwargs
    assert options["url"] == "postgresql://lotus:secret@postgres/lotus"
    assert options["render_item"] is render_financial_numeric
    assert options["literal_binds"] is True
    run_migrations.assert_called_once_with()


def test_alembic_environment_wires_renderer_for_online_migrations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure, run_migrations = _configure_alembic_context(monkeypatch, offline=False)
    connection = object()
    connectable = Mock()
    connectable.connect.return_value = nullcontext(connection)
    engine_from_config = Mock(return_value=connectable)
    monkeypatch.setattr(sqlalchemy, "engine_from_config", engine_from_config)
    monkeypatch.delenv("HOST_DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://lotus:secret@postgres/lotus")

    runpy.run_path(str(ALEMBIC_ENV))

    engine_config = engine_from_config.call_args.args[0]
    assert engine_config["sqlalchemy.url"] == "postgresql://lotus:secret@postgres/lotus"
    assert engine_from_config.call_args.kwargs["connect_args"] == {
        "application_name": "lotus-core-local"
    }
    configure.assert_called_once_with(
        connection=connection,
        target_metadata=configure.call_args.kwargs["target_metadata"],
        render_item=render_financial_numeric,
    )
    run_migrations.assert_called_once_with()


def test_alembic_environment_fails_closed_without_database_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_alembic_context(monkeypatch, offline=True)
    monkeypatch.delenv("HOST_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(Exception, match="Neither HOST_DATABASE_URL nor DATABASE_URL"):
        runpy.run_path(str(ALEMBIC_ENV))


def test_alembic_environment_rejects_local_credentials_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_alembic_context(monkeypatch, offline=True)
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("HOST_DATABASE_URL", raising=False)
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://user:password@postgres:5432/portfolio_db",
    )

    with pytest.raises(RuntimeConfigurationError, match="local default database credentials"):
        runpy.run_path(str(ALEMBIC_ENV))
