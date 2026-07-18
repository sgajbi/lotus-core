from datetime import UTC, date, datetime
from decimal import Decimal

from portfolio_common.logging_utils import correlation_id_var
from portfolio_common.reconciliation_quality import PARTIAL
from portfolio_common.source_data_product_metadata import (
    SourceDataDegradationDetail,
    SourceDataDegradationSummary,
    source_data_product_runtime_metadata,
)

from src.services.query_control_plane_service.app.application.dpm_source_readiness import (
    instrument_eligibility,
    market_data_coverage,
)
from src.services.query_control_plane_service.app.contracts.instrument_eligibility import (
    InstrumentEligibilityBulkRequest,
)
from src.services.query_control_plane_service.app.contracts.market_data_coverage import (
    MarketDataCoverageRequest,
    MarketDataCurrencyPair,
)
from src.services.query_control_plane_service.app.contracts.operations import (
    ReconciliationFindingListResponse,
    ReconciliationFindingRecord,
)
from src.services.query_control_plane_service.app.domain.dpm_source_readiness import (
    InstrumentEligibilityEvidence,
    MarketPriceEvidence,
)
from src.services.query_service.app.dtos.cashflow_projection_dto import (
    CashflowProjectionResponse,
)
from src.services.query_service.app.dtos.position_dto import Position
from src.services.query_service.app.dtos.valuation_dto import ValuationData
from src.services.query_service.app.services.position_holdings import (
    portfolio_positions_response_data,
)
from src.services.query_service.app.services.transaction_records import (
    paginated_transaction_ledger_response,
)

CORRELATION_ID = "corr-degraded-source-contract"


def test_positions_contract_exposes_field_level_fallback_provenance() -> None:
    response = _with_correlation(
        lambda: portfolio_positions_response_data(
            portfolio_id="PB1",
            positions=[
                Position(
                    security_id="HIST_A",
                    quantity=Decimal("20"),
                    cost_basis=Decimal("200"),
                    position_date=date(2026, 4, 10),
                    instrument_name="History A",
                    reprocessing_status="CURRENT",
                    valuation=ValuationData(
                        market_price=Decimal("11"),
                        market_value=Decimal("220"),
                    ),
                )
            ],
            response_as_of_date=date(2026, 4, 10),
            data_quality_status=PARTIAL,
            latest_evidence_timestamp=datetime(2026, 4, 10, 9, tzinfo=UTC),
            degradation=SourceDataDegradationSummary(
                status="PARTIAL",
                reason_codes=["HOLDINGS_VALUATION_FALLBACK"],
                details=[
                    SourceDataDegradationDetail(
                        section="positions",
                        record_key="security_id:HIST_A",
                        affected_fields=["valuation.market_price", "valuation.market_value"],
                        source_kind="FALLBACK",
                        source_product_name="HoldingsAsOf",
                        source_as_of_date=date(2026, 4, 10),
                        latest_evidence_timestamp=datetime(2026, 4, 10, 9, tzinfo=UTC),
                        freshness_status="PARTIAL",
                        reason_code="HOLDINGS_VALUATION_FALLBACK",
                    )
                ],
            ),
        )
    )

    assert response.product_name == "HoldingsAsOf"
    assert response.data_quality_status == PARTIAL
    assert response.degradation.status == "PARTIAL"
    assert response.degradation.details[0].source_kind == "FALLBACK"
    assert response.source_batch_fingerprint == response.content_hash
    assert response.correlation_id == CORRELATION_ID


