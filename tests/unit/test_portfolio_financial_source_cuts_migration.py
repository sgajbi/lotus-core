"""Frozen DDL/model parity and downgrade refusal; no SQL is executed."""

import runpy
from pathlib import Path

import pytest
from portfolio_common import database_models
from sqlalchemy.dialects.postgresql import dialect
from sqlalchemy.schema import CreateIndex, CreateTable

pytestmark = pytest.mark.unit


def migration(operations):
    root = next(p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file())
    module = runpy.run_path(
        str(root / "alembic/versions/c188b2c3d549_portfolio_financial_source_cuts.py")
    )
    module["upgrade"].__globals__["op"] = operations
    return module


class RecordingOperations:
    def __init__(self, *, populated=None, unknown_dependent=False):
        self.populated = populated
        self.unknown_dependent = unknown_dependent
        self.executed = []
        self.dropped = []

    def execute(self, statement):
        self.executed.append(str(statement))

    def get_bind(self):
        return self

    def scalar(self, statement):
        return self.populated is not None and self.populated in str(statement)

    def drop_table(self, name):
        if self.unknown_dependent:
            raise RuntimeError("unknown dependent prevents non-cascade drop")
        self.dropped.append(name)


def normal(sql):
    return " ".join(sql.split())


def test_frozen_ddl_matches_registered_models_without_mutable_model_import_in_migration():
    operations = RecordingOperations()
    module = migration(operations)
    assert (module["revision"], module["down_revision"]) == ("c188b2c3d549", "c187b2c3d548")
    expected = []
    for name in module["TABLES"]:
        table = database_models.IngestionJob.metadata.tables[name]
        expected.append(normal(str(CreateTable(table).compile(dialect=dialect()))))
        expected.extend(
            normal(str(CreateIndex(index).compile(dialect=dialect())))
            for index in sorted(table.indexes, key=lambda i: i.name)
        )
    assert [normal(sql) for sql in module["CREATE_DDL"]] == expected
    module["upgrade"]()
    assert len(operations.executed) == len(expected) + 7 + 9
    assert sum("BEFORE UPDATE OR DELETE" in sql for sql in operations.executed) == 7
    assert sum("BEFORE TRUNCATE" in sql for sql in operations.executed) == 9
    assert not any("CASCADE" in sql for sql in operations.executed)


@pytest.mark.parametrize(
    "table",
    [
        "portfolio_financial_source_cut_work",
        "portfolio_financial_source_capture_segments",
        "portfolio_historical_registry_members",
    ],
)
def test_any_populated_history_or_work_refuses_downgrade_before_first_drop(table):
    operations = RecordingOperations(populated=table)
    with pytest.raises(RuntimeError, match="nonempty"):
        migration(operations)["downgrade"]()
    assert operations.dropped == []
    assert operations.executed[0].startswith("LOCK TABLE ")
    assert operations.executed[0].endswith(" IN ACCESS EXCLUSIVE MODE")


def test_empty_downgrade_reverses_fk_creation_order_and_unknown_dependency_refuses():
    operations = RecordingOperations()
    module = migration(operations)
    module["downgrade"]()
    assert operations.dropped == list(reversed(module["TABLES"]))
    unknown = RecordingOperations(unknown_dependent=True)
    with pytest.raises(RuntimeError, match="unknown dependent"):
        migration(unknown)["downgrade"]()
    assert unknown.dropped == []
