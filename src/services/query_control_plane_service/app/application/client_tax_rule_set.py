"""Application use case for effective client tax-rule evidence."""

from typing import Literal

from portfolio_common.request_fingerprints import request_fingerprint
from portfolio_common.runtime_providers import Clock
from portfolio_common.source_data_product_metadata import source_data_product_runtime_metadata

from ..contracts.client_tax_rule_set import (
    ClientTaxRuleSetEntry,
    ClientTaxRuleSetRequest,
    ClientTaxRuleSetResponse,
    ClientTaxRuleSetSupportability,
)
from ..domain.client_tax_rule_set import ClientTaxRuleSourceRecord
from ..domain.effective_mandate import EffectiveMandateBinding
from ..ports.client_tax_rule_set import ClientTaxRuleSetSourceReader
from ..ports.effective_mandate import EffectiveMandateReader
from .source_evidence import latest_evidence_timestamp


class ClientTaxRuleSetService:
    """Resolve one deterministic tax-rule source product."""

    def __init__(
        self,
        *,
        mandate_reader: EffectiveMandateReader,
        reader: ClientTaxRuleSetSourceReader,
        clock: Clock,
    ) -> None:
        self._mandate_reader = mandate_reader
        self._reader = reader
        self._clock = clock

    async def get_client_tax_rule_set(
        self, *, portfolio_id: str, request: ClientTaxRuleSetRequest
    ) -> ClientTaxRuleSetResponse | None:
        binding = await self._mandate_reader.resolve(
            portfolio_id=portfolio_id, as_of_date=request.as_of_date, mandate_id=request.mandate_id
        )
        if binding is None:
            return None
        rules = await self._reader.list_rules(
            portfolio_id=portfolio_id,
            client_id=binding.client_id,
            as_of_date=request.as_of_date,
            mandate_id=binding.mandate_id,
            include_inactive_rules=request.include_inactive_rules,
        )
        return self._build_response(
            portfolio_id=portfolio_id, binding=binding, request=request, rules=rules
        )

    def _build_response(
        self,
        *,
        portfolio_id: str,
        binding: EffectiveMandateBinding,
        request: ClientTaxRuleSetRequest,
        rules: list[ClientTaxRuleSourceRecord],
    ) -> ClientTaxRuleSetResponse:
        entries = [_entry(record) for record in rules]
        state: Literal["READY", "INCOMPLETE", "UNAVAILABLE"] = "READY"
        reason = "CLIENT_TAX_RULE_SET_READY"
        missing: list[str] = []
        if not rules:
            state = "INCOMPLETE"
            reason = "CLIENT_TAX_RULE_SET_EMPTY"
            missing.append("client_tax_rule_set")
        return ClientTaxRuleSetResponse(
            portfolio_id=portfolio_id,
            client_id=binding.client_id,
            mandate_id=binding.mandate_id,
            rules=entries,
            supportability=ClientTaxRuleSetSupportability(
                state=state, reason=reason, rule_count=len(entries), missing_data_families=missing
            ),
            lineage={
                "source_system": "lotus-core-query-service",
                "source_table": "client_tax_rule_sets,portfolio_mandate_bindings",
                "contract_version": "rfc_042_client_tax_rule_set_v1",
            },
            **source_data_product_runtime_metadata(
                as_of_date=request.as_of_date,
                generated_at=self._clock.utc_now(),
                tenant_id=request.tenant_id,
                data_quality_status=("ACCEPTED" if rules else "MISSING"),
                latest_evidence_timestamp=latest_evidence_timestamp([binding], rules),
                source_batch_fingerprint=None,
                snapshot_id="client_tax_rule_set:"
                + request_fingerprint(
                    {
                        "portfolio_id": portfolio_id,
                        "client_id": binding.client_id,
                        "as_of_date": request.as_of_date.isoformat(),
                    }
                ),
            ),
        )


def _entry(record: ClientTaxRuleSourceRecord) -> ClientTaxRuleSetEntry:
    return ClientTaxRuleSetEntry(
        rule_set_id=record.rule_set_id,
        tax_year=record.tax_year,
        jurisdiction_code=record.jurisdiction_code,
        rule_code=record.rule_code,
        rule_category=record.rule_category,
        rule_status=record.rule_status,
        rule_source=record.rule_source,
        applies_to_asset_classes=list(record.applies_to_asset_classes),
        applies_to_security_ids=list(record.applies_to_security_ids),
        applies_to_income_types=list(record.applies_to_income_types),
        rate=record.rate,
        threshold_amount=record.threshold_amount,
        threshold_currency=record.threshold_currency,
        effective_from=record.effective_from,
        effective_to=record.effective_to,
        rule_version=record.rule_version,
        source_record_id=record.source_record_id,
    )
