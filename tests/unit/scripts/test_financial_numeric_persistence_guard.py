from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.quality.financial_numeric_persistence_guard import (
    DEFAULT_CONTRACT_PATH,
    ROOT,
    evaluate_guard,
)


def _model(*, constraint: str | None, nullable: bool = False) -> str:
    constraint_source = (
        f', CheckConstraint("{constraint}", name="ck_financial_value")'
        if constraint is not None
        else ""
    )
    return (
        "from sqlalchemy import CheckConstraint, Column, Numeric\n\n"
        "class FinancialRow:\n"
        '    __tablename__ = "financial_rows"\n'
        f"    value = Column(Numeric(18, 10), nullable={nullable!r})\n"
        f"    __table_args__ = ({constraint_source.lstrip(', ')},)\n"
        if constraint is not None
        else (
            "from sqlalchemy import Column, Numeric\n\n"
            "class FinancialRow:\n"
            '    __tablename__ = "financial_rows"\n'
            f"    value = Column(Numeric(18, 10), nullable={nullable!r})\n"
        )
    )


def _keyword_type_model() -> str:
    return (
        "from sqlalchemy import CheckConstraint, Column, Numeric\n\n"
        "class FinancialRow:\n"
        '    __tablename__ = "financial_rows"\n'
        "    value: object = Column(type_=Numeric(18, 10), nullable=False)\n"
        "    __table_args__ = (\n"
        "        CheckConstraint(\n"
        "            \"CAST(value AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity')\",\n"
        '            name="ck_financial_value_finite",\n'
        "        ),\n"
        '        CheckConstraint("value > 0", name="ck_financial_value_positive"),\n'
        "    )\n"
    )


def _numeric_alias_model(*, keyword: bool, include_unclassified: bool = False) -> str:
    column_type = "type_=MONEY" if keyword else "MONEY"
    unclassified = (
        f"    unclassified = Column({column_type}, nullable=False)\n"
        if include_unclassified
        else ""
    )
    return (
        "from sqlalchemy import CheckConstraint, Column, Numeric\n\n"
        "MONEY_BASE = Numeric(18, 10)\n"
        "MONEY = MONEY_BASE\n\n"
        "class FinancialRow:\n"
        '    __tablename__ = "financial_rows"\n'
        f"    value = Column({column_type}, nullable=False)\n"
        f"{unclassified}"
        "    __table_args__ = (\n"
        "        CheckConstraint(\n"
        "            \"CAST(value AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity')\",\n"
        '            name="ck_financial_value_finite",\n'
        "        ),\n"
        '        CheckConstraint("value > 0", name="ck_financial_value_positive"),\n'
        "    )\n"
    )


def _numeric_constructor_model(*, import_source: str, type_expression: str) -> str:
    return (
        f"{import_source}\n"
        "from sqlalchemy import CheckConstraint, Column\n\n"
        "class FinancialRow:\n"
        '    __tablename__ = "financial_rows"\n'
        f"    value = Column({type_expression}, nullable=False)\n"
        "    __table_args__ = (\n"
        "        CheckConstraint(\n"
        "            \"CAST(value AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity')\",\n"
        '            name="ck_financial_value_finite",\n'
        "        ),\n"
        '        CheckConstraint("value > 0", name="ck_financial_value_positive"),\n'
        "    )\n"
    )


def _attribute_constructor_alias_model(*, column_type: str) -> str:
    return (
        "import sqlalchemy as sa\n"
        "from sqlalchemy import CheckConstraint, Column\n\n"
        "MONEY_TYPE = sa.Numeric\n"
        "MONEY_ALIAS = MONEY_TYPE\n\n"
        "class FinancialRow:\n"
        '    __tablename__ = "financial_rows"\n'
        f"    value = Column({column_type}, nullable=False)\n"
        "    __table_args__ = (\n"
        "        CheckConstraint(\n"
        "            \"CAST(value AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity')\",\n"
        '            name="ck_financial_value_finite",\n'
        "        ),\n"
        '        CheckConstraint("value > 0", name="ck_financial_value_positive"),\n'
        "    )\n"
    )


