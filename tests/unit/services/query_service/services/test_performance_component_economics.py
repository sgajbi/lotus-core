import asyncio
from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace

from src.services.query_service.app.dtos.reference_integration_dto import (
    PerformanceComponentEconomicsRequest,
)
from src.services.query_service.app.services.performance_component_economics import (
    build_performance_component_economics_response,
    build_performance_component_economics_rows,
    build_performance_component_economics_totals,
    performance_component_economics_next_page_token_payload,
    performance_component_economics_page_scope,
    performance_component_economics_page_token,
    resolve_performance_component_economics_response,
)


def _transaction(
    *,
    transaction_id: str,
    security_id: str = " EQ_US_AAPL ",
    transaction_type: str = "DIVIDEND",
    currency: str = " usd ",
    trade_currency: str = " usd ",
    transaction_date: datetime | None = None,
    gross_transaction_amount: str = "125.0000",
    trade_fee: str | None = "2.5000",
    costs: list[SimpleNamespace] | None = None,
    cashflow: SimpleNamespace | None = None,
    withholding_tax_amount: str | None = None,
    other_interest_deductions_amount: str | None = None,
    net_interest_amount: str | None = None,
    realized_capital_pnl_base: str | None = None,
    realized_fx_pnl_base: str | None = None,
    realized_total_pnl_base: str | None = None,
    transaction_fx_rate: str | None = None,
    fx_contract_id: str | None = None,
    updated_at: datetime | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        transaction_id=transaction_id,
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        security_id=security_id,
        transaction_type=transaction_type,
        currency=currency,
        trade_currency=trade_currency,
        transaction_date=transaction_date or datetime(2026, 5, 10, 14, tzinfo=UTC),
        gross_transaction_amount=Decimal(gross_transaction_amount),
        trade_fee=Decimal(trade_fee) if trade_fee is not None else None,
        costs=costs,
        cashflow=cashflow,
        withholding_tax_amount=(
            Decimal(withholding_tax_amount) if withholding_tax_amount is not None else None
        ),
        other_interest_deductions_amount=(
            Decimal(other_interest_deductions_amount)
            if other_interest_deductions_amount is not None
            else None
        ),
        net_interest_amount=Decimal(net_interest_amount)
        if net_interest_amount is not None
        else None,
        realized_capital_pnl_local=Decimal("0"),
        realized_fx_pnl_local=Decimal("0"),
        realized_total_pnl_local=Decimal("0"),
        realized_capital_pnl_base=(
            Decimal(realized_capital_pnl_base) if realized_capital_pnl_base is not None else None
        ),
        realized_fx_pnl_base=Decimal(realized_fx_pnl_base)
        if realized_fx_pnl_base is not None
        else None,
        realized_total_pnl_base=(
            Decimal(realized_total_pnl_base) if realized_total_pnl_base is not None else None
        ),
        transaction_fx_rate=Decimal(transaction_fx_rate)
        if transaction_fx_rate is not None
        else None,
        fx_contract_id=fx_contract_id,
        updated_at=updated_at or datetime(2026, 5, 10, 15, tzinfo=UTC),
    )


def test_performance_component_economics_rows_preserve_source_figures() -> None:
    rows = build_performance_component_economics_rows(
        [
            _transaction(
                transaction_id="TXN-DIV-001",
                costs=[
                    SimpleNamespace(amount=Decimal("1.2500"), currency="USD"),
                    SimpleNamespace(amount=Decimal("1.2500"), currency="USD"),
                ],
                cashflow=SimpleNamespace(
                    amount=Decimal("100.0000"),
                    currency="usd",
                    classification="DIVIDEND",
                    timing="EOD",
                    is_position_flow=True,
                    is_portfolio_flow=False,
                ),
                withholding_tax_amount="15.0000",
                other_interest_deductions_amount="5.0000",
                net_interest_amount="80.0000",
                realized_capital_pnl_base="10.0000",
                realized_fx_pnl_base="3.0000",
                realized_total_pnl_base="13.0000",
                transaction_fx_rate="1.2500000000",
                fx_contract_id="FXC-001",
            )
        ]
    )

    row = rows[0]
    assert row.transaction_id == "TXN-DIV-001"
    assert row.security_id == "EQ_US_AAPL"
    assert row.transaction_type == "DIVIDEND"
    assert row.trade_currency == "USD"
    assert row.trade_fee_amount == Decimal("2.5000")
    assert row.trade_fee_currency == "USD"
    assert [(component.currency, component.amount) for component in row.trade_fee_components] == [
        ("USD", Decimal("2.5000"))
    ]
    assert row.cashflow_amount == Decimal("100.0000")
    assert row.cashflow_classification == "DIVIDEND"
    assert row.cashflow_timing == "EOD"
    assert row.withholding_tax_amount == Decimal("15.0000")
    assert row.other_interest_deductions_amount == Decimal("5.0000")
    assert row.net_interest_amount == Decimal("80.0000")
    assert row.realized_pnl_local_currency == "USD"
    assert row.realized_fx_pnl_base == Decimal("3.0000")
    assert row.transaction_fx_rate == Decimal("1.2500000000")
    assert row.fx_contract_id == "FXC-001"