def test_transactions_contract_reports_partial_page_and_missing_reference() -> None:
    response = _with_correlation(
        lambda: paginated_transaction_ledger_response(
            portfolio_id="PB1",
            reporting_currency="SGD",
            total_count=3,
            skip=0,
            limit=1,
            transactions=[],
            effective_as_of_date=date(2026, 4, 10),
            end_date=None,
            latest_evidence_timestamp=datetime(2026, 4, 10, 8, tzinfo=UTC),
            missing_instrument_security_ids=["UNKNOWN_SEC"],
        )
    )

    assert response.product_name == "TransactionLedgerWindow"
    assert response.data_quality_status == PARTIAL
    assert "TRANSACTION_LEDGER_PAGE_PARTIAL" in response.reason_codes
    assert "TRANSACTION_LEDGER_INSTRUMENT_REFERENCE_MISSING" in response.reason_codes
    assert response.missing_instrument_security_ids == ["UNKNOWN_SEC"]
    assert response.freshness_status == "CURRENT"
    assert response.correlation_id == CORRELATION_ID


def test_market_data_contract_reports_stale_and_missing_observations() -> None:
    request = MarketDataCoverageRequest(
        as_of_date=date(2026, 4, 10),
        instrument_ids=["EQ_US_AAPL", "FI_US_TREASURY_10Y"],
        currency_pairs=[MarketDataCurrencyPair(from_currency="USD", to_currency="SGD")],
        max_staleness_days=5,
    )
    response = _with_correlation(
        lambda: market_data_coverage.build_market_data_coverage_response(
            request=request,
            scope=market_data_coverage.market_data_coverage_scope(request),
            prices=[
                MarketPriceEvidence(
                    security_id="EQ_US_AAPL",
                    price_date=date(2026, 4, 1),
                    price=Decimal("187.12"),
                    currency="USD",
                    created_at=datetime(2026, 4, 1, 8, tzinfo=UTC),
                    updated_at=datetime(2026, 4, 1, 8, tzinfo=UTC),
                )
            ],
            fx_rates=[],
            generated_at=datetime(2026, 4, 10, 10, tzinfo=UTC),
        )
    )

    assert response.product_name == "MarketDataCoverageWindow"
    assert response.data_quality_status == PARTIAL
    assert response.supportability.state == "INCOMPLETE"
    assert response.supportability.reason == "MARKET_DATA_MISSING"
    assert response.supportability.stale_instrument_ids == ["EQ_US_AAPL"]
    assert response.supportability.missing_instrument_ids == ["FI_US_TREASURY_10Y"]
    assert response.supportability.missing_currency_pairs == ["USD/SGD"]
    assert response.correlation_id == CORRELATION_ID


def test_instrument_reference_contract_reports_missing_profiles() -> None:
    response = _with_correlation(
        lambda: instrument_eligibility.build_instrument_eligibility_response(
            request=InstrumentEligibilityBulkRequest(
                security_ids=["UNKNOWN_SEC", "EQ_US_AAPL"],
                as_of_date=date(2026, 4, 10),
            ),
            evidence=[
                InstrumentEligibilityEvidence(
                    security_id="EQ_US_AAPL",
                    eligibility_status="APPROVED",
                    product_shelf_status="APPROVED",
                    buy_allowed=True,
                    sell_allowed=True,
                    restriction_reason_codes=(),
                    settlement_days=2,
                    settlement_calendar_id="NYSE",
                    liquidity_tier="T1",
                    issuer_id="ISSUER_AAPL",
                    issuer_name="Apple Inc.",
                    ultimate_parent_issuer_id="ISSUER_AAPL",
                    ultimate_parent_issuer_name="Apple Inc.",
                    asset_class="equity",
                    country_of_risk="US",
                    effective_from=date(2026, 1, 1),
                    effective_to=None,
                    eligibility_version=1,
                    source_system="eligibility_master",
                    quality_status="accepted",
                    source_record_id="eligibility:EQ_US_AAPL",
                    observed_at=datetime(2026, 4, 10, 9, tzinfo=UTC),
                    created_at=datetime(2026, 4, 10, 9, tzinfo=UTC),
                    updated_at=datetime(2026, 4, 10, 9, tzinfo=UTC),
                )
            ],
            generated_at=datetime(2026, 4, 10, 10, tzinfo=UTC),
        )
    )

    assert response.product_name == "InstrumentEligibilityProfile"
    assert response.data_quality_status == PARTIAL
    assert response.supportability.state == "INCOMPLETE"
    assert response.supportability.missing_security_ids == ["UNKNOWN_SEC"]
    assert response.records[0].found is False
    assert response.correlation_id == CORRELATION_ID


