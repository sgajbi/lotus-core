from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace

from src.services.query_service.app.dtos.reference_integration_dto import (
    TransactionCostCurveRequest,
)
from src.services.query_service.app.services.transaction_cost_curve import (
    build_transaction_cost_curve_page,
    build_transaction_cost_curve_point,
    build_transaction_cost_curve_points,
    build_transaction_cost_curve_response,
    has_observed_transaction_cost_evidence,
    transaction_cost_curve_key,
    transaction_cost_curve_next_page_token_payload,
    transaction_cost_curve_page_token,
    transaction_cost_curve_request_scope,
    transaction_fee_amount,
)


class _StringCountedValue:
    def __init__(self, raw: str) -> None:
        self.raw = raw
        self.stringify_count = 0

    def __str__(self) -> str:
        self.stringify_count += 1
        return self.raw


def _transaction(
    *,
    transaction_id: str,
    security_id: str = " EQ_US_AAPL ",
    transaction_type: str = " buy ",
    currency: str = " usd ",
    gross_transaction_amount: str = "100000.0000",
    trade_fee: str | None = "20.0000",
    costs: list[SimpleNamespace] | None = None,
    transaction_date: datetime | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        transaction_id=transaction_id,
        security_id=security_id,
        transaction_type=transaction_type,
        currency=currency,
        gross_transaction_amount=Decimal(gross_transaction_amount),
        trade_fee=Decimal(trade_fee) if trade_fee is not None else None,
        costs=costs,
        transaction_date=transaction_date or datetime(2026, 5, 1, tzinfo=UTC),
    )


def test_transaction_cost_curve_uses_explicit_cost_rows_before_trade_fee() -> None:
    transaction = _transaction(
        transaction_id="TXN-AAPL-001",
        trade_fee="999.0000",
        costs=[SimpleNamespace(amount="12.5000"), SimpleNamespace(amount=Decimal("7.5000"))],
    )

    assert transaction_fee_amount(transaction) == Decimal("20.0000")
    assert has_observed_transaction_cost_evidence(transaction) is True
    assert transaction_cost_curve_key(transaction) == ("EQ_US_AAPL", "BUY", "USD")


def test_transaction_cost_curve_fee_amount_treats_blank_cost_as_zero() -> None:
    transaction = _transaction(
        transaction_id="TXN-AAPL-001",
        trade_fee="999.0000",
        costs=[SimpleNamespace(amount=" "), SimpleNamespace(amount=Decimal("7.5000"))],
    )

    assert transaction_fee_amount(transaction) == Decimal("7.5000")


def test_transaction_cost_curve_points_group_and_filter_evidence() -> None:
    points = build_transaction_cost_curve_points(
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        transactions=[
            _transaction(
                transaction_id="TXN-AAPL-002",
                gross_transaction_amount="200000.0000",
                trade_fee="30.0000",
                transaction_date=datetime(2026, 5, 3, tzinfo=UTC),
            ),
            _transaction(
                transaction_id="TXN-AAPL-001",
                gross_transaction_amount="100000.0000",
                trade_fee="20.0000",
                transaction_date=datetime(2026, 5, 1, tzinfo=UTC),
            ),
            _transaction(
                transaction_id="TXN-MSFT-ZERO-FEE",
                security_id="EQ_US_MSFT",
                trade_fee="0.0000",
            ),
        ],
        min_observation_count=2,
    )

    assert len(points) == 1
    point = points[0]
    assert point.portfolio_id == "PB_SG_GLOBAL_BAL_001"
    assert point.security_id == "EQ_US_AAPL"
    assert point.transaction_type == "BUY"
    assert point.currency == "USD"
    assert point.observation_count == 2
    assert point.total_notional == Decimal("300000.0000")
    assert point.total_cost == Decimal("50.0000")
    assert point.average_cost_bps == Decimal("1.6667")
    assert point.min_cost_bps == Decimal("1.5000")
    assert point.max_cost_bps == Decimal("2.0000")
    assert point.first_observed_date.isoformat() == "2026-05-01"
    assert point.last_observed_date.isoformat() == "2026-05-03"
    assert point.sample_transaction_ids == ["TXN-AAPL-001", "TXN-AAPL-002"]
    assert point.source_lineage["source_table"] == "transactions,transaction_costs"


def test_transaction_cost_curve_points_reuse_observations_in_bulk_path() -> None:
    gross_amount = _StringCountedValue("100000.0000")
    transaction = _transaction(
        transaction_id="TXN-AAPL-001",
        gross_transaction_amount="1.0000",
        trade_fee="20.0000",
    )
    transaction.gross_transaction_amount = gross_amount

    points = build_transaction_cost_curve_points(
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        transactions=[transaction],
        min_observation_count=1,
    )

    assert len(points) == 1
    assert points[0].total_notional == Decimal("100000.0000")
    assert gross_amount.stringify_count == 1


