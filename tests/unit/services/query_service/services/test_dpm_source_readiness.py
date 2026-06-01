from datetime import date
from types import SimpleNamespace

from src.services.query_service.app.dtos.reference_integration_dto import (
    DpmSourceReadinessRequest,
)
from src.services.query_service.app.services.dpm_source_readiness import (
    build_dpm_source_readiness_response,
    dpm_eligibility_request,
    dpm_mandate_binding_request,
    dpm_market_data_coverage_request,
    dpm_model_targets_request,
    dpm_source_evaluated_instrument_ids,
    dpm_source_family_readiness,
    dpm_source_readiness_supportability,
    dpm_tax_lot_window_request,
    eligibility_source_family_readiness,
    mandate_source_family_readiness,
    market_data_source_family_readiness,
    model_targets_source_family_readiness,
    tax_lots_source_family_readiness,
    unavailable_dpm_source_family,
)


def test_unavailable_dpm_source_family_sets_governed_defaults() -> None:
    family = unavailable_dpm_source_family(
        family="model_targets",
        product_name="DpmModelPortfolioTarget",
        reason="MODEL_PORTFOLIO_ID_UNAVAILABLE",
        missing_items=["model_portfolio_id"],
    )

    assert family.family == "model_targets"
    assert family.product_name == "DpmModelPortfolioTarget"
    assert family.state == "UNAVAILABLE"
    assert family.reason == "MODEL_PORTFOLIO_ID_UNAVAILABLE"
    assert family.missing_items == ["model_portfolio_id"]
    assert family.stale_items == []
    assert family.evidence_count == 0


def test_dpm_source_readiness_supportability_prioritizes_worst_family_state() -> None:
    supportability = dpm_source_readiness_supportability(
        [
            dpm_source_family_readiness(
                family="mandate",
                product_name="DiscretionaryMandateBinding",
                state="READY",
                reason="MANDATE_BINDING_READY",
                evidence_count=1,
            ),
            dpm_source_family_readiness(
                family="market_data",
                product_name="MarketDataCoverageWindow",
                state="DEGRADED",
                reason="MARKET_DATA_STALE",
                stale_items=["EQ_US_AAPL"],
                evidence_count=2,
            ),
            unavailable_dpm_source_family(
                family="tax_lots",
                product_name="PortfolioTaxLotWindow",
                reason="PORTFOLIO_TAX_LOTS_UNAVAILABLE",
                missing_items=["PB_SG_GLOBAL_BAL_001"],
            ),
        ]
    )

    assert supportability.state == "UNAVAILABLE"
    assert supportability.reason == "DPM_SOURCE_READINESS_UNAVAILABLE"
    assert supportability.ready_family_count == 1
    assert supportability.degraded_family_count == 1
    assert supportability.incomplete_family_count == 0
    assert supportability.unavailable_family_count == 1


def test_dpm_source_readiness_supportability_returns_ready_when_all_families_ready() -> None:
    supportability = dpm_source_readiness_supportability(
        [
            dpm_source_family_readiness(
                family="mandate",
                product_name="DiscretionaryMandateBinding",
                state="READY",
                reason="MANDATE_BINDING_READY",
                evidence_count=1,
            ),
            dpm_source_family_readiness(
                family="eligibility",
                product_name="InstrumentEligibilityProfile",
                state="READY",
                reason="INSTRUMENT_ELIGIBILITY_READY",
                evidence_count=4,
            ),
        ]
    )

    assert supportability.state == "READY"
    assert supportability.reason == "DPM_SOURCE_READINESS_READY"
    assert supportability.ready_family_count == 2


def test_dpm_source_family_mappers_preserve_source_supportability() -> None:
    mandate = mandate_source_family_readiness(
        SimpleNamespace(
            supportability=SimpleNamespace(
                state="READY",
                reason="MANDATE_READY",
                missing_data_families=["policy_pack"],
            )
        )
    )
    model_targets = model_targets_source_family_readiness(
        SimpleNamespace(
            supportability=SimpleNamespace(
                state="DEGRADED",
                reason="MODEL_TARGETS_DEGRADED",
                target_count=7,
            )
        )
    )
    eligibility = eligibility_source_family_readiness(
        SimpleNamespace(
            supportability=SimpleNamespace(
                state="INCOMPLETE",
                reason="ELIGIBILITY_MISSING",
                missing_security_ids=["SEC_MISSING"],
                resolved_count=3,
            )
        )
    )
    tax_lots = tax_lots_source_family_readiness(
        SimpleNamespace(
            supportability=SimpleNamespace(
                state="READY",
                reason="TAX_LOTS_READY",
                missing_security_ids=[],
                returned_lot_count=11,
            )
        )
    )

    assert mandate.family == "mandate"
    assert mandate.product_name == "DiscretionaryMandateBinding"
    assert mandate.missing_items == ["policy_pack"]
    assert mandate.evidence_count == 1
    assert model_targets.family == "model_targets"
    assert model_targets.evidence_count == 7
    assert eligibility.family == "eligibility"
    assert eligibility.missing_items == ["SEC_MISSING"]
    assert eligibility.evidence_count == 3
    assert tax_lots.family == "tax_lots"
    assert tax_lots.evidence_count == 11