def test_populated_cashflow_contract_fails_closed_without_source_evidence_timestamp() -> None:
    response = _with_correlation(
        lambda: CashflowProjectionResponse(
            portfolio_id="PB1",
            range_start_date=date(2026, 4, 10),
            range_end_date=date(2026, 4, 10),
            include_projected=True,
            portfolio_currency="SGD",
            points=[],
            total_net_cashflow=Decimal("0"),
            booked_total_net_cashflow=Decimal("0"),
            projected_settlement_total_cashflow=Decimal("0"),
            projection_days=1,
            request_fingerprint="cashflow_projection:" + "a" * 16,
            source_window_trust={
                "window_status": "DEGRADED",
                "supportability_status": "UNAVAILABLE",
                "reason_codes": ["SOURCE_EVIDENCE_TIMESTAMP_MISSING"],
                "source_row_count": 1,
                "calculated_source_row_count": 1,
                "output_group_count": 0,
                "source_component_totals": {"BOOKED": 0, "PROJECTED": 0},
                "calculated_component_totals": {"BOOKED": 0, "PROJECTED": 0},
            },
            calculation_lineage={
                "algorithm_id": "PORTFOLIO_CASHFLOW_PROJECTION",
                "algorithm_version": 1,
                "intermediate_precision": 50,
                "input_content_hash": "a" * 64,
                "calculation_content_hash": "b" * 64,
                "output_content_hash": "c" * 64,
            },
            **source_data_product_runtime_metadata(
                as_of_date=date(2026, 4, 10),
                reconciliation_status="BLOCKED",
                data_quality_status="BLOCKED",
                latest_evidence_timestamp=None,
                source_evidence_current=False,
                freshness_status="UNAVAILABLE",
            ),
        )
    )

    assert response.product_name == "PortfolioCashflowProjection"
    assert response.data_quality_status == "BLOCKED"
    assert response.reconciliation_status == "BLOCKED"
    assert response.source_window_trust.reason_codes == ["SOURCE_EVIDENCE_TIMESTAMP_MISSING"]
    assert response.source_evidence_current is False
    assert response.freshness_status == "UNAVAILABLE"
    assert response.correlation_id == CORRELATION_ID


def test_reconciliation_control_contract_exposes_blocking_finding_state() -> None:
    response = _with_correlation(
        lambda: ReconciliationFindingListResponse(
            run_id="recon_123",
            generated_at_utc=datetime(2026, 4, 10, 10, tzinfo=UTC),
            total=1,
            items=[
                ReconciliationFindingRecord(
                    finding_id="rf_123",
                    finding_type="missing_cashflow",
                    severity="ERROR",
                    security_id="SEC_A",
                    transaction_id="TXN_A",
                    business_date=date(2026, 4, 10),
                    epoch=3,
                    created_at=datetime(2026, 4, 10, 9, tzinfo=UTC),
                    detail={"expected_cashflow_count": 1, "observed_cashflow_count": 0},
                    is_blocking=True,
                    operational_state="BLOCKING",
                )
            ],
            **source_data_product_runtime_metadata(
                as_of_date=date(2026, 4, 10),
                data_quality_status=PARTIAL,
                latest_evidence_timestamp=datetime(2026, 4, 10, 9, tzinfo=UTC),
            ),
        )
    )

    assert response.product_name == "ReconciliationEvidenceBundle"
    assert response.data_quality_status == PARTIAL
    assert response.items[0].is_blocking is True
    assert response.items[0].operational_state == "BLOCKING"
    assert response.freshness_status == "CURRENT"
    assert response.correlation_id == CORRELATION_ID


def _with_correlation(build_response):
    token = correlation_id_var.set(CORRELATION_ID)
    try:
        return build_response()
    finally:
        correlation_id_var.reset(token)
