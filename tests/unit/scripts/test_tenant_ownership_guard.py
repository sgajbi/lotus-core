from pathlib import Path

from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import registry

from scripts.quality.tenant_ownership_guard import (
    _is_blocking,
    find_orm_tenant_findings,
    find_synthetic_default_findings,
)


def test_orm_report_lists_only_tables_without_tenant_ownership() -> None:
    mapper_registry = registry()
    base = mapper_registry.generate_base()

    class TenantOwned(base):
        __tablename__ = "tenant_owned"
        id = Column(Integer, primary_key=True)
        tenant_id = Column(String, nullable=False)

    class MissingTenant(base):
        __tablename__ = "missing_tenant"
        id = Column(Integer, primary_key=True)

    findings = find_orm_tenant_findings(base)

    assert [finding.detail for finding in findings] == ["missing_tenant (MissingTenant)"]


def test_synthetic_default_scan_covers_fields_dicts_keywords_and_headers(tmp_path: Path) -> None:
    source = tmp_path / "src" / "app" / "tenant_defaults.py"
    source.parent.mkdir(parents=True)
    source.write_text(
        "tenant_id: str = 'default'\n"
        "payload = {'tenant_id': 'default'}\n"
        "scope = build(tenant_id='default')\n"
        "header = headers.get('X-Tenant-Id', 'default')\n",
        encoding="utf-8",
    )

    findings = find_synthetic_default_findings(tmp_path)

    assert len(findings) == 4
    assert {finding.rule for finding in findings} == {"synthetic-default-tenant"}


def test_report_mode_banks_orm_debt_while_default_enforcement_blocks_new_fallbacks() -> None:
    mapper_registry = registry()
    base = mapper_registry.generate_base()

    class MissingTenant(base):
        __tablename__ = "missing_tenant"
        id = Column(Integer, primary_key=True)

    finding = find_orm_tenant_findings(base)[0]

    assert _is_blocking(finding, "report") is False
    assert _is_blocking(finding, "enforce-defaults") is False
    assert _is_blocking(finding, "enforce") is True
