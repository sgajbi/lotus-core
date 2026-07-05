from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace

from portfolio_common.logging_utils import correlation_id_var
from portfolio_common.reconciliation_quality import COMPLETE, PARTIAL

from src.services.query_service.app.dtos.cashflow_projection_dto import (
    CashflowProjectionResponse,
)
from src.services.query_service.app.dtos.operations_dto import (
    ReconciliationFindingListResponse,
    ReconciliationFindingRecord,
)
from src.services.query_service.app.dtos.position_dto import Position
from src.services.query_service.app.dtos.reference_integration_dto import (
    InstrumentEligibilityBulkRequest,
    MarketDataCoverageRequest,
    MarketDataCurrencyPair,
    TransactionCostCurveRequest,
)
from src.services.query_service.app.dtos.source_data_product_identity import (
    SourceDataDegradationDetail,
    SourceDataDegradationSummary,
    source_data_product_runtime_metadata,
)
from src.services.query_service.app.dtos.valuation_dto import ValuationData
from src.services.query_service.app.services.instrument_eligibility import (
    build_instrument_eligibility_bulk_response,
)
from src.services.query_service.app.services.market_data_coverage import (
    build_market_data_coverage_response,
    market_data_coverage_read_scope,
)
from src.services.query_service.app.services.position_holdings import (
    portfolio_positions_response_data,
)
from src.services.query_service.app.services.transaction_cost_curve import (
    build_transaction_cost_curve_page,
    build_transaction_cost_curve_response,
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
        lambda: build_market_data_coverage_response(
            request=request,
            read_scope=market_data_coverage_read_scope(request),
            price_rows=[
                SimpleNamespace(
                    security_id="EQ_US_AAPL",
                    price_date=date(2026, 4, 1),
                    price=Decimal("187.12"),
                    currency="USD",
                    updated_at=datetime(2026, 4, 1, 8, tzinfo=UTC),
                )
            ],
            fx_rows=[],
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
        lambda: build_instrument_eligibility_bulk_response(
            request=InstrumentEligibilityBulkRequest(
                security_ids=["UNKNOWN_SEC", "EQ_US_AAPL"],
                as_of_date=date(2026, 4, 10),
            ),
            rows=[
                SimpleNamespace(
                    security_id="EQ_US_AAPL",
                    eligibility_status="APPROVED",
                    product_shelf_status="APPROVED",
                    buy_allowed=True,
                    sell_allowed=True,
                    restriction_reason_codes=[],
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
                    quality_status="accepted",
                    source_record_id="eligibility:EQ_US_AAPL",
                    source_timestamp=datetime(2026, 4, 10, 9, tzinfo=UTC),
                )
            ],
        )
    )

    assert response.product_name == "InstrumentEligibilityProfile"
    assert response.data_quality_status == PARTIAL
    assert response.supportability.state == "INCOMPLETE"
    assert response.supportability.missing_security_ids == ["UNKNOWN_SEC"]
    assert response.records[0].found is False
    assert response.correlation_id == CORRELATION_ID


def test_valuation_contract_reports_page_scoped_degradation() -> None:
    transactions = [
        _costed_transaction("TXN-A", "EQ_US_AAPL", datetime(2026, 4, 1, 10, tzinfo=UTC)),
        _costed_transaction("TXN-B", "EQ_US_MSFT", datetime(2026, 4, 2, 10, tzinfo=UTC)),
    ]
    curve_page = build_transaction_cost_curve_page(
        portfolio_id="PB1",
        transactions=transactions,
        min_observation_count=1,
        after_key=(),
        page_size=1,
    )
    response = _with_correlation(
        lambda: build_transaction_cost_curve_response(
            portfolio_id="PB1",
            request=TransactionCostCurveRequest(
                as_of_date=date(2026, 4, 10),
                window={"start_date": date(2026, 4, 1), "end_date": date(2026, 4, 10)},
                page={"page_size": 1},
            ),
            request_scope_fingerprint="scope-123",
            curve_page=curve_page,
            transactions=transactions,
            next_page_token="token-2",
        )
    )

    assert response.product_name == "TransactionCostCurve"
    assert response.data_quality_status == PARTIAL
    assert response.supportability.state == "DEGRADED"
    assert response.supportability.reason == "TRANSACTION_COST_CURVE_PAGE_PARTIAL"
    assert response.page.next_page_token == "token-2"
    assert response.correlation_id == CORRELATION_ID


def test_cashflow_contract_cannot_report_current_without_source_evidence_timestamp() -> None:
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
            **source_data_product_runtime_metadata(
                as_of_date=date(2026, 4, 10),
                data_quality_status=COMPLETE,
                latest_evidence_timestamp=None,
            ),
        )
    )

    assert response.product_name == "PortfolioCashflowProjection"
    assert response.data_quality_status == COMPLETE
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


def _costed_transaction(
    transaction_id: str,
    security_id: str,
    transaction_date: datetime,
) -> SimpleNamespace:
    return SimpleNamespace(
        transaction_id=transaction_id,
        portfolio_id="PB1",
        security_id=security_id,
        transaction_type="BUY",
        currency="USD",
        trade_currency="USD",
        gross_transaction_amount=Decimal("100000"),
        trade_fee=Decimal("20"),
        costs=[],
        transaction_date=transaction_date,
        updated_at=transaction_date,
    )


def _with_correlation(build_response):
    token = correlation_id_var.set(CORRELATION_ID)
    try:
        return build_response()
    finally:
        correlation_id_var.reset(token)