def _contract(
    *,
    profile: str = "positive-finite",
    rollout_status: str = "orm-enforced",
    column: str = "value",
) -> dict[str, object]:
    return {
        "schema_version": "1.0.0",
        "model_path": "database_models.py",
        "expected_inventory": {"numeric_columns": 1, "tables": 1},
        "profiles": {
            "finite": {"nullable": False, "sign": "signed"},
            "positive-finite": {"nullable": False, "sign": "positive"},
            "nonnegative-finite": {"nullable": False, "sign": "nonnegative"},
            "nullable-finite": {"nullable": True, "sign": "signed"},
            "nullable-positive-finite": {"nullable": True, "sign": "positive"},
            "nullable-nonnegative-finite": {
                "nullable": True,
                "sign": "nonnegative",
            },
        },
        "rollout_statuses": ["orm-enforced", "planned"],
        "tables": {
            "financial_rows": {column: {"profile": profile, "rollout_status": rollout_status}}
        },
    }


def _write_fixture(
    root: Path,
    *,
    model: str,
    contract: dict[str, object] | str,
) -> Path:
    (root / "database_models.py").write_text(model, encoding="utf-8")
    contract_path = root / "contract.json"
    contract_path.write_text(
        contract if isinstance(contract, str) else json.dumps(contract),
        encoding="utf-8",
    )
    return contract_path


def test_guard_accepts_explicit_finiteness_and_sign_policy(tmp_path: Path) -> None:
    contract_path = _write_fixture(
        tmp_path,
        model=_model(
            constraint=(
                "value NOT IN ('NaN'::numeric, 'Infinity'::numeric, "
                "'-Infinity'::numeric) AND value > 0"
            )
        ),
        contract=_contract(),
    )

    report = evaluate_guard(tmp_path, contract_path)

    assert report.findings == ()
    assert report.numeric_column_count == 1
    assert report.table_count == 1
    assert report.orm_enforced_count == 1
    assert report.database_enforced_count == 0
    assert report.planned_count == 0


def test_guard_accepts_postgresql_text_cast_finiteness_constraint(
    tmp_path: Path,
) -> None:
    contract_path = _write_fixture(
        tmp_path,
        model=_model(
            constraint=("CAST(value AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity') AND value > 0")
        ),
        contract=_contract(),
    )

    assert evaluate_guard(tmp_path, contract_path).findings == ()


def test_guard_inventories_keyword_type_numeric_column(tmp_path: Path) -> None:
    contract_path = _write_fixture(
        tmp_path,
        model=_keyword_type_model(),
        contract=_contract(),
    )

    report = evaluate_guard(tmp_path, contract_path)

    assert report.findings == ()
    assert report.numeric_column_count == 1


@pytest.mark.parametrize("keyword", [False, True])
def test_guard_inventories_direct_reusable_numeric_alias(
    tmp_path: Path,
    keyword: bool,
) -> None:
    contract_path = _write_fixture(
        tmp_path,
        model=_numeric_alias_model(keyword=keyword),
        contract=_contract(),
    )

    report = evaluate_guard(tmp_path, contract_path)

    assert report.findings == ()
    assert report.numeric_column_count == 1


@pytest.mark.parametrize(
    ("import_source", "type_expression"),
    [
        ("from sqlalchemy import Numeric as X", "X(18, 10)"),
        ("from sqlalchemy import DECIMAL", "DECIMAL(18, 10)"),
        ("from sqlalchemy import NUMERIC", "NUMERIC"),
        ("from sqlalchemy import Numeric", "Numeric"),
        ("import sqlalchemy as sa", "sa.Numeric(18, 10)"),
    ],
)
def test_guard_inventories_imported_numeric_constructor_forms(
    tmp_path: Path,
    import_source: str,
    type_expression: str,
) -> None:
    contract_path = _write_fixture(
        tmp_path,
        model=_numeric_constructor_model(
            import_source=import_source,
            type_expression=type_expression,
        ),
        contract=_contract(),
    )

    report = evaluate_guard(tmp_path, contract_path)

    assert report.findings == ()
    assert report.numeric_column_count == 1


