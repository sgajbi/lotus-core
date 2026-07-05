from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class ReferenceDataPayload(Protocol):
    def model_dump(self, *args: Any, **kwargs: Any) -> dict[str, Any]: ...


@dataclass(frozen=True)
class ReferenceDataIngestionCommand:
    command_key: str
    endpoint: str
    entity_type: str
    records_attribute: str
    persist_method_name: str

    def accepted_count(self, payload: ReferenceDataPayload) -> int:
        return len(self._records(payload))

    def request_payload(self, payload: ReferenceDataPayload) -> dict[str, Any]:
        return payload.model_dump(mode="json")

    def records_for_persistence(self, payload: ReferenceDataPayload) -> list[dict[str, Any]]:
        return [record.model_dump() for record in self._records(payload)]

    async def persist(self, service: Any, payload: ReferenceDataPayload) -> None:
        persist_method = getattr(service, self.persist_method_name)
        await persist_method(self.records_for_persistence(payload))

    def _records(self, payload: ReferenceDataPayload) -> Any:
        return getattr(payload, self.records_attribute)


class ReferenceDataIngestionRegistry:
    def __init__(self, commands: list[ReferenceDataIngestionCommand]) -> None:
        self._commands_by_key = {command.command_key: command for command in commands}
        if len(self._commands_by_key) != len(commands):
            raise ValueError("Reference-data ingestion command keys must be unique.")

    def require(self, command_key: str) -> ReferenceDataIngestionCommand:
        try:
            return self._commands_by_key[command_key]
        except KeyError as exc:
            raise KeyError(f"Unknown reference-data ingestion command: {command_key}") from exc

    def all_commands(self) -> tuple[ReferenceDataIngestionCommand, ...]:
        return tuple(self._commands_by_key.values())