def test_transaction_cost_curve_page_builds_only_requested_slice() -> None:
    page = build_transaction_cost_curve_page(
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        transactions=[
            _transaction(transaction_id="TXN-AAPL-001", security_id="EQ_US_AAPL"),
            _transaction(transaction_id="TXN-MSFT-001", security_id="EQ_US_MSFT"),
            _transaction(transaction_id="TXN-TSLA-001", security_id="EQ_US_TSLA"),
        ],
        min_observation_count=1,
        page_size=1,
    )

    assert [point.security_id for point in page.points] == ["EQ_US_AAPL"]
    assert page.all_curve_keys == [
        ("EQ_US_AAPL", "BUY", "USD"),
        ("EQ_US_MSFT", "BUY", "USD"),
        ("EQ_US_TSLA", "BUY", "USD"),
    ]
    assert page.has_more is True

    next_page = build_transaction_cost_curve_page(
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        transactions=[
            _transaction(transaction_id="TXN-AAPL-001", security_id="EQ_US_AAPL"),
            _transaction(transaction_id="TXN-MSFT-001", security_id="EQ_US_MSFT"),
            _transaction(transaction_id="TXN-TSLA-001", security_id="EQ_US_TSLA"),
        ],
        min_observation_count=1,
        after_key=("EQ_US_AAPL", "BUY", "USD"),
        page_size=1,
    )

    assert [point.security_id for point in next_page.points] == ["EQ_US_MSFT"]
    assert next_page.has_more is True


def test_transaction_cost_curve_request_scope_binds_filters_and_cursor() -> None:
    request = TransactionCostCurveRequest(
        as_of_date=date(2026, 4, 10),
        window={"start_date": date(2026, 4, 1), "end_date": date(2026, 4, 10)},
        security_ids=["EQ_US_AAPL", "EQ_US_MSFT"],
        transaction_types=["BUY", "SELL"],
        min_observation_count=2,
        tenant_id="TENANT_SG",
    )

    scope = transaction_cost_curve_request_scope(
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        request=request,
        cursor={"last_curve_key": ["EQ_US_AAPL", "BUY", "USD"]},
    )

    assert scope.request_fingerprint
    assert scope.after_key == ("EQ_US_AAPL", "BUY", "USD")


def test_transaction_cost_curve_request_scope_rejects_token_scope_mismatch() -> None:
    request = TransactionCostCurveRequest(
        as_of_date=date(2026, 4, 10),
        window={"start_date": date(2026, 4, 1), "end_date": date(2026, 4, 10)},
    )

    try:
        transaction_cost_curve_request_scope(
            portfolio_id="PB_SG_GLOBAL_BAL_001",
            request=request,
            cursor={"scope_fingerprint": "wrong-scope"},
        )
    except ValueError as exc:
        assert "cost curve page token does not match request scope" in str(exc)
    else:
        raise AssertionError("Expected transaction cost curve page token scope mismatch")


def test_transaction_cost_curve_next_page_token_payload_uses_last_curve_point() -> None:
    request = TransactionCostCurveRequest(
        as_of_date=date(2026, 4, 10),
        window={"start_date": date(2026, 4, 1), "end_date": date(2026, 4, 10)},
    )
    scope = transaction_cost_curve_request_scope(
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        request=request,
        cursor={},
    )
    curve_page = build_transaction_cost_curve_page(
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        transactions=[
            _transaction(transaction_id="TXN-AAPL-001", security_id="EQ_US_AAPL"),
            _transaction(transaction_id="TXN-MSFT-001", security_id="EQ_US_MSFT"),
        ],
        min_observation_count=1,
        page_size=1,
    )

    assert transaction_cost_curve_next_page_token_payload(
        request_scope=scope,
        curve_page=curve_page,
    ) == {
        "scope_fingerprint": scope.request_fingerprint,
        "last_curve_key": ["EQ_US_AAPL", "BUY", "USD"],
    }

    final_page = build_transaction_cost_curve_page(
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        transactions=[_transaction(transaction_id="TXN-AAPL-001", security_id="EQ_US_AAPL")],
        min_observation_count=1,
        page_size=10,
    )
    assert (
        transaction_cost_curve_next_page_token_payload(
            request_scope=scope,
            curve_page=final_page,
        )
        is None
    )


def test_transaction_cost_curve_page_token_encodes_payload() -> None:
    request = TransactionCostCurveRequest(
        as_of_date=date(2026, 4, 10),
        window={"start_date": date(2026, 4, 1), "end_date": date(2026, 4, 10)},
    )
    scope = transaction_cost_curve_request_scope(
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        request=request,
        cursor={},
    )
    curve_page = build_transaction_cost_curve_page(
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        transactions=[
            _transaction(transaction_id="TXN-AAPL-001", security_id="EQ_US_AAPL"),
            _transaction(transaction_id="TXN-MSFT-001", security_id="EQ_US_MSFT"),
        ],
        min_observation_count=1,
        page_size=1,
    )
    encoded_payloads: list[dict[str, object]] = []

    def encode(payload: dict[str, object]) -> str:
        encoded_payloads.append(payload)
        return "encoded-token"

    assert (
        transaction_cost_curve_page_token(
            request_scope=scope,
            curve_page=curve_page,
            encode_page_token=encode,
        )
        == "encoded-token"
    )
    assert encoded_payloads == [
        {
            "scope_fingerprint": scope.request_fingerprint,
            "last_curve_key": ["EQ_US_AAPL", "BUY", "USD"],
        }
    ]


