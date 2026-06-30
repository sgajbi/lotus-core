from __future__ import annotations

from typing import Any, Literal

from ..dtos.reference_integration_dto import (
    ClientTaxRuleSetRequest,
    ClientTaxRuleSetResponse,
    ClientTaxRuleSetSupportability,
)
from ..dtos.source_data_product_identity import source_data_product_runtime_metadata
from .reference_data_helpers import latest_reference_evidence_timestamp
from .reference_data_mappers import client_tax_rule_set_entry
from .request_fingerprint import request_fingerprint


async def resolve_client_tax_rule_set_response(
    *,
    repository: Any,
    portfolio_id: str,
    request: ClientTaxRuleSetRequest,
) -> ClientTaxRuleSetResponse | None:
    binding = await repository.resolve_discretionary_mandate_binding(
        portfolio_id=portfolio_id,
        as_of_date=request.as_of_date,
        mandate_id=request.mandate_id,
    )
    if binding is None:
        return None

    rows = await repository.list_client_tax_rule_sets(
        portfolio_id=portfolio_id,
        client_id=binding.client_id,
        as_of_date=request.as_of_date,
        mandate_id=binding.mandate_id,
        include_inactive_rules=request.include_inactive_rules,
    )
    return build_client_tax_rule_set_response(
        portfolio_id=portfolio_id,
        binding=binding,
        request=request,
        rows=rows,
    )


def build_client_tax_rule_set_response(
    *,
    portfolio_id: str,
    binding: Any,
    request: ClientTaxRuleSetRequest,
    rows: list[Any],
) -> ClientTaxRuleSetResponse:
    entries = [client_tax_rule_set_entry(row) for row in rows]
    supportability_state: Literal["READY", "INCOMPLETE", "UNAVAILABLE"] = "READY"
    supportability_reason = "CLIENT_TAX_RULE_SET_READY"
    missing_data_families: list[str] = []
    if not rows:
        supportability_state = "INCOMPLETE"
        supportability_reason = "CLIENT_TAX_RULE_SET_EMPTY"
        missing_data_families.append("client_tax_rule_set")

    return ClientTaxRuleSetResponse(
        portfolio_id=portfolio_id,
        client_id=binding.client_id,
        mandate_id=binding.mandate_id,
        rules=entries,
        supportability=ClientTaxRuleSetSupportability(
            state=supportability_state,
            reason=supportability_reason,
            rule_count=len(entries),
            missing_data_families=missing_data_families,
        ),
        lineage={
            "source_system": "lotus-core-query-service",
            "source_table": "client_tax_rule_sets,portfolio_mandate_bindings",
            "contract_version": "rfc_042_client_tax_rule_set_v1",
        },
        **source_data_product_runtime_metadata(
            as_of_date=request.as_of_date,
            tenant_id=request.tenant_id,
            data_quality_status=("ACCEPTED" if rows else "MISSING"),
            latest_evidence_timestamp=latest_reference_evidence_timestamp([binding], rows),
            source_batch_fingerprint=None,
            snapshot_id=(
                "client_tax_rule_set:"
                + request_fingerprint(
                    {
                        "portfolio_id": portfolio_id,
                        "client_id": binding.client_id,
                        "as_of_date": request.as_of_date.isoformat(),
                    }
                )
            ),
        ),
    )
