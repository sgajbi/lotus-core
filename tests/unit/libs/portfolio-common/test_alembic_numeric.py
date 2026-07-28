from alembic.autogenerate import render_python_code
from alembic.operations.ops import CreateTableOp, UpgradeOps
from portfolio_common.alembic_numeric import render_financial_numeric
from portfolio_common.financial_numeric import ExactNumeric
from sqlalchemy import Column, Integer, MetaData, Table


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
