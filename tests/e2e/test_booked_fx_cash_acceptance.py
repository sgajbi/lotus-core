"""Registered HTTP/worker/PG evidence, not direct ledger repair or source-cut approval."""

import json
import os
from datetime import date
from decimal import Decimal
from pathlib import Path

from sqlalchemy import text

from tests.test_support.booked_fx_cash_oracle import (
    FIRST_DAY,
    LAST_DAY,
    assert_funded_cash_transactions,
    assert_linked_transactions,
    assert_qualified_holdings,
    has_funded_cash_holdings,
    has_missing_valuation_fx,
    has_portfolio_marks,
    has_qualified_holdings,
    has_same_currency_funded_holdings,
)
from tests.test_support.booked_fx_cash_restart import restart_owned_query
from tests.test_support.booked_fx_cash_scenario import funded_cash_transactions, seed_scenario
from tests.test_support.docker_stack import resolve_compose_file, wait_for_http_health
from tests.test_support.output_control import emit_test_output
from tests.test_support.pipeline_quiescence import (
    read_pipeline_activity_snapshot,
    read_pipeline_last_activity_at,
    wait_for_pipeline_quiescence,
)

from .api_client import E2EApiClient
from .data_factory import unique_suffix


def admit_scenario_instruments(client, equity, cash, currency="XTS"):
    """Own and settle real reference admission before publishing any transaction."""
    client.ingest(
        "/ingest/instruments",
        {
            "instruments": [
                {
                    "security_id": security,
                    "name": f"Synthetic {kind}",
                    "isin": security,
                    "currency": currency,
                    "product_type": kind,
                    "asset_class": kind,
                }
                for security, kind in ((equity, "Equity"), (cash, "Cash"))
            ]
        },
    )
    for security in (equity, cash):
        client.poll_for_data(
            f"/instruments/?security_id={security}",
            lambda body, expected=security: any(
                row["security_id"] == expected for row in body.get("instruments", [])
            ),
        )


