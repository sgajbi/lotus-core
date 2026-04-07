from decimal import Decimal
from types import SimpleNamespace

from src.services.query_service.app.advisory_simulation.allocation_contract import (
    ADVISORY_PROPOSAL_ALLOCATION_DIMENSIONS,
)
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


def test_advisory_simulation_exposes_allocation_lens_metadata_and_views():
    result = execute_advisory_simulation(
        request=_request(),
        request_hash="sha256:allocation-lens",
        idempotency_key=None,
        correlation_id="corr-core-allocation-lens",
        simulation_contract_version="advisory-simulation.v1",
    )

    assert result.allocation_lens.contract_version == "advisory-simulation.v1"
    assert result.allocation_lens.source == "LOTUS_CORE"


def test_noop_advisory_after_reuses_trusted_before_state_for_snapshot_inputs():
    request = ProposalSimulateRequest.model_validate(
        {
            "portfolio_snapshot": {
                "portfolio_id": "pf_core_trust_noop",
                "base_currency": "USD",
                "positions": [
                    {
                        "instrument_id": "EQ_EUR",
                        "quantity": "10",
                        "market_value": {"amount": "120", "currency": "USD"},
                    }
                ],
                "cash_balances": [],
            },
            "market_data_snapshot": {
                "prices": [{"instrument_id": "EQ_EUR", "price": "10", "currency": "EUR"}],
                "fx_rates": [{"pair": "EUR/USD", "rate": "1.5"}],
            },
            "shelf_entries": [
                {
                    "instrument_id": "EQ_EUR",
                    "status": "APPROVED",
                    "asset_class": "EQUITY",
                    "attributes": {
                        "country": "Germany",
                        "product_type": "Equity",
                        "sector": "Technology",
                    },
                }
            ],
            "options": {
                "enable_proposal_simulation": True,
                "valuation_mode": "TRUST_SNAPSHOT",
            },
            "proposed_cash_flows": [],
            "proposed_trades": [],
        }
    )

    result = execute_advisory_simulation(
        request=request,
        request_hash="sha256:trust-noop",
        idempotency_key=None,
        correlation_id="corr-core-trust-noop",
        simulation_contract_version="advisory-simulation.v1",
    )

    assert result.before.total_value.amount == Decimal("120")
    assert result.after_simulated.total_value.amount == Decimal("120")
    assert result.before.model_dump(mode="json") == result.after_simulated.model_dump(mode="json")
    assert tuple(result.allocation_lens.dimensions) == ADVISORY_PROPOSAL_ALLOCATION_DIMENSIONS
    assert [view.dimension for view in result.before.allocation_views] == list(
        ADVISORY_PROPOSAL_ALLOCATION_DIMENSIONS
    )
    assert [view.dimension for view in result.after_simulated.allocation_views] == list(
        ADVISORY_PROPOSAL_ALLOCATION_DIMENSIONS
    )


def test_advisory_simulation_preserves_cash_currency_split_in_allocation_views() -> None:
    request = ProposalSimulateRequest.model_validate(
        {
            "portfolio_snapshot": {
                "portfolio_id": "pf_core_currency_split",
                "base_currency": "USD",
                "positions": [],
                "cash_balances": [
                    {"currency": "USD", "amount": "100"},
                    {"currency": "EUR", "amount": "100"},
                ],
            },
            "market_data_snapshot": {
                "prices": [],
                "fx_rates": [{"pair": "EUR/USD", "rate": "1.2"}],
            },
            "shelf_entries": [],
            "options": {"enable_proposal_simulation": True},
            "proposed_cash_flows": [],
            "proposed_trades": [],
        }
    )

    result = execute_advisory_simulation(
        request=request,
        request_hash="sha256:cash-currency-split",
        idempotency_key=None,
        correlation_id="corr-core-cash-currency-split",
        simulation_contract_version="advisory-simulation.v1",
    )

    currency_view = next(
        view for view in result.before.allocation_views if view.dimension == "currency"
    )
    product_type_view = next(
        view for view in result.before.allocation_views if view.dimension == "product_type"
    )

    assert {bucket.key: bucket.value.amount for bucket in currency_view.buckets} == {
        "EUR": Decimal("120.0"),
        "USD": Decimal("100"),
    }
    assert {bucket.key: bucket.value.amount for bucket in product_type_view.buckets} == {
        "Cash": Decimal("220.0")
    }


def test_advisory_simulation_uses_reporting_labels_for_asset_class_allocation_views() -> None:
    request = ProposalSimulateRequest.model_validate(
        {
            "portfolio_snapshot": {
                "portfolio_id": "pf_core_asset_class_labels",
                "base_currency": "USD",
                "positions": [{"instrument_id": "EQ_1", "quantity": "1"}],
                "cash_balances": [{"currency": "USD", "amount": "50"}],
            },
            "market_data_snapshot": {
                "prices": [{"instrument_id": "EQ_1", "price": "100", "currency": "USD"}],
                "fx_rates": [],
            },
            "shelf_entries": [
                {"instrument_id": "EQ_1", "status": "APPROVED", "asset_class": "EQUITY"}
            ],
            "options": {"enable_proposal_simulation": True},
            "proposed_cash_flows": [],
            "proposed_trades": [],
        }
    )

    result = execute_advisory_simulation(
        request=request,
        request_hash="sha256:asset-class-view-labels",
        idempotency_key=None,
        correlation_id="corr-core-asset-class-view-labels",
        simulation_contract_version="advisory-simulation.v1",
    )

    asset_class_view = next(
        view for view in result.before.allocation_views if view.dimension == "asset_class"
    )

    assert [bucket.key for bucket in asset_class_view.buckets] == ["Cash", "Equity"]
    assert asset_class_view.buckets[0].weight == Decimal("0.3333333333333333333333333333")
