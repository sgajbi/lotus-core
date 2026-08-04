from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.quality.financial_numeric_persistence_guard import (
    DEFAULT_CONTRACT_PATH,
    ROOT,
    evaluate_guard,
    inventory_numeric_columns,
)


def _model(
    *,
    constraint: str | None,
    nullable: bool = False,
    exact_numeric: bool = True,
) -> str:
    constraint_source = (
        f', CheckConstraint("{constraint}", name="ck_financial_value")'
        if constraint is not None
        else ""
    )
    numeric_import = (
        "from portfolio_common.financial_numeric import ExactNumeric\n"
        if exact_numeric
        else "from sqlalchemy import Numeric\n"
    )
    numeric_type = "ExactNumeric" if exact_numeric else "Numeric"
    return (
        numeric_import + "from sqlalchemy import CheckConstraint, Column\n\n"
        "class FinancialRow:\n"
        '    __tablename__ = "financial_rows"\n'
        f"    value = Column({numeric_type}(18, 10), nullable={nullable!r})\n"
        f"    __table_args__ = ({constraint_source.lstrip(', ')},)\n"
        if constraint is not None
        else (
            numeric_import + "from sqlalchemy import Column\n\n"
            "class FinancialRow:\n"
            '    __tablename__ = "financial_rows"\n'
            f"    value = Column({numeric_type}(18, 10), nullable={nullable!r})\n"
        )
    )


def _keyword_type_model() -> str:
    return (
        "from portfolio_common.financial_numeric import ExactNumeric\n"
        "from sqlalchemy import CheckConstraint, Column\n\n"
        "class FinancialRow:\n"
        '    __tablename__ = "financial_rows"\n'
        "    value: object = Column(type_=ExactNumeric(18, 10), nullable=False)\n"
        "    __table_args__ = (\n"
        "        CheckConstraint(\n"
        "            \"CAST(value AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity')\",\n"
        '            name="ck_financial_value_finite",\n'
        "        ),\n"
        '        CheckConstraint("value > 0", name="ck_financial_value_positive"),\n'
        "    )\n"
    )


def _finite_helper_model(*, dynamic_column: bool = False) -> str:
    column_argument = "column_name" if dynamic_column else '"value"'
    dynamic_declaration = 'column_name = "value"\n\n' if dynamic_column else ""
    return (
        "from portfolio_common.financial_numeric import ExactNumeric\n"
        "from sqlalchemy import CheckConstraint, Column\n\n"
        f"{dynamic_declaration}"
        "class FinancialRow:\n"
        '    __tablename__ = "financial_rows"\n'
        "    value = Column(ExactNumeric(18, 10), nullable=False)\n"
        "    __table_args__ = (\n"
        "        _finite_numeric_check_constraint(\n"
        '            "ck_financial_value_finite",\n'
        f"            {column_argument},\n"
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
    storage_shape: str = "bounded-18-10",
) -> dict[str, object]:
    contract: dict[str, object] = {
        "schema_version": "2.0.0",
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
        "storage_shapes": {
            "bounded-18-10": {
                "mode": "bounded",
                "precision": 18,
                "scale": 10,
            },
            "exact-unbounded": {
                "mode": "exact-unbounded",
                "precision": None,
                "scale": None,
            },
        },
        "default_storage_shape": "bounded-18-10",
        "exact_bind_enforcement": "required",
        "storage_shape_overrides": {},
        "domain_families": {
            "financial-test": {
                "owner": "test-owner",
                "boundary_class": "api-command",
            }
        },
        "table_domain_families": {"financial_rows": "financial-test"},
        "tables": {
            "financial_rows": {column: {"profile": profile, "rollout_status": rollout_status}}
        },
    }
    if storage_shape != "bounded-18-10":
        contract["storage_shape_overrides"] = {f"financial_rows.{column}": storage_shape}
    return contract


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


