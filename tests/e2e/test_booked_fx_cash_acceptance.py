"""Registered HTTP/worker/PG evidence, not direct ledger repair or source-cut approval."""

import json
import os
from pathlib import Path

from tests.test_support.booked_fx_cash_oracle import (
    FIRST_DAY,
    LAST_DAY,
    assert_linked_transactions,
    assert_qualified_holdings,
    has_portfolio_marks,
    has_qualified_holdings,
)
from tests.test_support.booked_fx_cash_restart import restart_owned_query
from tests.test_support.booked_fx_cash_scenario import seed_scenario
from tests.test_support.docker_stack import resolve_compose_file, wait_for_http_health
from tests.test_support.output_control import emit_test_output
from tests.test_support.pipeline_quiescence import (
    read_pipeline_activity_snapshot,
    read_pipeline_last_activity_at,
    wait_for_pipeline_quiescence,
)

from .api_client import E2EApiClient
from .data_factory import unique_suffix


def test_booked_fx_cash_reference_correction_replay_and_process_restart(
    clean_db, db_engine, e2e_api_client: E2EApiClient, capsys
):
    client = e2e_api_client
    scenario = seed_scenario(client, unique_suffix())
    scope = {key: scenario[key] for key in ("portfolio", "equity", "cash")}
    positions_url = f"/portfolios/{scope['portfolio']}/positions"
    transactions_url = f"/portfolios/{scope['portfolio']}/transactions?limit=50"

    def holdings(day, fx):
        return client.poll_for_data(
            f"{positions_url}?as_of_date={day}",
            lambda body: has_qualified_holdings(body, **scope, day=day, reference_fx=fx),
            timeout=180,
            fail_message=f"Booked FX holdings not financially qualified for {day} FX{fx}",
        )

    request = {
        "as_of_date": LAST_DAY,
        "window": {"start_date": FIRST_DAY, "end_date": LAST_DAY},
        "consumer_system": "lotus-performance",
        "frequency": "daily",
        "reporting_currency": "USD",
        "page": {"page_size": 50},
    }
    timeseries_url = f"/integration/portfolios/{scope['portfolio']}/analytics/portfolio-timeseries"

    def timeseries(fx):
        return client.poll_for_post_query_data(
            timeseries_url,
            request,
            lambda body: has_portfolio_marks(body, last_fx=fx),
            timeout=180,
            fail_message=f"Booked cash/security aggregate not reconciled at reference FX{fx}",
        )

    original = {FIRST_DAY: holdings(FIRST_DAY, "2"), LAST_DAY: holdings(LAST_DAY, "2.5")}
    before_marks = timeseries("2.5")
    before_transactions = client.query(transactions_url).json()
    assert_linked_transactions(
        before_transactions, **{key: scenario[key] for key in ("buy_id", "equity", "cash")}
    )
    correction = {
        "fx_rates": [
            {"from_currency": "XTS", "to_currency": "USD", "rate_date": LAST_DAY, "rate": "3"}
        ]
    }
    accepted = client.ingest("/ingest/fx-rates", correction)
    assert accepted.status_code == 202 and accepted.json()["accepted_count"] == 1
    corrected = holdings(LAST_DAY, "3")
    corrected_marks = timeseries("3")
    assert corrected["content_hash"] != original[LAST_DAY]["content_hash"]
    replayed_source = client.ingest(
        "/ingest/transactions", {"transactions": [scenario["transaction"]]}
    )
    assert replayed_source.status_code == 202
    replay = client.reprocess_transactions([scenario["buy_id"], f"{scenario['buy_id']}-CASHLEG"])
    assert replay.status_code == 202
    idle = wait_for_pipeline_quiescence(
        timeout_seconds=120,
        poll_seconds=1,
        stable_cycles=2,
        quiet_seconds=8,
        snapshot_reader=lambda: read_pipeline_activity_snapshot(db_engine),
        last_activity_reader=lambda: read_pipeline_last_activity_at(db_engine),
    )
    replayed = {FIRST_DAY: holdings(FIRST_DAY, "2"), LAST_DAY: holdings(LAST_DAY, "3")}
    after_transactions = client.query(transactions_url).json()
    assert_linked_transactions(
        after_transactions, **{key: scenario[key] for key in ("buy_id", "equity", "cash")}
    )
    restart = restart_owned_query(
        project=os.environ["COMPOSE_PROJECT_NAME"],
        compose_file=resolve_compose_file(str(Path(__file__).resolve().parents[2])),
        ready=lambda: wait_for_http_health(
            "query_service", f"{client.query_url}/health/ready", timeout_seconds=60
        ),
    )
    fresh = E2EApiClient(
        client.ingestion_url, client.query_url, client.query_control_plane_url, client.tenant_id
    )
    try:
        restarted = {}
        for day, fx in ((FIRST_DAY, "2"), (LAST_DAY, "3")):
            body = fresh.query(f"{positions_url}?as_of_date={day}").json()
            assert_qualified_holdings(body, **scope, day=day, reference_fx=fx)
            assert body["positions"] == replayed[day]["positions"]
            assert body["content_hash"] == replayed[day]["content_hash"]
            restarted[day] = body
        persisted = fresh.query(transactions_url).json()
        assert_linked_transactions(
            persisted, **{key: scenario[key] for key in ("buy_id", "equity", "cash")}
        )
    finally:
        fresh.session.close()
    with capsys.disabled():
        emit_test_output(
            "BOOKED_FX_CASH_ACCEPTANCE "
            + json.dumps(
                {
                    "source_commit": os.getenv("GITHUB_SHA"),
                    "scenario": scenario,
                    "original": original,
                    "original_marks": before_marks,
                    "original_transactions": before_transactions,
                    "correction_request": correction,
                    "correction_acceptance": accepted.json(),
                    "corrected": corrected,
                    "corrected_marks": corrected_marks,
                    "source_redelivery": replayed_source.json(),
                    "replay": replay.json(),
                    "quiescence": idle,
                    "replayed": replayed,
                    "transactions_after_replay": after_transactions,
                    "restart": restart,
                    "after_restart": restarted,
                    "transactions_after_restart": persisted,
                    "source_authority": (
                        "synthetic policy/price facts; legacy operational FX, "
                        "not qualified provider cut"
                    ),
                },
                sort_keys=True,
            )
        )