REFERENCE_DATA_INGESTION_REGISTRY = ReferenceDataIngestionRegistry(
    [
        ReferenceDataIngestionCommand(
            command_key="benchmark_assignment",
            endpoint="/ingest/benchmark-assignments",
            entity_type="benchmark_assignment",
            records_attribute="benchmark_assignments",
            persist_method_name="upsert_portfolio_benchmark_assignments",
        ),
        ReferenceDataIngestionCommand(
            command_key="model_portfolio",
            endpoint="/ingest/model-portfolios",
            entity_type="model_portfolio",
            records_attribute="model_portfolios",
            persist_method_name="upsert_model_portfolio_definitions",
        ),
        ReferenceDataIngestionCommand(
            command_key="model_portfolio_target",
            endpoint="/ingest/model-portfolio-targets",
            entity_type="model_portfolio_target",
            records_attribute="model_portfolio_targets",
            persist_method_name="upsert_model_portfolio_targets",
        ),
        ReferenceDataIngestionCommand(
            command_key="instrument_eligibility_profile",
            endpoint="/ingest/instrument-eligibility",
            entity_type="instrument_eligibility_profile",
            records_attribute="eligibility_profiles",
            persist_method_name="upsert_instrument_eligibility_profiles",
        ),
        ReferenceDataIngestionCommand(
            command_key="mandate_binding",
            endpoint="/ingest/mandate-bindings",
            entity_type="mandate_binding",
            records_attribute="mandate_bindings",
            persist_method_name="upsert_discretionary_mandate_bindings",
        ),
        ReferenceDataIngestionCommand(
            command_key="client_restriction_profile",
            endpoint="/ingest/client-restriction-profiles",
            entity_type="client_restriction_profile",
            records_attribute="restriction_profiles",
            persist_method_name="upsert_client_restriction_profiles",
        ),
        ReferenceDataIngestionCommand(
            command_key="sustainability_preference_profile",
            endpoint="/ingest/sustainability-preferences",
            entity_type="sustainability_preference_profile",
            records_attribute="sustainability_preferences",
            persist_method_name="upsert_sustainability_preference_profiles",
        ),
        ReferenceDataIngestionCommand(
            command_key="client_tax_profile",
            endpoint="/ingest/client-tax-profiles",
            entity_type="client_tax_profile",
            records_attribute="tax_profiles",
            persist_method_name="upsert_client_tax_profiles",
        ),
        ReferenceDataIngestionCommand(
            command_key="client_tax_rule_set",
            endpoint="/ingest/client-tax-rule-sets",
            entity_type="client_tax_rule_set",
            records_attribute="tax_rule_sets",
            persist_method_name="upsert_client_tax_rule_sets",
        ),
        ReferenceDataIngestionCommand(
            command_key="client_income_needs_schedule",
            endpoint="/ingest/client-income-needs-schedules",
            entity_type="client_income_needs_schedule",
            records_attribute="income_needs_schedules",
            persist_method_name="upsert_client_income_needs_schedules",
        ),
        ReferenceDataIngestionCommand(
            command_key="liquidity_reserve_requirement",
            endpoint="/ingest/liquidity-reserve-requirements",
            entity_type="liquidity_reserve_requirement",
            records_attribute="liquidity_reserve_requirements",
            persist_method_name="upsert_liquidity_reserve_requirements",
        ),
        ReferenceDataIngestionCommand(
            command_key="planned_withdrawal_schedule",
            endpoint="/ingest/planned-withdrawal-schedules",
            entity_type="planned_withdrawal_schedule",
            records_attribute="planned_withdrawal_schedules",
            persist_method_name="upsert_planned_withdrawal_schedules",
        ),
        ReferenceDataIngestionCommand(
            command_key="benchmark_definition",
            endpoint="/ingest/benchmark-definitions",
            entity_type="benchmark_definition",
            records_attribute="benchmark_definitions",
            persist_method_name="upsert_benchmark_definitions",
        ),
        ReferenceDataIngestionCommand(
            command_key="benchmark_composition",
            endpoint="/ingest/benchmark-compositions",
            entity_type="benchmark_composition",
            records_attribute="benchmark_compositions",
            persist_method_name="upsert_benchmark_compositions",
        ),
        ReferenceDataIngestionCommand(
            command_key="index_definition",
            endpoint="/ingest/indices",
            entity_type="index_definition",
            records_attribute="indices",
            persist_method_name="upsert_indices",
        ),
        ReferenceDataIngestionCommand(
            command_key="index_price_series",
            endpoint="/ingest/index-price-series",
            entity_type="index_price_series",
            records_attribute="index_price_series",
            persist_method_name="upsert_index_price_series",
        ),
        ReferenceDataIngestionCommand(
            command_key="index_return_series",
            endpoint="/ingest/index-return-series",
            entity_type="index_return_series",
            records_attribute="index_return_series",
            persist_method_name="upsert_index_return_series",
        ),
        ReferenceDataIngestionCommand(
            command_key="benchmark_return_series",
            endpoint="/ingest/benchmark-return-series",
            entity_type="benchmark_return_series",
            records_attribute="benchmark_return_series",
            persist_method_name="upsert_benchmark_return_series",
        ),
        ReferenceDataIngestionCommand(
            command_key="risk_free_series",
            endpoint="/ingest/risk-free-series",
            entity_type="risk_free_series",
            records_attribute="risk_free_series",
            persist_method_name="upsert_risk_free_series",
        ),
        ReferenceDataIngestionCommand(
            command_key="classification_taxonomy",
            endpoint="/ingest/reference/classification-taxonomy",
            entity_type="classification_taxonomy",
            records_attribute="classification_taxonomy",
            persist_method_name="upsert_classification_taxonomy",
        ),
        ReferenceDataIngestionCommand(
            command_key="cash_account_master",
            endpoint="/ingest/reference/cash-accounts",
            entity_type="cash_account_master",
            records_attribute="cash_accounts",
            persist_method_name="upsert_cash_account_masters",
        ),
        ReferenceDataIngestionCommand(
            command_key="instrument_lookthrough_component",
            endpoint="/ingest/reference/instrument-lookthrough-components",
            entity_type="instrument_lookthrough_component",
            records_attribute="lookthrough_components",
            persist_method_name="upsert_instrument_lookthrough_components",
        ),
    ]
)
