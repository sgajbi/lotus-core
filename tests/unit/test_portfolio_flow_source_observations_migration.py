"""Frozen DDL parity and refusal decisions; no PostgreSQL execution claimed."""

import runpy
from pathlib import Path

import pytest
import sqlalchemy as sa
from portfolio_common.portfolio_flow_source_observation_models import (
    FlowEventObservationHead,
    FlowEventObservationRow,
    FlowSourceCutRow,
)
from sqlalchemy.dialects.postgresql import dialect
from sqlalchemy.schema import CreateTable

pytestmark = pytest.mark.unit


def migration(operations):
    root = next(p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file())
    module = runpy.run_path(
        str(root / "alembic/versions/c187b2c3d548_portfolio_flow_source_observations.py")
    )
    module["upgrade"].__globals__["op"] = operations
    return module


class Operations:
    def __init__(self, *, isolation="read committed", populated=False):
        self.metadata = sa.MetaData()
        for table, names in (
            ("portfolios", ("tenant_id", "portfolio_id")),
            ("ingestion_jobs", ("tenant_id", "job_id")),
        ):
            sa.Table(table, self.metadata, *(sa.Column(n, sa.String()) for n in names))
        self.isolation = isolation
        self.populated = populated
        self.events = []

    def create_table(self, name, *items):
        sa.Table(name, self.metadata, *items)

    def create_index(self, name, table, columns, **kwargs):
        sa.Index(name, *(self.metadata.tables[table].c[c] for c in columns), **kwargs)

    def execute(self, statement):
        self.events.append(str(statement))

    def drop_table(self, name):
        self.events.append("DROP " + name)

    def get_bind(self):
        return self

    def scalar(self, statement):
        self.events.append(str(statement))
        return self.isolation if str(statement) == "SHOW transaction_isolation" else self.populated


def normalize(value):
    return "".join(str(value).split())


def constraints(table):
    values = []
    for c in table.constraints:
        if isinstance(c, sa.CheckConstraint):
            values.append(("check", normalize(c.sqltext)))
        elif isinstance(c, sa.ForeignKeyConstraint):
            values.append(
                (
                    "foreign",
                    tuple(e.parent.name for e in c.elements),
                    tuple(e.target_fullname for e in c.elements),
                )
            )
        elif isinstance(c, sa.UniqueConstraint):
            values.append(("unique", tuple(x.name for x in c.columns)))
    return sorted(values)


def test_frozen_migration_matches_models_without_importing_mutable_models():
    operations = Operations()
    module = migration(operations)
    assert module["revision"] == "c187b2c3d548" and module["down_revision"] == "c186b2c3d547"
    module["upgrade"]()
    for model in (FlowEventObservationRow, FlowEventObservationHead, FlowSourceCutRow):
        frozen = operations.metadata.tables[model.__tablename__]
        expected = model.__table__
        assert constraints(frozen) == constraints(expected)
        assert sorted(
            (
                i.name,
                tuple(c.name for c in i.columns),
                i.unique,
                normalize(i.dialect_options["postgresql"].get("where")),
            )
            for i in frozen.indexes
        ) == sorted(
            (
                i.name,
                tuple(c.name for c in i.columns),
                i.unique,
                normalize(i.dialect_options["postgresql"].get("where")),
            )
            for i in expected.indexes
        )
        assert sorted(
            (c.name, str(c.type.compile(dialect=dialect())), c.nullable, c.primary_key)
            for c in frozen.columns
        ) == sorted(
            (c.name, str(c.type.compile(dialect=dialect())), c.nullable, c.primary_key)
            for c in expected.columns
        )
        assert "CREATE TABLE" in str(CreateTable(frozen).compile(dialect=dialect()))
    assert sum("BEFORE UPDATE OR DELETE" in e for e in operations.events) == 2
    assert sum("BEFORE TRUNCATE" in e for e in operations.events) == 3
    index = next(iter(operations.metadata.tables["portfolio_flow_source_cuts"].indexes))
    assert index.unique and index.name == "uq_flow_cut_successor"


@pytest.mark.parametrize(
    "isolation,populated,refused",
    [
        ("read committed", False, False),
        ("read committed", True, True),
        ("repeatable read", False, True),
        ("serializable", False, True),
    ],
)
def test_downgrade_requires_current_empty_history_after_fencing(isolation, populated, refused):
    operations = Operations(isolation=isolation, populated=populated)
    module = migration(operations)
    if refused:
        with pytest.raises(RuntimeError):
            module["downgrade"]()
        assert not any(e.startswith("DROP ") for e in operations.events)
    else:
        module["downgrade"]()
        assert sum(e.startswith("DROP ") for e in operations.events) == 3
    if isolation == "read committed":
        lock = next(i for i, e in enumerate(operations.events) if e.startswith("LOCK TABLE"))
        probe = next(i for i, e in enumerate(operations.events) if "SELECT EXISTS" in e)
        assert lock < probe and "ACCESS EXCLUSIVE MODE" in operations.events[lock]
