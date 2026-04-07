from decimal import Decimal
from types import SimpleNamespace

from src.services.query_service.app.advisory_simulation.models import ProposalSimulateRequest
from src.services.query_service.app.services.advisory_simulation_service import (
    execute_advisory_simulation,
)
from src.services.query_service.app.services.allocation_calculator import (
    AllocationInputRow,
    calculate_allocation_views,
)


def _request() -> ProposalSimulateRequest:
    return ProposalSimulateRequest.model_validate(
        {
            "portfolio_snapshot": {
                "portfolio_id": "pf_core_adv_1",
                "base_currency": "USD",
                "positions": [],
                "cash_balances": [{"currency": "USD", "amount": "1000"}],
            },
            "market_data_snapshot": {
                "prices": [{"instrument_id": "EQ_1", "price": "100", "currency": "USD"}],
                "fx_rates": [],
            },
            "shelf_entries": [{"instrument_id": "EQ_1", "status": "APPROVED"}],
            "options": {"enable_proposal_simulation": True},
            "proposed_cash_flows": [{"currency": "USD", "amount": "200"}],
            "proposed_trades": [{"side": "BUY", "instrument_id": "EQ_1", "quantity": "2"}],
        }
    )


def test_execute_advisory_simulation_preserves_supplied_lineage_inputs():
    result = execute_advisory_simulation(
        request=_request(),
        request_hash="sha256:test-hash",
        idempotency_key="idem-core-001",
        correlation_id="corr-core-001",
        simulation_contract_version="advisory-simulation.v1",
    )

    assert result.status == "READY"
    assert result.correlation_id == "corr-core-001"
    assert result.lineage.request_hash == "sha256:test-hash"
    assert result.lineage.idempotency_key == "idem-core-001"
    assert result.lineage.simulation_contract_version == "advisory-simulation.v1"
    assert [intent.intent_type for intent in result.intents] == [
        "CASH_FLOW",
        "SECURITY_TRADE",
    ]


def test_execute_advisory_simulation_computes_request_hash_when_missing():
    result = execute_advisory_simulation(
        request=_request(),
        request_hash=None,
        idempotency_key=None,
        correlation_id="corr-core-002",
        simulation_contract_version="advisory-simulation.v1",
    )

    assert result.lineage.request_hash.startswith("sha256:")
    assert result.correlation_id == "corr-core-002"
    assert result.lineage.simulation_contract_version == "advisory-simulation.v1"


def test_noop_advisory_before_allocation_matches_shared_live_calculator():
    request = ProposalSimulateRequest.model_validate(
        {
            "portfolio_snapshot": {
                "portfolio_id": "pf_core_alloc_noop",
                "base_currency": "USD",
                "positions": [
                    {"instrument_id": "EQ_1", "quantity": "2"},
                    {"instrument_id": "BOND_1", "quantity": "1"},
                ],
                "cash_balances": [{"currency": "USD", "amount": "50"}],
            },
            "market_data_snapshot": {
                "prices": [
                    {"instrument_id": "EQ_1", "price": "100", "currency": "USD"},
                    {"instrument_id": "BOND_1", "price": "200", "currency": "USD"},
                ],
                "fx_rates": [],
            },
            "shelf_entries": [
                {"instrument_id": "EQ_1", "status": "APPROVED", "asset_class": "EQUITY"},
                {
                    "instrument_id": "BOND_1",
                    "status": "APPROVED",
                    "asset_class": "FIXED_INCOME",
                },
            ],
            "options": {"enable_proposal_simulation": True},
            "proposed_cash_flows": [],
            "proposed_trades": [],
        }
    )

    result = execute_advisory_simulation(
        request=request,
        request_hash="sha256:no-op-allocation",
        idempotency_key=None,
        correlation_id="corr-core-noop-allocation",
        simulation_contract_version="advisory-simulation.v1",
    )
    expected_view = calculate_allocation_views(
        rows=[
            AllocationInputRow(
                instrument=SimpleNamespace(asset_class="EQUITY"),
                snapshot=SimpleNamespace(security_id="EQ_1"),
                market_value_reporting_currency=Decimal("200"),
            ),
            AllocationInputRow(
                instrument=SimpleNamespace(asset_class="FIXED_INCOME"),
                snapshot=SimpleNamespace(security_id="BOND_1"),
                market_value_reporting_currency=Decimal("200"),
            ),
            AllocationInputRow(
                instrument=SimpleNamespace(asset_class="CASH"),
                snapshot=SimpleNamespace(security_id="CASH_USD"),
                market_value_reporting_currency=Decimal("50"),
            ),
        ],
        dimensions=["asset_class"],
    ).views[0]

    before = {
        metric.key: (metric.value.amount, metric.weight)
        for metric in result.before.allocation_by_asset_class
    }
    after = {
        metric.key: (metric.value.amount, metric.weight)
        for metric in result.after_simulated.allocation_by_asset_class
    }
    expected = {
        bucket.dimension_value: (bucket.market_value_reporting_currency, bucket.weight)
        for bucket in expected_view.buckets
    }

    assert before == expected
    assert after == expected
