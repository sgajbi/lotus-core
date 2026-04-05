from src.services.query_service.app.advisory_simulation.advisory.funding import (
    funding_priority_currencies,
)


class _Options:
    def __init__(self, fx_funding_source_currency: str):
        self.fx_funding_source_currency = fx_funding_source_currency


def test_funding_priority_base_only_prefers_base_when_different_target_currency():
    result = funding_priority_currencies(
        options=_Options("BASE_ONLY"),
        base_currency="USD",
        target_currency="EUR",
        cash_ledger={"USD": 1000, "EUR": 0, "SGD": 10},
    )
    assert result == ["USD"]