def test_transaction_cost_curve_page_token_suppresses_terminal_page() -> None:
    request = TransactionCostCurveRequest(
        as_of_date=date(2026, 4, 10),
        window={"start_date": date(2026, 4, 1), "end_date": date(2026, 4, 10)},
    )
    scope = transaction_cost_curve_request_scope(
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        request=request,
        cursor={},
    )
    curve_page = build_transaction_cost_curve_page(
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        transactions=[_transaction(transaction_id="TXN-AAPL-001", security_id="EQ_US_AAPL")],
        min_observation_count=1,
        page_size=10,
    )

    def encode(_: dict[str, object]) -> str:
        raise AssertionError("Unexpected token encoding for terminal page")

    assert (
        transaction_cost_curve_page_token(
            request_scope=scope,
            curve_page=curve_page,
            encode_page_token=encode,
        )
        is None
    )


def test_transaction_cost_curve_response_reports_page_scoped_supportability() -> None:
    transactions = [
        _transaction(
            transaction_id="TXN-AAPL-001",
            security_id="EQ_US_AAPL",
            transaction_date=datetime(2026, 4, 1, 10, tzinfo=UTC),
        ),
        _transaction(
            transaction_id="TXN-MSFT-001",
            security_id="EQ_US_MSFT",
            transaction_date=datetime(2026, 4, 2, 10, tzinfo=UTC),
        ),
    ]
    transactions[0].updated_at = datetime(2026, 4, 1, 10, tzinfo=UTC)
    transactions[1].updated_at = datetime(2026, 4, 2, 10, tzinfo=UTC)
    curve_page = build_transaction_cost_curve_page(
        portfolio_id="PB1",
        transactions=transactions,
        min_observation_count=1,
        after_key=(),
        page_size=1,
    )

    response = build_transaction_cost_curve_response(
        portfolio_id="PB1",
        request=TransactionCostCurveRequest(
            as_of_date=date(2026, 4, 10),
            window={"start_date": date(2026, 4, 1), "end_date": date(2026, 4, 10)},
            security_ids=["EQ_US_AAPL"],
            page={"page_size": 1},
        ),
        request_scope_fingerprint="scope-123",
        curve_page=curve_page,
        transactions=transactions,
        next_page_token="token-2",
    )

    assert response.product_name == "TransactionCostCurve"
    assert response.page.next_page_token == "token-2"
    assert response.page.returned_component_count == 1
    assert response.supportability.state == "DEGRADED"
    assert response.supportability.reason == "TRANSACTION_COST_CURVE_PAGE_PARTIAL"
    assert response.supportability.missing_security_ids == []
    assert response.data_quality_status == "PARTIAL"
    assert response.latest_evidence_timestamp == datetime(2026, 4, 2, 10, tzinfo=UTC)
    assert response.lineage == {
        "source_system": "transactions",
        "contract_version": "rfc_040_wtbd_007_v1",
    }


def test_transaction_cost_curve_response_reports_missing_requested_security() -> None:
    transactions = [_transaction(transaction_id="TXN-AAPL-001", security_id="EQ_US_AAPL")]
    curve_page = build_transaction_cost_curve_page(
        portfolio_id="PB1",
        transactions=transactions,
        min_observation_count=1,
        after_key=(),
        page_size=10,
    )

    response = build_transaction_cost_curve_response(
        portfolio_id="PB1",
        request=TransactionCostCurveRequest(
            as_of_date=date(2026, 4, 10),
            window={"start_date": date(2026, 4, 1), "end_date": date(2026, 4, 10)},
            security_ids=["EQ_US_AAPL", "UNKNOWN_SEC"],
        ),
        request_scope_fingerprint="scope-123",
        curve_page=curve_page,
        transactions=transactions,
        next_page_token=None,
    )

    assert response.supportability.state == "INCOMPLETE"
    assert response.supportability.reason == "TRANSACTION_COST_EVIDENCE_MISSING_FOR_SECURITIES"
    assert response.supportability.missing_security_ids == ["UNKNOWN_SEC"]
    assert response.data_quality_status == "PARTIAL"


def test_transaction_cost_curve_point_ignores_unusable_direct_rows() -> None:
    point = build_transaction_cost_curve_point(
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        key=("EQ_US_AAPL", "BUY", "USD"),
        rows=[
            _transaction(
                transaction_id="TXN-AAPL-ZERO-NOTIONAL",
                gross_transaction_amount="0.0000",
                trade_fee="50.0000",
            ),
            _transaction(
                transaction_id="TXN-AAPL-001",
                gross_transaction_amount="100000.0000",
                trade_fee="20.0000",
            ),
        ],
    )

    assert point is not None
    assert point.observation_count == 1
    assert point.total_notional == Decimal("100000.0000")
    assert point.total_cost == Decimal("20.0000")
    assert point.average_cost_bps == Decimal("2.0000")
    assert point.sample_transaction_ids == ["TXN-AAPL-001"]
