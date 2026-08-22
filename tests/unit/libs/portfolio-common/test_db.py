import ast
import importlib
from collections import Counter
from pathlib import Path

import pytest
import sqlalchemy
import sqlalchemy.ext.asyncio as sa_async
from portfolio_common.database_runtime_identity import (
    DATABASE_APPLICATION_NAME_MAX_LENGTH,
    DATABASE_RUNTIME_IDENTITIES,
    database_runtime_identity,
    database_runtime_identity_scope,
)
from portfolio_common.database_runtime_profile import DatabaseRuntimeProfileError
from portfolio_common.db import get_async_database_url, get_sync_database_url
from portfolio_common.runtime_settings import RuntimeConfigurationError


class _FakeSyncSession:
    pass


class _FakeAsyncSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeFactory:
    def __init__(self, session_cls):
        self._session_cls = session_cls

    def __call__(self):
        return self._session_cls()


def test_db_module_import_does_not_create_engines(monkeypatch):
    sync_calls = []
    async_calls = []

    def _fake_create_engine(*args, **kwargs):
        sync_calls.append((args, kwargs))
        return object()

    def _fake_create_async_engine(*args, **kwargs):
        async_calls.append((args, kwargs))
        return object()

    monkeypatch.setattr(sqlalchemy, "create_engine", _fake_create_engine)
    monkeypatch.setattr(sa_async, "create_async_engine", _fake_create_async_engine)

    import portfolio_common.db as db_module

    reloaded = importlib.reload(db_module)

    assert reloaded._engine is None
    assert reloaded._async_engine is None
    assert sync_calls == []
    assert async_calls == []


def test_sessionlocal_creates_sync_engine_lazily(monkeypatch):
    sync_calls = []

    def _fake_create_engine(*args, **kwargs):
        sync_calls.append((args, kwargs))
        return object()

    monkeypatch.setattr(sqlalchemy, "create_engine", _fake_create_engine)
    monkeypatch.setattr(
        sqlalchemy.orm,
        "sessionmaker",
        lambda **kwargs: _FakeFactory(_FakeSyncSession),
    )

    import portfolio_common.db as db_module

    reloaded = importlib.reload(db_module)
    session = reloaded.SessionLocal()

    assert isinstance(session, _FakeSyncSession)
    assert sync_calls == [
        (
            (reloaded.get_sync_database_url(),),
            {
                "connect_args": {
                    "application_name": "lotus-core-local",
                    "connect_timeout": 60,
                    "options": ("-c statement_timeout=0 -c idle_in_transaction_session_timeout=0"),
                },
                "pool_pre_ping": True,
                "pool_size": 5,
                "max_overflow": 10,
                "pool_timeout": 30,
                "pool_recycle": -1,
            },
        )
    ]


