"""Behavior tests for QCP-owned client tax-rule resolution."""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from src.services.query_control_plane_service.app.application.client_tax_rule_set import (
    ClientTaxRuleSetService,
)
from src.services.query_control_plane_service.app.contracts.client_tax_rule_set import (
    ClientTaxRuleSetRequest,
)
from src.services.query_control_plane_service.app.domain.client_tax_rule_set import (
    ClientTaxRuleSourceRecord,
)
from src.services.query_control_plane_service.app.domain.effective_mandate import (
    EffectiveMandateBinding,
)


class _Clock:
    def utc_now(self) -> datetime:
        return datetime(2026, 5, 3, 10, tzinfo=UTC)


class _Reader:
    def __init__(self, binding, rules):
        self.binding = binding
        self.rules = rules
        self.calls: list[str] = []

    async def resolve(self, **_):
        self.calls.append("binding")
        return self.binding

    async def list_rules(self, **_):
        self.calls.append("rules")
        return self.rules


def _binding() -> EffectiveMandateBinding:
    return EffectiveMandateBinding(
        "CIF_SG_000184",
        "MANDATE_PB_SG_GLOBAL_BAL_001",
        datetime(2026, 5, 3, 8, tzinfo=UTC),
        datetime(2026, 5, 3, 7, tzinfo=UTC),
        datetime(2026, 5, 3, 8, tzinfo=UTC),
    )


def _rule() -> ClientTaxRuleSourceRecord:
    timestamp = datetime(2026, 5, 3, 9, tzinfo=UTC)
    return ClientTaxRuleSourceRecord(
        rule_set_id="TAX_RULES_SG_2026",
        tax_year=2026,
        jurisdiction_code="SG",
        rule_code="US_DIVIDEND_WITHHOLDING",
        rule_category="WITHHOLDING",
        rule_status="active",
        rule_source="bank_tax_reference",
        applies_to_asset_classes=("equity",),
        applies_to_security_ids=(),
        applies_to_income_types=("DIVIDEND",),
        rate=Decimal("0.3000000000"),
        threshold_amount=Decimal("250000.0000"),
        threshold_currency="USD",
        effective_from=date(2026, 1, 1),
        effective_to=None,
        rule_version=2,
        source_record_id="tax-rule:2",
        observed_at=timestamp,
        created_at=timestamp,
        updated_at=timestamp,
    )


def _request() -> ClientTaxRuleSetRequest:
    return ClientTaxRuleSetRequest(
        as_of_date=date(2026, 5, 3), tenant_id="default", mandate_id="MANDATE_PB_SG_GLOBAL_BAL_001"
    )


def _service(reader: _Reader) -> ClientTaxRuleSetService:
    return ClientTaxRuleSetService(mandate_reader=reader, reader=reader, clock=_Clock())


@pytest.mark.asyncio
async def test_resolves_ready_tax_rules() -> None:
    reader = _Reader(_binding(), [_rule()])
    response = await _service(reader).get_client_tax_rule_set(
        portfolio_id="PB_SG_GLOBAL_BAL_001", request=_request()
    )
    assert response is not None
    assert response.generated_at == datetime(2026, 5, 3, 10, tzinfo=UTC)
    assert response.supportability.state == "READY"
    assert response.rules[0].rate == Decimal("0.3000000000")
    assert response.latest_evidence_timestamp == datetime(2026, 5, 3, 9, tzinfo=UTC)
    assert reader.calls == ["binding", "rules"]


@pytest.mark.asyncio
async def test_marks_empty_rules_incomplete() -> None:
    response = await _service(_Reader(_binding(), [])).get_client_tax_rule_set(
        portfolio_id="PB_SG_GLOBAL_BAL_001", request=_request()
    )
    assert response is not None
    assert response.supportability.state == "INCOMPLETE"
    assert response.supportability.missing_data_families == ["client_tax_rule_set"]
    assert response.data_quality_status == "MISSING"


@pytest.mark.asyncio
async def test_missing_binding_skips_rule_read() -> None:
    reader = _Reader(None, [_rule()])
    assert (
        await _service(reader).get_client_tax_rule_set(
            portfolio_id="PB_MISSING", request=_request()
        )
        is None
    )
    assert reader.calls == ["binding"]


@pytest.mark.asyncio
async def test_snapshot_identity_is_stable() -> None:
    service = _service(_Reader(_binding(), [_rule()]))
    first = await service.get_client_tax_rule_set(
        portfolio_id="PB_SG_GLOBAL_BAL_001", request=_request()
    )
    second = await service.get_client_tax_rule_set(
        portfolio_id="PB_SG_GLOBAL_BAL_001", request=_request()
    )
    assert first is not None and second is not None
    assert first.snapshot_id == second.snapshot_id