@pytest.mark.parametrize(
    "column_type",
    [
        "MONEY_TYPE(18, 10)",
        "type_=MONEY_TYPE(18, 10)",
        "MONEY_ALIAS(18, 10)",
        "type_=MONEY_ALIAS",
    ],
)
def test_guard_inventories_attribute_constructor_aliases(
    tmp_path: Path,
    column_type: str,
) -> None:
    contract_path = _write_fixture(
        tmp_path,
        model=_attribute_constructor_alias_model(column_type=column_type),
        contract=_contract(),
    )

    report = evaluate_guard(tmp_path, contract_path)

    assert report.findings == ()
    assert report.numeric_column_count == 1


def test_guard_rejects_unclassified_column_using_numeric_alias(tmp_path: Path) -> None:
    contract_path = _write_fixture(
        tmp_path,
        model=_numeric_alias_model(keyword=False, include_unclassified=True),
        contract=_contract(),
    )

    findings = evaluate_guard(tmp_path, contract_path).findings

    assert "financial_rows.unclassified: Numeric column is missing a classification" in findings
    assert any("ORM has 2" in finding for finding in findings)


def test_guard_accepts_planned_column_and_reports_residual(tmp_path: Path) -> None:
    contract_path = _write_fixture(
        tmp_path,
        model=_model(constraint=None, nullable=True),
        contract=_contract(
            profile="nullable-finite",
            rollout_status="planned",
        ),
    )

    report = evaluate_guard(tmp_path, contract_path)

    assert report.findings == ()
    assert report.orm_enforced_count == 0
    assert report.database_enforced_count == 0
    assert report.planned_count == 1


def test_guard_rejects_database_enforced_in_v1(tmp_path: Path) -> None:
    contract_path = _write_fixture(
        tmp_path,
        model=_model(constraint=None),
        contract=_contract(rollout_status="database-enforced"),
    )

    report = evaluate_guard(tmp_path, contract_path)

    assert report.database_enforced_count == 0
    assert "financial_rows.value: unknown rollout_status 'database-enforced'" in report.findings


def test_guard_rejects_database_evidence_extension_in_v1(tmp_path: Path) -> None:
    contract = _contract(rollout_status="planned")
    contract["database_enforcement_evidence"] = {"financial_rows.value": {"unsupported": True}}
    contract_path = _write_fixture(
        tmp_path,
        model=_model(constraint=None),
        contract=contract,
    )

    assert (
        "contract v1 keys must be schema_version, model_path, expected_inventory, "
        "profiles, rollout_statuses, and tables" in evaluate_guard(tmp_path, contract_path).findings
    )


def test_guard_rejects_sign_only_constraint_as_finiteness(tmp_path: Path) -> None:
    contract_path = _write_fixture(
        tmp_path,
        model=_model(constraint="value > 0"),
        contract=_contract(),
    )

    report = evaluate_guard(tmp_path, contract_path)

    assert report.findings == (
        "financial_rows.value: orm-enforced classification lacks an explicit "
        "ORM exclusion of NaN, Infinity, and -Infinity",
    )


@pytest.mark.parametrize(
    "constraint",
    [
        "value <> 'NaN'::numeric AND value > 0",
        "value <> 'Infinity'::numeric AND value > 0",
        "value <> '-Infinity'::numeric AND value > 0",
        "value NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric) OR TRUE",
        "NOT (value NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric)) "
        "AND value > 0",
        "value NOT IN ('NaN', 'Infinity', '-Infinity', NULL) AND value > 0",
        "value NOT IN ('NaN', 'Infinity', '-Infinity', '0') AND value > 0",
        "value NOT IN ('NaN', 'Infinity', 'Infinity') AND value > 0",
        "other_value NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric) "
        "AND value > 0",
    ],
)
def test_guard_requires_all_special_values_for_the_classified_column(
    tmp_path: Path,
    constraint: str,
) -> None:
    contract_path = _write_fixture(
        tmp_path,
        model=_model(constraint=constraint),
        contract=_contract(),
    )

    assert any(
        "lacks an explicit ORM exclusion" in finding
        for finding in evaluate_guard(tmp_path, contract_path).findings
    )


def test_guard_rejects_missing_extra_and_nullable_mismatches(tmp_path: Path) -> None:
    contract = _contract(column="obsolete_value")
    contract_path = _write_fixture(
        tmp_path,
        model=_model(constraint=None, nullable=True),
        contract=contract,
    )

    findings = evaluate_guard(tmp_path, contract_path).findings

    assert "financial_rows.value: Numeric column is missing a classification" in findings
    assert (
        "financial_rows.obsolete_value: classification has no matching ORM Numeric column"
        in findings
    )


