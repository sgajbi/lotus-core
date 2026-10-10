"""Supported ingress/real worker correction must reach live analytics content identity."""

import json
import os

from tests.test_support.analytics_correction_oracle import (
    DAYS,
    assert_corrected_read,
    assert_equivalent_read,
    has_economics,
)
from tests.test_support.output_control import emit_test_output
from tests.test_support.pipeline_quiescence import (
    read_pipeline_activity_snapshot,
    read_pipeline_last_activity_at,
    wait_for_pipeline_quiescence,
)

from .api_client import E2EApiClient
from .data_factory import unique_suffix


def seed_prices(client: E2EApiClient, security_id: str, prices: tuple[str, ...]):
    return client.ingest(
        "/ingest/market-prices",
        {
            "market_prices": [
                {"security_id": security_id, "price_date": day, "price": price, "currency": "USD"}
                for day, price in zip(DAYS, prices, strict=True)
            ]
        },
    )


def seed_position(client: E2EApiClient, suffix: str) -> tuple[str, str]:
    portfolio_id, security_id = f"E2E_CONTENT_{suffix}", f"SEC_CONTENT_{suffix}"
    client.ingest(
        "/ingest/portfolios",
        {
            "portfolios": [
                {
                    "portfolio_id": portfolio_id,
                    "base_currency": "USD",
                    "open_date": DAYS[0],
                    "risk_exposure": "Medium",
                    "investment_time_horizon": "Long",
                    "portfolio_type": "Advisory",
                    "booking_center_code": "SG",
                    "client_id": f"CONTENT_CIF_{suffix}",
                    "status": "ACTIVE",
                }
            ]
        },
    )
    client.wait_for_admitted_portfolio(portfolio_id)
    client.ingest(
        "/ingest/instruments",
        {
            "instruments": [
                {
                    "security_id": security_id,
                    "name": "Synthetic Correction Equity",
                    "isin": f"CONTENT_{suffix}",
                    "currency": "USD",
                    "product_type": "Equity",
                }
            ]
        },
    )
    client.poll_for_data(
        f"/instruments?security_id={security_id}",
        lambda body: any(row["security_id"] == security_id for row in body.get("instruments", [])),
    )
    client.ingest(
        "/ingest/business-dates",
        {
            "business_dates": [{"business_date": day} for day in DAYS],
        },
    )
    client.ingest(
        "/ingest/transactions",
        {
            "transactions": [
                {
                    "transaction_id": f"CONTENT_BUY_{suffix}",
                    "portfolio_id": portfolio_id,
                    "instrument_id": security_id,
                    "security_id": security_id,
                    "transaction_date": f"{DAYS[0]}T10:00:00Z",
                    "transaction_type": "BUY",
                    "quantity": "10",
                    "price": "100",
                    "gross_transaction_amount": "1000",
                    "trade_currency": "USD",
                    "currency": "USD",
                }
            ]
        },
    )
    seed_prices(client, security_id, ("100", "110", "120"))
    return portfolio_id, security_id


def test_supported_historical_price_correction_changes_live_analytics_identity(
    clean_db, db_engine, e2e_api_client: E2EApiClient, capsys
):
    """No SQL writes, direct worker calls, replay resets or stand-in HTTP applications."""
    client = e2e_api_client
    portfolio_id, security_id = seed_position(client, unique_suffix())
    request = {
        "as_of_date": DAYS[-1],
        "window": {"start_date": DAYS[0], "end_date": DAYS[-1]},
        "consumer_system": "lotus-performance",
        "frequency": "daily",
        "reporting_currency": "USD",
        "page": {"page_size": 200},
    }
    receipts = {}
    for dataset in ("portfolio", "position"):
        endpoint = f"/integration/portfolios/{portfolio_id}/analytics/{dataset}-timeseries"
        before = client.poll_for_post_query_data(
            endpoint,
            request,
            lambda body: has_economics(body, dataset, ("100", "110", "120")),
            timeout=240,
            fail_message=f"Original {dataset} worker materialization incomplete",
        )
        repeated = client.post_query(endpoint, request).json()
        assert_equivalent_read(before, repeated, dataset)
        page_request = {**request, "page": {"page_size": 2}}
        page = client.post_query(endpoint, page_request).json()
        token = page["page"]["next_page_token"]
        assert token
        continuation = {**request, "page": {"page_size": 2, "page_token": token}}
        unchanged = client.post_query(endpoint, continuation)
        assert unchanged.status_code == 200
        receipts[dataset] = {
            "endpoint": endpoint,
            "request": request,
            "before": before,
            "repeat": repeated,
            "page_request": page_request,
            "page": page,
            "continuation_request": continuation,
            "unchanged_continuation": unchanged.json(),
        }
    correction = {
        "market_prices": [
            {
                "security_id": security_id,
                "price_date": DAYS[1],
                "price": "130",
                "currency": "USD",
            }
        ]
    }
    accepted = client.ingest("/ingest/market-prices", correction)
    assert accepted.status_code == 202
    assert accepted.json()["accepted_count"] == 1
    for dataset, receipt in receipts.items():
        after = client.poll_for_post_query_data(
            receipt["endpoint"],
            request,
            lambda body: has_economics(body, dataset, ("100", "130", "120")),
            timeout=240,
            fail_message=f"Historical correction did not reach {dataset} analytics",
        )
        assert_corrected_read(receipt["before"], after, dataset)
        repeated = client.post_query(receipt["endpoint"], request).json()
        assert_equivalent_read(after, repeated, dataset)
        stale = client.post_query(
            receipt["endpoint"],
            receipt["continuation_request"],
            raise_for_status=False,
        )
        assert stale.status_code == 409, stale.text
        assert stale.json()["error_code"] == "QCP_ANALYTICS_STALE_CONTINUATION"
        receipt.update(after=after, corrected_repeat=repeated, stale_continuation=stale.json())
    # A duplicate supported source delivery may enqueue work but cannot change economics/identity.
    replay = client.ingest("/ingest/market-prices", correction)
    assert replay.status_code == 202
    replay_idle = wait_for_pipeline_quiescence(
        timeout_seconds=120,
        poll_seconds=1,
        stable_cycles=2,
        quiet_seconds=8,
        snapshot_reader=lambda: read_pipeline_activity_snapshot(db_engine),
        last_activity_reader=lambda: read_pipeline_last_activity_at(db_engine),
    )
    for dataset, receipt in receipts.items():
        repeated = client.post_query(receipt["endpoint"], request).json()
        assert_equivalent_read(receipt["after"], repeated, dataset)
        receipt["source_replay_read"] = repeated
    # Bypass pytest capture only for this source-safe synthetic receipt: default main E2E
    # logs retain passing proof without changing workflow/manifest capture policy.
    with capsys.disabled():
        emit_test_output(
            "ANALYTICS_CORRECTION_RECEIPT "
            + json.dumps(
                {
                    "source_commit": os.getenv("GITHUB_SHA"),
                    "correction_request": correction,
                    "correction_acceptance": accepted.json(),
                    "replay_acceptance": replay.json(),
                    "replay_quiescence": replay_idle,
                    "products": receipts,
                    "source_cut_qualification": "UNAVAILABLE",
                },
                sort_keys=True,
            )
        )