def _assert_only_exact_bind_finding(findings: tuple[str, ...]) -> None:
    assert len(findings) == 1
    assert findings[0].startswith(
        "financial_rows.value: precision contract requires ExactNumeric bind enforcement; "
    )


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
    assert report.bounded_numeric_count == 1
    assert report.unbounded_numeric_count == 0
    assert report.domain_family_count == 1
    assert report.orm_enforced_count == 1
    assert report.database_enforced_count == 0
    assert report.planned_count == 0


def test_guard_requires_exact_numeric_when_contract_enables_bind_enforcement(
    tmp_path: Path,
) -> None:
    contract = _contract()
    contract_path = _write_fixture(
        tmp_path,
        model=_model(
            constraint=(
                "value NOT IN ('NaN'::numeric, 'Infinity'::numeric, "
                "'-Infinity'::numeric) AND value > 0"
            ),
            exact_numeric=False,
        ),
        contract=contract,
    )

    report = evaluate_guard(tmp_path, contract_path)

    _assert_only_exact_bind_finding(report.findings)


def test_guard_requires_exact_bind_enforcement_key(tmp_path: Path) -> None:
    contract = _contract()
    del contract["exact_bind_enforcement"]
    contract_path = _write_fixture(
        tmp_path,
        model=_model(
            constraint=(
                "value NOT IN ('NaN'::numeric, 'Infinity'::numeric, "
                "'-Infinity'::numeric) AND value > 0"
            )
        ),
        contract=contract,
    )

    report = evaluate_guard(tmp_path, contract_path)

    assert (
        "contract v2 keys must be schema_version, model_path, expected_inventory, "
        "profiles, rollout_statuses, storage_shapes, default_storage_shape, "
        "exact_bind_enforcement, storage_shape_overrides, domain_families, "
        "table_domain_families, and tables"
    ) in report.findings
    assert "contract.exact_bind_enforcement must be required" in report.findings


