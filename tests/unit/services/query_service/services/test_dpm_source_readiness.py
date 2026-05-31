from src.services.query_service.app.services.dpm_source_readiness import (
    dpm_source_family_readiness,
    dpm_source_readiness_supportability,
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