def test_performance_component_economics_totals_group_domain_figures() -> None:
    rows = build_performance_component_economics_rows(
        [
            _transaction(
                transaction_id="TXN-DIV-001",
                currency="EUR",
                trade_currency="USD",
                costs=[SimpleNamespace(amount=Decimal("2.5000"), currency="USD")],
                cashflow=SimpleNamespace(
                    amount=Decimal("100.0000"),
                    currency="EUR",
                    classification="DIVIDEND",
                    timing="EOD",
                    is_position_flow=True,
                    is_portfolio_flow=False,
                ),
                withholding_tax_amount="15.0000",
                other_interest_deductions_amount="5.0000",
                net_interest_amount="80.0000",
                realized_capital_pnl_base="10.0000",
                realized_fx_pnl_base="3.0000",
                realized_total_pnl_base="13.0000",
            )
        ]
    )

    totals = {
        (total.component_family, total.currency): total
        for total in build_performance_component_economics_totals(
            rows,
            portfolio_base_currency="USD",
        )
    }

    assert totals[("cashflow", "EUR")].amount == Decimal("100.0000")
    assert totals[("fee", "USD")].amount == Decimal("2.5000")
    assert totals[("income", "EUR")].amount == Decimal("80.0000")
    assert totals[("tax", "EUR")].amount == Decimal("20.0000")
    assert totals[("realized_capital_pnl", "USD")].amount == Decimal("10.0000")
    assert totals[("realized_fx_pnl", "USD")].amount == Decimal("3.0000")
    assert totals[("realized_total_pnl", "USD")].amount == Decimal("13.0000")
    assert totals[("tax", "EUR")].evidence_count == 2
    assert rows[0].trade_currency == "USD"
    assert rows[0].realized_pnl_local_currency == "USD"


def test_performance_component_economics_response_reports_coverage_and_lineage() -> None:
    transaction = _transaction(
        transaction_id="TXN-DIV-001",
        costs=[
            SimpleNamespace(
                amount=Decimal("2.5000"),
                currency="USD",
                updated_at=datetime(2026, 5, 10, 17, tzinfo=UTC),
            )
        ],
        cashflow=SimpleNamespace(
            amount=Decimal("100.0000"),
            currency="USD",
            classification="DIVIDEND",
            timing="EOD",
            is_position_flow=True,
            is_portfolio_flow=False,
            updated_at=datetime(2026, 5, 10, 16, tzinfo=UTC),
        ),
        withholding_tax_amount="15.0000",
        other_interest_deductions_amount="5.0000",
        net_interest_amount="80.0000",
        realized_capital_pnl_base="10.0000",
        realized_fx_pnl_base="3.0000",
        realized_total_pnl_base="13.0000",
        transaction_fx_rate="1.2500000000",
    )
    request = PerformanceComponentEconomicsRequest(
        as_of_date=date(2026, 5, 10),
        window={"start_date": date(2026, 5, 1), "end_date": date(2026, 5, 10)},
        tenant_id="tenant-sg",
    )

    response = build_performance_component_economics_response(
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        request=request,
        rows=build_performance_component_economics_rows([transaction]),
        transactions=[transaction],
        portfolio_base_currency="USD",
    )

    assert response.product_name == "PerformanceComponentEconomics"
    assert response.supportability.state == "READY"
    assert response.supportability.reason == "PERFORMANCE_COMPONENT_ECONOMICS_READY"
    assert response.supportability.source_row_count == 1
    assert response.supportability.observed_component_families == [
        "cashflow",
        "fee",
        "income",
        "tax",
        "realized_capital_pnl",
        "realized_fx_pnl",
        "realized_total_pnl",
        "fx_context",
    ]
    assert response.supportability.missing_component_families == []
    assert response.component_totals_scope == "returned_page"
    assert response.page.page_size == 250
    assert response.page.next_page_token is None
    assert response.data_quality_status == "COMPLETE"
    assert response.tenant_id == "tenant-sg"
    assert response.latest_evidence_timestamp == datetime(2026, 5, 10, 17, tzinfo=UTC)
    assert response.lineage["source_table"] == "transactions,cashflows,transaction_costs"


