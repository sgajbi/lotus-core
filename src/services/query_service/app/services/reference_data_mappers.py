from __future__ import annotations

from decimal import Decimal
from typing import Any

from ..dtos.reference_integration_dto import (
    BenchmarkComponentResponse,
    BenchmarkDefinitionResponse,
    ClientIncomeNeedsScheduleEntry,
    ClientTaxProfileEntry,
    ClientTaxRuleSetEntry,
    IndexDefinitionResponse,
    LiquidityReserveRequirementEntry,
    PlannedWithdrawalScheduleEntry,
)


def _as_decimal(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def benchmark_component_response(row: Any) -> BenchmarkComponentResponse:
    return BenchmarkComponentResponse(
        index_id=row.index_id,
        composition_weight=_as_decimal(row.composition_weight),
        composition_effective_from=row.composition_effective_from,
        composition_effective_to=row.composition_effective_to,
        rebalance_event_id=row.rebalance_event_id,
    )


def benchmark_definition_response(
    row: Any,
    *,
    components: list[Any] | None = None,
) -> BenchmarkDefinitionResponse:
    return BenchmarkDefinitionResponse(
        benchmark_id=row.benchmark_id,
        benchmark_name=row.benchmark_name,
        benchmark_type=row.benchmark_type,
        benchmark_currency=row.benchmark_currency,
        return_convention=row.return_convention,
        benchmark_status=row.benchmark_status,
        benchmark_family=row.benchmark_family,
        benchmark_provider=row.benchmark_provider,
        rebalance_frequency=row.rebalance_frequency,
        classification_set_id=row.classification_set_id,
        classification_labels=dict(row.classification_labels or {}),
        effective_from=row.effective_from,
        effective_to=row.effective_to,
        quality_status=row.quality_status,
        source_timestamp=row.source_timestamp,
        source_vendor=row.source_vendor,
        source_record_id=row.source_record_id,
        components=[benchmark_component_response(component) for component in components or []],
    )


def index_definition_response(row: Any) -> IndexDefinitionResponse:
    return IndexDefinitionResponse(
        index_id=row.index_id,
        index_name=row.index_name,
        index_currency=row.index_currency,
        index_type=row.index_type,
        index_status=row.index_status,
        index_provider=row.index_provider,
        index_market=row.index_market,
        classification_set_id=row.classification_set_id,
        classification_labels=dict(row.classification_labels or {}),
        effective_from=row.effective_from,
        effective_to=row.effective_to,
        quality_status=row.quality_status,
        source_timestamp=row.source_timestamp,
        source_vendor=row.source_vendor,
        source_record_id=row.source_record_id,
    )


def client_tax_profile_entry(row: Any) -> ClientTaxProfileEntry:
    return ClientTaxProfileEntry(
        tax_profile_id=row.tax_profile_id,
        tax_residency_country=row.tax_residency_country,
        booking_tax_jurisdiction=row.booking_tax_jurisdiction,
        tax_status=row.tax_status,
        profile_status=row.profile_status,
        withholding_tax_rate=(
            _as_decimal(row.withholding_tax_rate) if row.withholding_tax_rate is not None else None
        ),
        capital_gains_tax_applicable=bool(row.capital_gains_tax_applicable),
        income_tax_applicable=bool(row.income_tax_applicable),
        treaty_codes=_string_list(row.treaty_codes),
        eligible_account_types=_string_list(row.eligible_account_types),
        effective_from=row.effective_from,
        effective_to=row.effective_to,
        profile_version=int(row.profile_version),
        source_record_id=row.source_record_id,
    )


def client_tax_rule_set_entry(row: Any) -> ClientTaxRuleSetEntry:
    return ClientTaxRuleSetEntry(
        rule_set_id=row.rule_set_id,
        tax_year=int(row.tax_year),
        jurisdiction_code=row.jurisdiction_code,
        rule_code=row.rule_code,
        rule_category=row.rule_category,
        rule_status=row.rule_status,
        rule_source=row.rule_source,
        applies_to_asset_classes=_string_list(row.applies_to_asset_classes),
        applies_to_security_ids=_string_list(row.applies_to_security_ids),
        applies_to_income_types=_string_list(row.applies_to_income_types),
        rate=_as_decimal(row.rate) if row.rate is not None else None,
        threshold_amount=(
            _as_decimal(row.threshold_amount) if row.threshold_amount is not None else None
        ),
        threshold_currency=row.threshold_currency,
        effective_from=row.effective_from,
        effective_to=row.effective_to,
        rule_version=int(row.rule_version),
        source_record_id=row.source_record_id,
    )


def client_income_needs_schedule_entry(row: Any) -> ClientIncomeNeedsScheduleEntry:
    return ClientIncomeNeedsScheduleEntry(
        schedule_id=row.schedule_id,
        need_type=row.need_type,
        need_status=row.need_status,
        amount=_as_decimal(row.amount),
        currency=row.currency,
        frequency=row.frequency,
        start_date=row.start_date,
        end_date=row.end_date,
        priority=int(row.priority),
        funding_policy=row.funding_policy,
        source_record_id=row.source_record_id,
    )


def liquidity_reserve_requirement_entry(row: Any) -> LiquidityReserveRequirementEntry:
    return LiquidityReserveRequirementEntry(
        reserve_requirement_id=row.reserve_requirement_id,
        reserve_type=row.reserve_type,
        reserve_status=row.reserve_status,
        required_amount=_as_decimal(row.required_amount),
        currency=row.currency,
        horizon_days=int(row.horizon_days),
        priority=int(row.priority),
        policy_source=row.policy_source,
        effective_from=row.effective_from,
        effective_to=row.effective_to,
        requirement_version=int(row.requirement_version),
        source_record_id=row.source_record_id,
    )


def planned_withdrawal_schedule_entry(row: Any) -> PlannedWithdrawalScheduleEntry:
    return PlannedWithdrawalScheduleEntry(
        withdrawal_schedule_id=row.withdrawal_schedule_id,
        withdrawal_type=row.withdrawal_type,
        withdrawal_status=row.withdrawal_status,
        amount=_as_decimal(row.amount),
        currency=row.currency,
        scheduled_date=row.scheduled_date,
        recurrence_frequency=row.recurrence_frequency,
        purpose_code=row.purpose_code,
        source_record_id=row.source_record_id,
    )
