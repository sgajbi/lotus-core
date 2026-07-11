"""Source-read boundary for effective client tax-rule resolution."""

from datetime import date
from typing import Protocol

from ..domain.client_tax_rule_set import ClientTaxRuleSourceRecord


class ClientTaxRuleSetSourceReader(Protocol):
    """Read tax-rule evidence without exposing persistence models."""

    async def list_rules(
        self,
        *,
        portfolio_id: str,
        client_id: str,
        as_of_date: date,
        mandate_id: str | None,
        include_inactive_rules: bool,
    ) -> list[ClientTaxRuleSourceRecord]: ...