def test_performance_component_economics_totals_do_not_mislabel_mixed_fee_currency() -> None:
    rows = build_performance_component_economics_rows(
        [
            _transaction(
                transaction_id="TXN-MIXED-FEE-001",
                costs=[
                    SimpleNamespace(amount=Decimal("1.0000"), currency="USD"),
                    SimpleNamespace(amount=Decimal("2.0000"), currency="EUR"),
                ],
            )
        ]
    )

    totals = {
        (total.component_family, total.currency): total
        for total in build_performance_component_economics_totals(
            rows,
            portfolio_base_currency="USD",
        )
    }

    assert rows[0].trade_fee_amount == Decimal("0")
    assert rows[0].trade_fee_currency == "MIXED"
    assert [
        (component.currency, component.amount) for component in rows[0].trade_fee_components
    ] == [
        ("EUR", Decimal("2.0000")),
        ("USD", Decimal("1.0000")),
    ]
    assert totals[("fee", "EUR")].amount == Decimal("2.0000")
    assert totals[("fee", "USD")].amount == Decimal("1.0000")


def test_performance_component_economics_deduplicates_fee_component_identity() -> None:
    rows = build_performance_component_economics_rows(
        [
            _transaction(
                transaction_id="TXN-DUP-FEE-001",
                costs=[
                    SimpleNamespace(
                        fee_type=" brokerage ",
                        amount=Decimal("1.0000"),
                        currency="usd",
                    ),
                    SimpleNamespace(
                        fee_type="BROKERAGE",
                        amount=Decimal("1.0000"),
                        currency="USD",
                    ),
                    SimpleNamespace(
                        fee_type="exchange_fee",
                        amount=Decimal("2.0000"),
                        currency="USD",
                    ),
                ],
            )
        ]
    )

    totals = {
        (total.component_family, total.currency): total
        for total in build_performance_component_economics_totals(
            rows,
            portfolio_base_currency="USD",
        )
    }

    assert [
        (component.currency, component.amount) for component in rows[0].trade_fee_components
    ] == [("USD", Decimal("3.0000"))]
    assert totals[("fee", "USD")].amount == Decimal("3.0000")
    assert totals[("fee", "USD")].evidence_count == 1