def test_sync_database_url_normalizes_postgres_scheme(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgres://user:pass@host:5432/dbname")
    monkeypatch.delenv("HOST_DATABASE_URL", raising=False)

    assert get_sync_database_url() == "postgresql://user:pass@host:5432/dbname"


def test_async_database_url_normalizes_postgres_scheme(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgres://user:pass@host:5432/dbname")
    monkeypatch.delenv("HOST_DATABASE_URL", raising=False)

    assert get_async_database_url() == "postgresql+asyncpg://user:pass@host:5432/dbname"


def test_sync_database_url_removes_asyncpg_driver_scheme(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://user:pass@host:5432/dbname")
    monkeypatch.delenv("HOST_DATABASE_URL", raising=False)

    assert get_sync_database_url() == "postgresql://user:pass@host:5432/dbname"


def test_async_database_url_preserves_asyncpg_driver_scheme(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://user:pass@host:5432/dbname")
    monkeypatch.delenv("HOST_DATABASE_URL", raising=False)

    assert get_async_database_url() == "postgresql+asyncpg://user:pass@host:5432/dbname"


@pytest.mark.parametrize("url_loader", [get_sync_database_url, get_async_database_url])
def test_database_url_loader_rejects_local_default_in_production(monkeypatch, url_loader):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://user:password@postgres:5432/portfolio_db",
    )
    monkeypatch.delenv("HOST_DATABASE_URL", raising=False)

    with pytest.raises(RuntimeConfigurationError, match="local default database credentials"):
        url_loader()


@pytest.mark.parametrize("url_loader", [get_sync_database_url, get_async_database_url])
def test_database_url_loader_allows_default_in_explicit_local_profile(monkeypatch, url_loader):
    monkeypatch.setenv("ENVIRONMENT", "local")
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://user:password@postgres:5432/portfolio_db",
    )
    monkeypatch.delenv("HOST_DATABASE_URL", raising=False)

    assert url_loader().endswith("user:password@postgres:5432/portfolio_db")


@pytest.mark.asyncio
async def test_asyncsessionlocal_creates_async_engine_lazily(monkeypatch):
    async_calls = []

    def _fake_create_async_engine(*args, **kwargs):
        async_calls.append((args, kwargs))
        return object()

    monkeypatch.setattr(sa_async, "create_async_engine", _fake_create_async_engine)
    monkeypatch.setattr(
        sa_async,
        "async_sessionmaker",
        lambda **kwargs: _FakeFactory(_FakeAsyncSession),
    )

    import portfolio_common.db as db_module

    reloaded = importlib.reload(db_module)

    async with reloaded.AsyncSessionLocal() as session:
        assert isinstance(session, _FakeAsyncSession)

    assert async_calls == [
        (
            (reloaded.get_async_database_url(),),
            {
                "connect_args": {
                    "timeout": 60,
                    "server_settings": {
                        "application_name": "lotus-core-local",
                        "statement_timeout": "0ms",
                        "idle_in_transaction_session_timeout": "0ms",
                    },
                },
                "pool_pre_ping": True,
                "pool_size": 5,
                "max_overflow": 10,
                "pool_timeout": 30,
                "pool_recycle": -1,
            },
        )
    ]


def test_database_runtime_identity_accepts_only_allowlisted_service(monkeypatch):
    monkeypatch.setenv("SERVICE_NAME", "portfolio-transaction-processing")

    assert database_runtime_identity() == "portfolio-transaction-processing"


def test_explicit_database_runtime_identity_ignores_invalid_ambient_identity(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("SERVICE_NAME", "untrusted-ambient-identity")

    assert (
        database_runtime_identity(explicit_identity="derived-state-resource-monitor")
        == "derived-state-resource-monitor"
    )


def test_scoped_database_runtime_identity_is_restored(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("SERVICE_NAME", "query-service")

    with database_runtime_identity_scope("reprocess-transactions"):
        assert database_runtime_identity() == "reprocess-transactions"

    assert database_runtime_identity() == "query-service"


def test_standalone_sync_engine_uses_explicit_identity(monkeypatch):
    sync_calls = []

    import portfolio_common.db as db_module

    monkeypatch.setattr(
        db_module,
        "create_engine",
        lambda *args, **kwargs: sync_calls.append((args, kwargs)) or object(),
    )

    db_module.create_sync_database_engine(
        runtime_identity="offline-integrity-auditor",
        database_url="postgresql+asyncpg://user:pass@host:5432/dbname",
    )

    assert sync_calls == [
        (
            ("postgresql://user:pass@host:5432/dbname",),
            {
                "connect_args": {
                    "application_name": "offline-integrity-auditor",
                    "connect_timeout": 60,
                    "options": ("-c statement_timeout=0 -c idle_in_transaction_session_timeout=0"),
                },
                "pool_pre_ping": True,
                "pool_size": 5,
                "max_overflow": 10,
                "pool_timeout": 30,
                "pool_recycle": -1,
            },
        )
    ]


def test_standalone_async_engine_uses_explicit_identity(monkeypatch):
    async_calls = []

    import portfolio_common.db as db_module

    monkeypatch.setattr(
        db_module,
        "create_async_engine",
        lambda *args, **kwargs: async_calls.append((args, kwargs)) or object(),
    )

    db_module.create_async_database_engine(
        runtime_identity="average-cost-reconciliation",
        database_url="postgresql://user:pass@host:5432/dbname",
    )

    assert async_calls == [
        (
            ("postgresql+asyncpg://user:pass@host:5432/dbname",),
            {
                "connect_args": {
                    "timeout": 60,
                    "server_settings": {
                        "application_name": "average-cost-reconciliation",
                        "statement_timeout": "0ms",
                        "idle_in_transaction_session_timeout": "0ms",
                    },
                },
                "pool_pre_ping": True,
                "pool_size": 5,
                "max_overflow": 10,
                "pool_timeout": 30,
                "pool_recycle": -1,
            },
        )
    ]


@pytest.mark.parametrize(
    ("factory_name", "url"),
    [
        ("create_sync_database_engine", "postgresql://user:password@host:5432/dbname"),
        (
            "create_async_database_engine",
            "postgresql+asyncpg://user:password@host:5432/dbname",
        ),
    ],
)
def test_standalone_engine_rejects_direct_local_credentials_in_production(
    monkeypatch,
    factory_name,
    url,
):
    import portfolio_common.db as db_module

    monkeypatch.setenv("ENVIRONMENT", "production")
    engine_factory = getattr(db_module, factory_name)

    with pytest.raises(RuntimeConfigurationError, match="local default database credentials"):
        engine_factory(runtime_identity="offline-integrity-auditor", database_url=url)


def test_database_runtime_identity_uses_bounded_local_fallback(monkeypatch):
    monkeypatch.delenv("SERVICE_NAME", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "local")

    assert database_runtime_identity() == "lotus-core-local"


@pytest.mark.parametrize("service_name", ["", "unknown-service"])
def test_database_runtime_identity_rejects_blank_or_unknown_values(monkeypatch, service_name):
    monkeypatch.setenv("SERVICE_NAME", service_name)
    monkeypatch.setenv("ENVIRONMENT", "local")

    with pytest.raises(RuntimeConfigurationError, match="Invalid database runtime identity"):
        database_runtime_identity()


def test_database_runtime_identity_rejects_overlong_values(monkeypatch):
    monkeypatch.setenv("SERVICE_NAME", "x" * (DATABASE_APPLICATION_NAME_MAX_LENGTH + 1))

    with pytest.raises(RuntimeConfigurationError, match="63-byte limit"):
        database_runtime_identity()


def test_governed_identity_overrides_database_url_application_name(monkeypatch):
    sync_calls = []

    def _fake_create_engine(*args, **kwargs):
        sync_calls.append((args, kwargs))
        return object()

    monkeypatch.setattr(sqlalchemy, "create_engine", _fake_create_engine)
    monkeypatch.setenv("SERVICE_NAME", "query-service")
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://user:pass@host:5432/dbname?application_name=untrusted",
    )
    monkeypatch.delenv("HOST_DATABASE_URL", raising=False)

    import portfolio_common.db as db_module

    reloaded = importlib.reload(db_module)
    reloaded.get_engine()

    assert sync_calls[0][0][0].endswith("?application_name=untrusted")
    assert sync_calls[0][1]["connect_args"]["application_name"] == "query-service"


@pytest.mark.parametrize(
    "reserved_option",
    [
        "connect_args",
        "creator",
        "async_creator",
        "pool_size",
        "max_overflow",
        "pool_timeout",
        "pool_recycle",
    ],
)
def test_standalone_engine_rejects_governed_option_override(monkeypatch, reserved_option):
    import portfolio_common.db as db_module

    monkeypatch.setattr(db_module, "create_engine", lambda *args, **kwargs: object())

    with pytest.raises(DatabaseRuntimeProfileError, match="governed"):
        db_module.create_sync_database_engine(
            runtime_identity="offline-integrity-auditor",
            database_url="postgresql://user:pass@host:5432/dbname",
            **{reserved_option: object()},
        )


def test_governed_environment_fails_before_engine_creation_without_identity(monkeypatch):
    sync_calls = []
    monkeypatch.setattr(
        sqlalchemy,
        "create_engine",
        lambda *args, **kwargs: sync_calls.append((args, kwargs)),
    )
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://service:governed-secret@postgres:5432/portfolio_db",
    )
    monkeypatch.delenv("HOST_DATABASE_URL", raising=False)
    monkeypatch.delenv("SERVICE_NAME", raising=False)

    import portfolio_common.db as db_module

    reloaded = importlib.reload(db_module)
    with pytest.raises(RuntimeConfigurationError, match="SERVICE_NAME is required"):
        reloaded.get_engine()

    assert sync_calls == []


def test_database_runtime_identity_is_required_in_governed_environment(monkeypatch):
    monkeypatch.delenv("SERVICE_NAME", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "production")

    with pytest.raises(RuntimeConfigurationError, match="SERVICE_NAME is required"):
        database_runtime_identity()


def test_database_runtime_identity_inventory_is_bounded_and_postgres_safe():
    assert len(DATABASE_RUNTIME_IDENTITIES) == 27
    assert all(
        0 < len(identity) <= DATABASE_APPLICATION_NAME_MAX_LENGTH
        for identity in DATABASE_RUNTIME_IDENTITIES
    )


def _database_constructor_calls(tree: ast.AST) -> list[tuple[str, int]]:
    constructor_aliases: dict[str, str] = {}
    sqlalchemy_module_aliases: set[str] = set()
    dbapi_module_aliases: set[str] = set()
    dbapi_connect_aliases: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module == "sqlalchemy" or node.module.startswith("sqlalchemy."):
                for alias in node.names:
                    if alias.name in {
                        "create_engine",
                        "create_async_engine",
                        "engine_from_config",
                    }:
                        constructor_aliases[alias.asname or alias.name] = alias.name
            elif node.module in {"asyncpg", "psycopg", "psycopg2"}:
                dbapi_connect_aliases.update(
                    alias.asname or alias.name for alias in node.names if alias.name == "connect"
                )
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imported_name = alias.asname or alias.name.split(".")[0]
                if alias.name.startswith("sqlalchemy"):
                    sqlalchemy_module_aliases.add(imported_name)
                if alias.name in {"asyncpg", "psycopg", "psycopg2"}:
                    dbapi_module_aliases.add(imported_name)

    calls: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name):
            if node.func.id in dbapi_connect_aliases:
                calls.append(("dbapi.connect", node.lineno))
            elif node.func.id in constructor_aliases:
                calls.append((constructor_aliases[node.func.id], node.lineno))
        elif isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
            if node.func.value.id in dbapi_module_aliases and node.func.attr == "connect":
                calls.append(("dbapi.connect", node.lineno))
            elif node.func.value.id in sqlalchemy_module_aliases and node.func.attr in {
                "create_engine",
                "create_async_engine",
                "engine_from_config",
            }:
                calls.append((node.func.attr, node.lineno))
    return calls


@pytest.mark.parametrize(
    "source",
    [
        "from psycopg import connect\nconnect('dsn')",
        "from psycopg2 import connect as raw_connect\nraw_connect('dsn')",
        "from asyncpg import connect as open_database\nopen_database('dsn')",
        "import psycopg as pg\npg.connect('dsn')",
        "def bypass():\n from psycopg import connect as raw_connect\n raw_connect('dsn')",
    ],
)
def test_database_constructor_guard_detects_direct_dbapi_aliases(source):
    calls = _database_constructor_calls(ast.parse(source))

    assert len(calls) == 1
    assert calls[0][0] == "dbapi.connect"


def test_database_constructor_guard_detects_sqlalchemy_export_aliases():
    source = "from sqlalchemy.engine import create_engine as ce\nce('url')"

    assert _database_constructor_calls(ast.parse(source)) == [("create_engine", 2)]


def test_database_constructor_guard_detects_nested_sqlalchemy_aliases():
    source = "def bypass():\n from sqlalchemy.engine import create_engine as ce\n ce('url')"

    assert _database_constructor_calls(ast.parse(source)) == [("create_engine", 3)]


def test_database_engines_use_governed_factory():
    repo_root = Path(__file__).resolve().parents[4]
    expected_calls = {
        Path("src/libs/portfolio-common/portfolio_common/db.py"): Counter(
            {"create_engine": 2, "create_async_engine": 2}
        ),
        Path("alembic/env.py"): Counter({"engine_from_config": 1}),
    }
    violations: list[str] = []
    observed_calls: dict[Path, Counter[str]] = {}

    for source_root in ("src", "scripts", "tools", "alembic", "tests"):
        for path in (repo_root / source_root).rglob("*.py"):
            relative_path = path.relative_to(repo_root)
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(relative_path))
            for function_name, line_number in _database_constructor_calls(tree):
                if function_name == "dbapi.connect":
                    violations.append(f"{relative_path.as_posix()}:{line_number}")
                else:
                    observed_calls.setdefault(relative_path, Counter())[function_name] += 1
                    if relative_path not in expected_calls:
                        violations.append(f"{relative_path.as_posix()}:{line_number}")

    assert violations == [], (
        "Database engines must use portfolio_common.db governed factories: " + ", ".join(violations)
    )
    assert observed_calls == expected_calls