@pytest.mark.parametrize(
    "keyword",
    ["asdecimal=False", "asdecimal=dynamic_setting", "decimal_return_scale=10"],
)
def test_inventory_rejects_inexact_exact_numeric_options(
    tmp_path: Path,
    keyword: str,
) -> None:
    model_path = tmp_path / "database_models.py"
    model_path.write_text(
        "from portfolio_common.financial_numeric import ExactNumeric\n"
        "from sqlalchemy import Column\n\n"
        "class FinancialRow:\n"
        '    __tablename__ = "financial_rows"\n'
        f"    value = Column(ExactNumeric(18, 10, {keyword}), nullable=False)\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="ExactNumeric"):
        inventory_numeric_columns(model_path)


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


def test_guard_accepts_finiteness_as_final_term_in_grouped_constraint(
    tmp_path: Path,
) -> None:
    contract_path = _write_fixture(
        tmp_path,
        model=_model(
            constraint=(
                "value > 0 AND (CAST(value AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity'))"
            )
        ),
        contract=_contract(),
    )

    assert evaluate_guard(tmp_path, contract_path).findings == ()


def test_guard_accepts_canonical_finite_constraint_helper(tmp_path: Path) -> None:
    contract_path = _write_fixture(
        tmp_path,
        model=_finite_helper_model(),
        contract=_contract(),
    )

    assert evaluate_guard(tmp_path, contract_path).findings == ()


def test_guard_rejects_dynamic_finite_constraint_helper_column(tmp_path: Path) -> None:
    contract_path = _write_fixture(
        tmp_path,
        model=_finite_helper_model(dynamic_column=True),
        contract=_contract(),
    )

    report = evaluate_guard(tmp_path, contract_path)

    assert report.findings[0] == (
        "cannot inventory ORM model database_models.py: "
        "FinancialRow: _finite_numeric_check_constraint arguments must be string literals"
    )


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

    _assert_only_exact_bind_finding(report.findings)
    assert report.numeric_column_count == 1


@pytest.mark.parametrize(
    ("import_source", "type_expression", "storage_shape"),
    [
        ("from sqlalchemy import Numeric as X", "X(18, 10)", "bounded-18-10"),
        ("from sqlalchemy import DECIMAL", "DECIMAL(18, 10)", "bounded-18-10"),
        ("from sqlalchemy import NUMERIC", "NUMERIC", "exact-unbounded"),
        ("from sqlalchemy import Numeric", "Numeric", "exact-unbounded"),
        ("import sqlalchemy as sa", "sa.Numeric(18, 10)", "bounded-18-10"),
    ],
)
def test_guard_inventories_imported_numeric_constructor_forms(
    tmp_path: Path,
    import_source: str,
    type_expression: str,
    storage_shape: str,
) -> None:
    contract_path = _write_fixture(
        tmp_path,
        model=_numeric_constructor_model(
            import_source=import_source,
            type_expression=type_expression,
        ),
        contract=_contract(storage_shape=storage_shape),
    )

    report = evaluate_guard(tmp_path, contract_path)

    _assert_only_exact_bind_finding(report.findings)
    assert report.numeric_column_count == 1


@pytest.mark.parametrize(
    ("column_type", "storage_shape"),
    [
        ("MONEY_TYPE(18, 10)", "bounded-18-10"),
        ("type_=MONEY_TYPE(18, 10)", "bounded-18-10"),
        ("MONEY_ALIAS(18, 10)", "bounded-18-10"),
        ("type_=MONEY_ALIAS", "exact-unbounded"),
    ],
)
def test_guard_inventories_attribute_constructor_aliases(
    tmp_path: Path,
    column_type: str,
    storage_shape: str,
) -> None:
    contract_path = _write_fixture(
        tmp_path,
        model=_attribute_constructor_alias_model(column_type=column_type),
        contract=_contract(storage_shape=storage_shape),
    )

    report = evaluate_guard(tmp_path, contract_path)

    _assert_only_exact_bind_finding(report.findings)
    assert report.numeric_column_count == 1


@pytest.mark.parametrize(
    ("type_expression", "expected_shape"),
    [
        ("Numeric(18, 10)", (18, 10)),
        ("Numeric(precision=18, scale=4)", (18, 4)),
        ("Numeric(18, 0)", (18, 0)),
        ("Numeric()", (None, None)),
        ("Numeric", (None, None)),
    ],
)
def test_inventory_records_numeric_precision_and_scale(
    tmp_path: Path,
    type_expression: str,
    expected_shape: tuple[int | None, int | None],
) -> None:
    model_path = tmp_path / "database_models.py"
    model_path.write_text(
        _numeric_constructor_model(
            import_source="from sqlalchemy import Numeric",
            type_expression=type_expression,
        ),
        encoding="utf-8",
    )

    column = inventory_numeric_columns(model_path)[0]

    assert (column.precision, column.scale) == expected_shape
    assert column.is_unbounded is (expected_shape == (None, None))


@pytest.mark.parametrize(
    "model",
    [
        _numeric_constructor_model(
            import_source="from sqlalchemy import Numeric",
            type_expression="Numeric(PRECISION, 10)",
        ),
        _numeric_constructor_model(
            import_source="from sqlalchemy import Numeric",
            type_expression="Numeric(10)",
        ),
        _numeric_constructor_model(
            import_source="from sqlalchemy import Numeric",
            type_expression="Numeric(4, 10)",
        ),
    ],
)
def test_guard_rejects_ambiguous_or_invalid_numeric_shape(
    tmp_path: Path,
    model: str,
) -> None:
    contract_path = _write_fixture(
        tmp_path,
        model=model,
        contract=_contract(),
    )

    findings = evaluate_guard(tmp_path, contract_path).findings

    assert findings
    assert findings[0].startswith("cannot inventory ORM model database_models.py:")


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


def test_guard_rejects_unsupported_contract_extension_in_v2(tmp_path: Path) -> None:
    contract = _contract(rollout_status="planned")
    contract["database_enforcement_evidence"] = {"financial_rows.value": {"unsupported": True}}
    contract_path = _write_fixture(
        tmp_path,
        model=_model(constraint=None),
        contract=contract,
    )

    assert (
        "contract v2 keys must be schema_version, model_path, expected_inventory, "
        "profiles, rollout_statuses, storage_shapes, default_storage_shape, "
        "exact_bind_enforcement, storage_shape_overrides, domain_families, "
        "table_domain_families, and tables" in evaluate_guard(tmp_path, contract_path).findings
    )


def test_guard_rejects_storage_shape_drift(tmp_path: Path) -> None:
    contract_path = _write_fixture(
        tmp_path,
        model=_model(
            constraint=(
                "value NOT IN ('NaN'::numeric, 'Infinity'::numeric, "
                "'-Infinity'::numeric) AND value > 0"
            )
        ),
        contract=_contract(storage_shape="exact-unbounded"),
    )

    assert evaluate_guard(tmp_path, contract_path).findings == (
        "financial_rows.value: ORM Numeric(18, 10) conflicts with "
        "storage shape 'exact-unbounded' Numeric(None, None)",
    )


def test_guard_rejects_unknown_stale_and_redundant_storage_shape_overrides(
    tmp_path: Path,
) -> None:
    contract = _contract()
    contract["storage_shape_overrides"] = {
        "financial_rows.value": "bounded-18-10",
        "financial_rows.missing": "exact-unbounded",
    }
    contract_path = _write_fixture(
        tmp_path,
        model=_model(
            constraint=(
                "value NOT IN ('NaN'::numeric, 'Infinity'::numeric, "
                "'-Infinity'::numeric) AND value > 0"
            )
        ),
        contract=contract,
    )

    findings = evaluate_guard(tmp_path, contract_path).findings

    assert "financial_rows.value: redundant storage-shape override matches the default" in findings
    assert (
        "storage-shape override has no classified Numeric column: 'financial_rows.missing'"
        in findings
    )


@pytest.mark.parametrize(
    ("shape", "expected_finding"),
    [
        (
            {"mode": "exact-unbounded", "precision": 18, "scale": 10},
            "storage shape 'bounded-18-10' exact-unbounded mode requires null precision and scale",
        ),
        (
            {"mode": "bounded", "precision": 4, "scale": 10},
            "storage shape 'bounded-18-10' bounded mode requires precision > 0 "
            "and 0 <= scale <= precision",
        ),
        (
            {"mode": "rounded", "precision": 18, "scale": 10},
            "storage shape 'bounded-18-10' has unsupported mode 'rounded'",
        ),
    ],
)
def test_guard_rejects_invalid_storage_shape_definitions(
    tmp_path: Path,
    shape: dict[str, object],
    expected_finding: str,
) -> None:
    contract = _contract()
    storage_shapes = contract["storage_shapes"]
    assert isinstance(storage_shapes, dict)
    storage_shapes["bounded-18-10"] = shape
    contract_path = _write_fixture(
        tmp_path,
        model=_model(
            constraint=(
                "value NOT IN ('NaN'::numeric, 'Infinity'::numeric, "
                "'-Infinity'::numeric) AND value > 0"
            )
        ),
        contract=contract,
    )

    assert expected_finding in evaluate_guard(tmp_path, contract_path).findings


def test_guard_rejects_missing_stale_and_unknown_domain_family_mappings(
    tmp_path: Path,
) -> None:
    contract = _contract()
    contract["table_domain_families"] = {
        "financial_rows": "unknown-family",
        "stale_rows": "financial-test",
    }
    contract_path = _write_fixture(
        tmp_path,
        model=_model(
            constraint=(
                "value NOT IN ('NaN'::numeric, 'Infinity'::numeric, "
                "'-Infinity'::numeric) AND value > 0"
            )
        ),
        contract=contract,
    )

    findings = evaluate_guard(tmp_path, contract_path).findings

    assert "financial_rows: domain-family mapping names unknown family 'unknown-family'" in findings
    assert "stale_rows: domain-family mapping has no classified Numeric table" in findings
    assert "domain family 'financial-test' is not assigned to a Numeric table" in findings


@pytest.mark.parametrize(
    ("family", "expected_finding"),
    [
        (
            {"owner": "Test Owner", "boundary_class": "api-command"},
            "domain family 'financial-test' has invalid owner 'Test Owner'",
        ),
        (
            {"owner": "test-owner", "boundary_class": "database"},
            "domain family 'financial-test' has unsupported boundary_class 'database'",
        ),
    ],
)
def test_guard_rejects_invalid_domain_family_metadata(
    tmp_path: Path,
    family: dict[str, str],
    expected_finding: str,
) -> None:
    contract = _contract()
    domain_families = contract["domain_families"]
    assert isinstance(domain_families, dict)
    domain_families["financial-test"] = family
    contract_path = _write_fixture(
        tmp_path,
        model=_model(
            constraint=(
                "value NOT IN ('NaN'::numeric, 'Infinity'::numeric, "
                "'-Infinity'::numeric) AND value > 0"
            )
        ),
        contract=contract,
    )

    assert expected_finding in evaluate_guard(tmp_path, contract_path).findings


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
    amortized_cost_profiles = {
        column: classification["profile"]
        for table in ("lot_amortized_cost_profiles", "lot_amortized_cost_periods")
        for column, classification in contract["tables"][table].items()
    }
    lot_state_profiles = {
        column: classification["profile"]
        for column, classification in contract["tables"]["position_lot_state"].items()
    }
    disposal_profiles = {
        table: {
            column: classification["profile"]
            for column, classification in contract["tables"][table].items()
        }
        for table in ("lot_disposal_receipts", "lot_disposal_allocations")
    }

    assert report.numeric_column_count == 131
    assert report.table_count == 35
    assert report.bounded_numeric_count == 128
    assert report.unbounded_numeric_count == 3
    assert report.domain_family_count == 11
    assert report.orm_enforced_count == 131
    assert report.database_enforced_count == 0
    assert report.planned_count == 0
    assert transaction_profiles["quantity"] == "nonnegative-finite"
    assert transaction_profiles["price"] == "nonnegative-finite"
    assert transaction_profiles["gross_transaction_amount"] == "nonnegative-finite"
    assert transaction_profiles["gross_cost"] == "nullable-finite"
    assert transaction_profiles["net_cost"] == "nullable-finite"
    assert transaction_profiles["net_cost_local"] == "nullable-finite"
    assert transaction_profiles["net_interest_amount"] == "nullable-nonnegative-finite"
    assert amortized_cost_profiles["initial_amortized_cost_local"] == (
        "nullable-nonnegative-finite"
    )
    assert amortized_cost_profiles["year_fraction"] == "positive-finite"
    assert amortized_cost_profiles["period_rate"] == "nullable-finite"
    assert amortized_cost_profiles["rounding_adjustment_local"] == "finite"
    assert lot_state_profiles["amortized_book_carrying_local"] == ("nullable-nonnegative-finite")
    assert lot_state_profiles["amortized_book_carrying_base"] == ("nullable-nonnegative-finite")
    assert disposal_profiles["lot_disposal_receipts"] == {
        "consumed_quantity": "nonnegative-finite",
        "consumed_cost_local": "nonnegative-finite",
        "consumed_cost_base": "nonnegative-finite",
    }
    assert disposal_profiles["lot_disposal_allocations"] == {
        "consumed_quantity": "positive-finite",
        "consumed_cost_local": "nonnegative-finite",
        "consumed_cost_base": "nonnegative-finite",
        "amortized_cost_original_quantity": "nullable-positive-finite",
        "amortized_cost_open_quantity_before": "nullable-positive-finite",
        "amortized_cost_residual_quantity": "nullable-nonnegative-finite",
        "amortized_cost_scheduled_local": "nullable-nonnegative-finite",
        "amortized_cost_current_local": "nullable-nonnegative-finite",
        "amortized_cost_current_base": "nullable-nonnegative-finite",
        "amortized_cost_residual_local": "nullable-nonnegative-finite",
        "amortized_cost_book_fx_rate_to_base": "nullable-positive-finite",
        "amortized_cost_residual_base": "nullable-nonnegative-finite",
        "amortized_cost_retained_rounding_local": "nullable-finite",
        "amortized_cost_retained_rounding_base": "nullable-finite",
    }