def test_resolve_performance_component_economics_response_orchestrates_repository_read() -> None:
    async def run_case():
        calls: list[tuple[str, dict[str, object]]] = []

        class Repository:
            async def portfolio_exists(self, portfolio_id: str) -> bool:
                calls.append(("portfolio_exists", {"portfolio_id": portfolio_id}))
                return True

            async def get_portfolio_base_currency(self, portfolio_id: str) -> str:
                calls.append(("get_portfolio_base_currency", {"portfolio_id": portfolio_id}))
                return "USD"

            async def list_performance_component_economics_evidence(
                self, **kwargs: object
            ) -> list[SimpleNamespace]:
                calls.append(("performance_component_economics", kwargs))
                return [
                    _transaction(transaction_id="TXN-DIV-001"),
                    _transaction(transaction_id="TXN-DIV-002", security_id="EQ_US_MSFT"),
                ]

        encoded_payloads: list[dict[str, object]] = []

        def encode(payload: dict[str, object]) -> str:
            encoded_payloads.append(payload)
            return "encoded-token"

        response = await resolve_performance_component_economics_response(
            repository=Repository(),
            portfolio_id="PB_SG_GLOBAL_BAL_001",
            request=PerformanceComponentEconomicsRequest(
                as_of_date=date(2026, 5, 10),
                window={"start_date": date(2026, 5, 1), "end_date": date(2026, 5, 10)},
                security_ids=["EQ_US_AAPL"],
                transaction_types=["dividend"],
                page={"page_size": 1},
            ),
            decode_page_token=lambda _: {},
            encode_page_token=encode,
        )
        return response, calls, encoded_payloads

    response, calls, encoded_payloads = asyncio.run(run_case())

    assert response.portfolio_id == "PB_SG_GLOBAL_BAL_001"
    assert response.page.next_page_token == "encoded-token"
    assert response.page.returned_component_count == 1
    assert response.supportability.state == "DEGRADED"
    assert response.supportability.reason == "PERFORMANCE_COMPONENT_ECONOMICS_PAGE_PARTIAL"
    assert response.data_quality_status == "PARTIAL"
    assert [call[0] for call in calls] == [
        "portfolio_exists",
        "get_portfolio_base_currency",
        "performance_component_economics",
    ]
    assert calls[2][1]["transaction_types"] == ["DIVIDEND"]
    assert calls[2][1]["security_ids"] == ["EQ_US_AAPL"]
    assert calls[2][1]["after_key"] == ()
    assert calls[2][1]["limit"] == 2
    assert encoded_payloads == [
        {
            "scope_fingerprint": response.page.request_scope_fingerprint,
            "last_row_key": ["EQ_US_AAPL", "2026-05-10", "TXN-DIV-001"],
        }
    ]


def test_performance_component_economics_page_scope_rejects_scope_mismatch() -> None:
    request = PerformanceComponentEconomicsRequest(
        as_of_date=date(2026, 5, 10),
        window={"start_date": date(2026, 5, 1), "end_date": date(2026, 5, 10)},
    )

    try:
        performance_component_economics_page_scope(
            portfolio_id="PB_SG_GLOBAL_BAL_001",
            request=request,
            cursor={"scope_fingerprint": "wrong-scope"},
        )
    except ValueError as exc:
        assert "component economics page token does not match request scope" in str(exc)
    else:
        raise AssertionError("Expected performance component economics page token scope mismatch")


def test_performance_component_economics_page_scope_rejects_malformed_row_key() -> None:
    request = PerformanceComponentEconomicsRequest(
        as_of_date=date(2026, 5, 10),
        window={"start_date": date(2026, 5, 1), "end_date": date(2026, 5, 10)},
    )

    try:
        performance_component_economics_page_scope(
            portfolio_id="PB_SG_GLOBAL_BAL_001",
            request=request,
            cursor={"last_row_key": ["EQ_US_AAPL"]},
        )
    except ValueError as exc:
        assert "page token has an invalid row key" in str(exc)
    else:
        raise AssertionError("Expected performance component economics malformed page token")


def test_performance_component_economics_page_token_uses_last_row_key() -> None:
    request = PerformanceComponentEconomicsRequest(
        as_of_date=date(2026, 5, 10),
        window={"start_date": date(2026, 5, 1), "end_date": date(2026, 5, 10)},
    )
    page_scope = performance_component_economics_page_scope(
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        request=request,
        cursor={},
    )
    rows = build_performance_component_economics_rows(
        [
            _transaction(transaction_id="TXN-DIV-001"),
            _transaction(transaction_id="TXN-DIV-002", security_id="EQ_US_MSFT"),
        ]
    )

    assert performance_component_economics_next_page_token_payload(
        page_scope=page_scope,
        rows=rows,
        has_more=True,
    ) == {
        "scope_fingerprint": page_scope.request_fingerprint,
        "last_row_key": ["EQ_US_MSFT", "2026-05-10", "TXN-DIV-002"],
    }
    encoded_payloads: list[dict[str, object]] = []
    assert (
        performance_component_economics_page_token(
            page_scope=page_scope,
            rows=rows,
            has_more=True,
            encode_page_token=lambda payload: encoded_payloads.append(payload) or "token",
        )
        == "token"
    )
    assert encoded_payloads[0]["last_row_key"] == ["EQ_US_MSFT", "2026-05-10", "TXN-DIV-002"]
    assert (
        performance_component_economics_page_token(
            page_scope=page_scope,
            rows=rows,
            has_more=False,
            encode_page_token=lambda _: "unexpected",
        )
        is None
    )