def test_guard_rejects_nullable_profile_drift(tmp_path: Path) -> None:
    contract_path = _write_fixture(
        tmp_path,
        model=_model(constraint=None, nullable=True),
        contract=_contract(profile="finite", rollout_status="planned"),
    )

    assert evaluate_guard(tmp_path, contract_path).findings == (
        "financial_rows.value: ORM nullable=True conflicts with finite",
    )


def test_guard_rejects_unknown_profile_and_rollout_status(tmp_path: Path) -> None:
    contract = _contract(profile="mostly-finite", rollout_status="assumed")
    contract_path = _write_fixture(
        tmp_path,
        model=_model(constraint=None),
        contract=contract,
    )

    findings = evaluate_guard(tmp_path, contract_path).findings

    assert "financial_rows.value: unknown finite-policy profile 'mostly-finite'" in findings
    assert "financial_rows.value: unknown rollout_status 'assumed'" in findings


def test_guard_rejects_duplicate_json_classification_keys(tmp_path: Path) -> None:
    contract_path = _write_fixture(
        tmp_path,
        model=_model(constraint=None),
        contract=(
            '{"schema_version":"1.0.0","schema_version":"1.0.0","model_path":"database_models.py"}'
        ),
    )

    report = evaluate_guard(tmp_path, contract_path)

    assert report.numeric_column_count == 0
    assert "duplicate JSON key: schema_version" in report.findings[0]


def test_guard_rejects_uninventoried_mapped_numeric_shape(tmp_path: Path) -> None:
    contract_path = _write_fixture(
        tmp_path,
        model=(
            "from decimal import Decimal\n"
            "from sqlalchemy import Numeric\n"
            "from sqlalchemy.orm import Mapped, mapped_column\n\n"
            "class FinancialRow:\n"
            '    __tablename__ = "financial_rows"\n'
            "    value: Mapped[Decimal] = mapped_column(Numeric(18, 10), nullable=False)\n"
        ),
        contract=_contract(),
    )

    report = evaluate_guard(tmp_path, contract_path)

    assert report.numeric_column_count == 0
    assert report.findings[0] == (
        "cannot inventory ORM model database_models.py: value: unsupported mapped_column "
        "Numeric declaration; use Column or extend the guard inventory"
    )


def test_guard_rejects_indirect_numeric_alias(tmp_path: Path) -> None:
    contract_path = _write_fixture(
        tmp_path,
        model=(
            "from sqlalchemy import Column, Numeric\n\n"
            "MONEY = make_type(Numeric(18, 10))\n\n"
            "class FinancialRow:\n"
            '    __tablename__ = "financial_rows"\n'
            "    value = Column(MONEY, nullable=False)\n"
        ),
        contract=_contract(),
    )

    report = evaluate_guard(tmp_path, contract_path)

    assert report.numeric_column_count == 0
    assert report.findings[0] == (
        "cannot inventory ORM model database_models.py: MONEY: unsupported indirect "
        "Numeric alias; assign Numeric(...) directly or extend the guard inventory"
    )


def test_repository_contract_classifies_inventory_and_persistence_semantics() -> None:
    report = evaluate_guard()
    contract = json.loads((ROOT / DEFAULT_CONTRACT_PATH).read_text(encoding="utf-8"))
    transaction_profiles = {
        column: classification["profile"]
        for column, classification in contract["tables"]["transactions"].items()
    }

    assert report.numeric_column_count == 96
    assert report.table_count == 30
    assert report.orm_enforced_count == 14
    assert report.database_enforced_count == 0
    assert report.planned_count == 82
    assert transaction_profiles["quantity"] == "nonnegative-finite"
    assert transaction_profiles["price"] == "nonnegative-finite"
    assert transaction_profiles["gross_transaction_amount"] == "nonnegative-finite"
    assert transaction_profiles["gross_cost"] == "nullable-finite"
    assert transaction_profiles["net_cost"] == "nullable-finite"
    assert transaction_profiles["net_cost_local"] == "nullable-finite"
    assert transaction_profiles["net_interest_amount"] == "nullable-nonnegative-finite"