def test_booked_fx_cash_reference_correction_replay_and_process_restart(
    clean_db, db_engine, e2e_api_client: E2EApiClient, capsys
):
    client = e2e_api_client
    scenario = seed_scenario(client, unique_suffix(), admit_instruments=admit_scenario_instruments)
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

    # The booking-date reference deliberately conflicts with source-booked FX2.
    first_holdings = holdings(FIRST_DAY, "2.5")
    missing_jobs = []

    def missing_fx_producer_and_response(body):
        if not has_missing_valuation_fx(body, **scope):
            return False
        with db_engine.connect() as connection:
            rows = (
                connection.execute(
                    text(
                        "SELECT id, security_id, epoch, status, failure_reason "
                        "FROM portfolio_valuation_jobs WHERE portfolio_id = :portfolio "
                        "AND valuation_date = :day ORDER BY epoch DESC, id DESC"
                    ),
                    {"portfolio": scope["portfolio"], "day": date.fromisoformat(LAST_DAY)},
                )
                .mappings()
                .all()
            )
        latest = {}
        for row in rows:
            latest.setdefault(row["security_id"], dict(row))
        if set(latest) != {scope["equity"], scope["cash"]}:
            return False
        if not all(
            row["status"] == "FAILED"
            and row["failure_reason"] == f"Missing exact-date FX rate for XTS->USD on {LAST_DAY}"
            for row in latest.values()
        ):
            return False
        missing_jobs[:] = list(latest.values())
        return True

    unavailable = client.poll_for_data(
        f"{positions_url}?as_of_date={LAST_DAY}",
        missing_fx_producer_and_response,
        timeout=180,
        fail_message="Missing exact-date FX must refuse valuation without rewriting booked cost",
    )
    supplied = client.ingest(
        "/ingest/fx-rates",
        {
            "fx_rates": [
                {"from_currency": "XTS", "to_currency": "USD", "rate_date": LAST_DAY, "rate": "2.5"}
            ]
        },
    )
    assert supplied.status_code == 202 and supplied.json()["accepted_count"] == 1
    original = {FIRST_DAY: first_holdings, LAST_DAY: holdings(LAST_DAY, "2.5")}
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
    replayed = {FIRST_DAY: holdings(FIRST_DAY, "2.5"), LAST_DAY: holdings(LAST_DAY, "3")}
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
        for day, fx in ((FIRST_DAY, "2.5"), (LAST_DAY, "3")):
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
    funded_cuts = {}
    commands = funded_cash_transactions(scenario)
    for stage, command in commands:
        admission = client.ingest("/ingest/transactions", {"transactions": [command]})
        assert admission.status_code == 202 and admission.json()["accepted_count"] == 1
        body = client.poll_for_data(
            f"{positions_url}?as_of_date={LAST_DAY}",
            lambda body, cut=stage: has_funded_cash_holdings(body, **scope, stage=cut),
            timeout=180,
            fail_message=f"Funded foreign cash failed independent financial cut {stage}",
        )
        funded_cuts[stage] = {"request": command, "acceptance": admission.json(), "holdings": body}
    funded_transactions = client.query(transactions_url).json()
    assert_funded_cash_transactions(funded_transactions, scenario)
    funded_redelivery = client.ingest(
        "/ingest/transactions", {"transactions": [command for _, command in commands]}
    )
    assert funded_redelivery.status_code == 202
    funded_replay = client.reprocess_transactions(
        [row["transaction_id"] for row in funded_transactions["transactions"]]
    )
    assert funded_replay.status_code == 202
    funded_idle = wait_for_pipeline_quiescence(
        timeout_seconds=120,
        poll_seconds=1,
        stable_cycles=2,
        quiet_seconds=8,
        snapshot_reader=lambda: read_pipeline_activity_snapshot(db_engine),
        last_activity_reader=lambda: read_pipeline_last_activity_at(db_engine),
    )
    funded_after_replay = client.query(f"{positions_url}?as_of_date={LAST_DAY}").json()
    assert has_funded_cash_holdings(funded_after_replay, **scope, stage="funded_interest")
    assert (
        funded_after_replay["positions"] == funded_cuts["funded_interest"]["holdings"]["positions"]
    )
    funded_transactions_after_replay = client.query(transactions_url).json()
    assert_funded_cash_transactions(funded_transactions_after_replay, scenario)
    # A separate USD book is admitted through the same real routes, with no FX-rate input.
    same_currency = seed_scenario(
        client, unique_suffix(), admit_instruments=admit_scenario_instruments, same_currency=True
    )
    funding = funded_cash_transactions(same_currency)[0][1]
    funding_response = client.ingest("/ingest/transactions", {"transactions": [funding]})
    assert funding_response.status_code == 202 and funding_response.json()["accepted_count"] == 1
    same_currency_scope = {key: same_currency[key] for key in ("portfolio", "equity", "cash")}
    same_currency_holdings = client.poll_for_data(
        f"/portfolios/{same_currency['portfolio']}/positions?as_of_date={LAST_DAY}",
        lambda body: has_same_currency_funded_holdings(body, **same_currency_scope),
        timeout=180,
        fail_message="Funded USD identity conversion must have zero FX P&L and exact base cost",
    )
    same_currency_transactions = client.query(
        f"/portfolios/{same_currency['portfolio']}/transactions?limit=50"
    ).json()
    same_currency_rows = same_currency_transactions["transactions"]
    assert len(same_currency_rows) == 3
    assert {row["transaction_id"] for row in same_currency_rows} == {
        same_currency["buy_id"],
        f"{same_currency['buy_id']}-CASHLEG",
        funding["transaction_id"],
    }
    assert all(Decimal(str(row["transaction_fx_rate"])) == 1 for row in same_currency_rows)
    child = next(row for row in same_currency_rows if row.get("originating_transaction_id"))
    assert child["originating_transaction_id"] == same_currency["buy_id"]
    assert child["settlement_cash_account_id"] == same_currency["cash"]
    with capsys.disabled():
        emit_test_output(
            "BOOKED_FX_CASH_ACCEPTANCE "
            + json.dumps(
                {
                    "source_commit": os.getenv("GITHUB_SHA"),
                    "scenario": scenario,
                    "original": original,
                    "missing_exact_date_fx": unavailable,
                    "missing_exact_date_fx_jobs": missing_jobs,
                    "supplied_exact_date_fx": supplied.json(),
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
                    "funded_cuts": funded_cuts,
                    "funded_transactions": funded_transactions,
                    "funded_redelivery": funded_redelivery.json(),
                    "funded_replay": funded_replay.json(),
                    "funded_quiescence": funded_idle,
                    "funded_after_replay": funded_after_replay,
                    "funded_transactions_after_replay": funded_transactions_after_replay,
                    "same_currency_scenario": same_currency,
                    "same_currency_funding": funding,
                    "same_currency_funding_acceptance": funding_response.json(),
                    "same_currency_holdings": same_currency_holdings,
                    "same_currency_transactions": same_currency_transactions,
                    "source_authority": (
                        "synthetic policy/price facts; legacy operational FX, "
                        "not qualified provider cut"
                    ),
                },
                sort_keys=True,
            )
        )