def test_market_data_source_family_mapper_combines_missing_and_stale_scope() -> None:
    family = market_data_source_family_readiness(
        SimpleNamespace(
            supportability=SimpleNamespace(
                state="DEGRADED",
                reason="MARKET_DATA_STALE",
                missing_instrument_ids=["SEC_MISSING"],
                missing_currency_pairs=["USD/SGD"],
                stale_instrument_ids=["SEC_STALE"],
                stale_currency_pairs=["EUR/USD"],
                resolved_price_count=5,
                resolved_fx_count=2,
            )
        )
    )

    assert family.family == "market_data"
    assert family.product_name == "MarketDataCoverageWindow"
    assert family.state == "DEGRADED"
    assert family.reason == "MARKET_DATA_STALE"
    assert family.missing_items == ["SEC_MISSING", "USD/SGD"]
    assert family.stale_items == ["SEC_STALE", "EUR/USD"]
    assert family.evidence_count == 7


def test_dpm_source_evaluated_instrument_ids_deduplicates_and_sorts_scope() -> None:
    assert dpm_source_evaluated_instrument_ids(
        request_instrument_ids=["SEC_Z", "SEC_A"],
        target_instrument_ids=["SEC_A", "SEC_B"],
    ) == ["SEC_A", "SEC_B", "SEC_Z"]


def test_dpm_source_readiness_request_builders_preserve_read_scope_policy() -> None:
    request = DpmSourceReadinessRequest(
        as_of_date=date(2026, 4, 10),
        instrument_ids=["EQ_US_AAPL"],
        mandate_id="MANDATE_001",
        model_portfolio_id="MODEL_BALANCED",
        currency_pairs=[{"from_currency": "USD", "to_currency": "SGD"}],
        valuation_currency="SGD",
        max_staleness_days=3,
        tenant_id="TENANT_SG",
    )

    mandate_request = dpm_mandate_binding_request(request)
    model_request = dpm_model_targets_request(request)
    eligibility_request = dpm_eligibility_request(
        request=request,
        instrument_ids=["EQ_US_AAPL", "EQ_US_MSFT"],
    )
    tax_lot_request = dpm_tax_lot_window_request(
        request=request,
        evaluated_instrument_ids=["EQ_US_AAPL", "EQ_US_MSFT"],
    )
    market_data_request = dpm_market_data_coverage_request(
        request=request,
        evaluated_instrument_ids=["EQ_US_AAPL", "EQ_US_MSFT"],
    )

    assert mandate_request.as_of_date == date(2026, 4, 10)
    assert mandate_request.tenant_id == "TENANT_SG"
    assert mandate_request.mandate_id == "MANDATE_001"
    assert mandate_request.include_policy_pack is True
    assert model_request.as_of_date == date(2026, 4, 10)
    assert model_request.include_inactive_targets is False
    assert model_request.tenant_id == "TENANT_SG"
    assert eligibility_request.security_ids == ["EQ_US_AAPL", "EQ_US_MSFT"]
    assert eligibility_request.include_restricted_rationale is False
    assert eligibility_request.tenant_id == "TENANT_SG"
    assert tax_lot_request.security_ids == ["EQ_US_AAPL", "EQ_US_MSFT"]
    assert tax_lot_request.tenant_id == "TENANT_SG"
    assert market_data_request.instrument_ids == ["EQ_US_AAPL", "EQ_US_MSFT"]
    assert len(market_data_request.currency_pairs) == 1
    assert market_data_request.currency_pairs[0].from_currency == "USD"
    assert market_data_request.currency_pairs[0].to_currency == "SGD"
    assert market_data_request.valuation_currency == "SGD"
    assert market_data_request.max_staleness_days == 3
    assert market_data_request.tenant_id == "TENANT_SG"


def test_dpm_tax_lot_request_uses_full_portfolio_scope_when_universe_empty() -> None:
    request = DpmSourceReadinessRequest(
        as_of_date=date(2026, 4, 10),
        tenant_id="TENANT_SG",
    )

    tax_lot_request = dpm_tax_lot_window_request(
        request=request,
        evaluated_instrument_ids=[],
    )

    assert tax_lot_request.security_ids is None
    assert tax_lot_request.tenant_id == "TENANT_SG"


def test_build_dpm_source_readiness_response_sets_runtime_metadata_and_lineage() -> None:
    families = [
        dpm_source_family_readiness(
            family="mandate",
            product_name="DiscretionaryMandateBinding",
            state="READY",
            reason="MANDATE_BINDING_READY",
            evidence_count=1,
        )
    ]

    response = build_dpm_source_readiness_response(
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        request=DpmSourceReadinessRequest(
            as_of_date=date(2026, 4, 10),
            instrument_ids=["EQ_US_AAPL"],
            mandate_id="MANDATE_001",
            model_portfolio_id="MODEL_BALANCED",
        ),
        resolved_mandate_id="MANDATE_001",
        resolved_model_portfolio_id="MODEL_BALANCED",
        evaluated_instrument_ids=["EQ_US_AAPL"],
        families=families,
    )

    assert response.product_name == "DpmSourceReadiness"
    assert response.portfolio_id == "PB_SG_GLOBAL_BAL_001"
    assert response.supportability.state == "READY"
    assert response.data_quality_status == "COMPLETE"
    assert response.lineage == {
        "source_system": "lotus-core",
        "contract_version": "rfc_087_v1",
        "readiness_scope": "dpm_source_family",
    }
