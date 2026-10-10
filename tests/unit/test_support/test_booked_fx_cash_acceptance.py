"""Adverse financial/qualification and ownership controls; no runtime execution."""

import copy
import json
from importlib import import_module
from subprocess import CompletedProcess

import pytest

from tests.test_support.booked_fx_cash_oracle import (
    FIRST_DAY,
    LAST_DAY,
    assert_linked_transactions,
    assert_portfolio_marks,
    assert_qualified_holdings,
    has_qualified_holdings,
)
from tests.test_support.booked_fx_cash_restart import restart_owned_query
from tests.test_support.booked_fx_cash_scenario import seed_scenario


def test_synthetic_http_scenario_respects_registered_ingestion_schemas():
    """DTO validation only: never HTTP, worker execution or runtime acceptance."""
    models = {
        "/ingest/portfolios": ("portfolio_dto", "PortfolioIngestionRequest"),
        "/ingest/instruments": ("instrument_dto", "InstrumentIngestionRequest"),
        "/ingest/reference/cash-accounts": (
            "reference_data_support_dto",
            "CashAccountMasterIngestionRequest",
        ),
        "/ingest/instrument-valuation-policy-assignments": (
            "reference_data_valuation_policy_dto",
            "InstrumentValuationPolicyAssignmentIngestionRequest",
        ),
        "/ingest/authoritative-market-price-source-facts": (
            "market_price_dto",
            "AuthoritativeMarketPriceSourceFactIngestionRequest",
        ),
        "/ingest/business-dates": ("business_date_dto", "BusinessDateIngestionRequest"),
        "/ingest/fx-rates": ("fx_rate_dto", "FxRateIngestionRequest"),
        "/ingest/transactions": (
            "transaction_ingestion_request_dto",
            "TransactionIngestionRequest",
        ),
        "/ingest/market-prices": ("market_price_dto", "MarketPriceIngestionRequest"),
    }
    calls = []

    class SchemaOnlyClient:
        tenant_id = "tenant_e2e"

        def ingest(self, endpoint, body):
            if endpoint == "/ingest/portfolios":
                for row in body["portfolios"]:
                    row["tenant_id"] = self.tenant_id  # Existing E2E client admission behavior.
            module, model = models[endpoint]
            getattr(import_module(f"src.services.ingestion_service.app.DTOs.{module}"), model)(
                **body
            )
            calls.append(endpoint)
            return self

        status_code = 202

        def json(self):
            return {"accepted_count": 1}

        def wait_for_admitted_portfolio(self, portfolio):
            assert portfolio.startswith("FX1158_P_")

        def poll_for_data(self, url, predicate):
            security = url.split("security_id=", 1)[1]
            assert predicate({"instruments": [{"security_id": security}]})

    scenario = seed_scenario(SchemaOnlyClient(), "DTO_ONLY")
    assert set(calls) == set(models)
    assert scenario["transaction"]["transaction_fx_rate"] == "2"


SCOPE = {"portfolio": "P", "equity": "EQ", "cash": "CASH"}


def payload(day=LAST_DAY, fx="2.5"):
    # Literal independently derived table, not values computed by the oracle under test.
    values = {
        (FIRST_DAY, "2"): (("2000", "0", "0", "0"), ("-2000", "0", "0", "0")),
        (LAST_DAY, "2.5"): (("2750", "750", "250", "500"), ("-2500", "-500", "0", "-500")),
        (LAST_DAY, "3"): (("3300", "1300", "300", "1000"), ("-3000", "-1000", "0", "-1000")),
    }
    price, local_mark, local_gain = (
        ("100", "1000", "0") if day == FIRST_DAY else ("110", "1100", "100")
    )
    rows = []
    for index, (security, quantity, basis, base_basis, mark, gain) in enumerate(
        (
            ("EQ", "10", "1000", "2000", local_mark, local_gain),
            ("CASH", "-1000", "-1000", "-2000", "-1000", "0"),
        )
    ):
        base_mark, base_gain, price_gain, fx_gain = values[day, fx][index]
        rows.append(
            {
                "security_id": security,
                "quantity": quantity,
                "cost_basis_local": basis,
                "cost_basis": base_basis,
                "currency": "XTS",
                "position_date": day,
                "reprocessing_status": "CURRENT",
                "valuation": {
                    "market_price": price if security == "EQ" else "1",
                    "market_value_local": mark,
                    "market_value": base_mark,
                    "unrealized_gain_loss_local": gain,
                    "unrealized_gain_loss": base_gain,
                    "unrealized_price_gain_loss": price_gain,
                    "unrealized_fx_gain_loss": fx_gain,
                },
            }
        )
    return {
        "portfolio_id": "P",
        "as_of_date": day,
        "positions": rows,
        "data_quality_status": "COMPLETE",
        "reconciliation_status": "COMPLETE",
        "freshness_status": "CURRENT",
        "source_evidence_current": True,
        "degradation": {"reason_codes": []},
        "content_hash": "sha256:" + "a" * 64,
        "source_digest": "sha256:" + "a" * 64,
        "source_refs": [f"lotus-core://source/HoldingsAsOf/P/{day}"],
    }


@pytest.mark.parametrize("day,fx", [(FIRST_DAY, "2"), (LAST_DAY, "2.5"), (LAST_DAY, "3")])
def test_independent_two_date_and_reference_corrected_cash_table(day, fx):
    assert_qualified_holdings(payload(day, fx), **SCOPE, day=day, reference_fx=fx)


@pytest.mark.parametrize(
    "path,value",
    [
        (("positions", 1, "cost_basis"), "-1000"),  # Original demonstrated defect.
        (("positions", 0, "cost_basis"), "2500"),  # Unconditional reference overwrite.
        (("positions", 1, "valuation", "unrealized_gain_loss"), "-1500"),
        (("positions", 0, "valuation", "unrealized_price_gain_loss"), "200"),
        (("positions", 1, "valuation", "unrealized_fx_gain_loss"), "500"),
        (("positions", 1, "quantity"), None),
        (("positions", 0, "valuation", "market_value"), "NaN"),
        (("positions", 0, "reprocessing_status"), "REPROCESSING"),
        (("positions", 0, "position_date"), FIRST_DAY),
        (("positions", 0, "currency"), "USD"),
        (("reconciliation_status",), "STALE"),
        (("data_quality_status",), "PARTIAL"),
        (("freshness_status",), "STALE"),
        (("source_evidence_current",), False),
        (("source_evidence_current",), 1),
        (("degradation", "reason_codes"), ["HOLDINGS_RECONCILIATION_STALE"]),
        (("source_refs",), ["lotus-core://source/HoldingsAsOf/FOREIGN/2026-04-10"]),
        (("source_digest",), "sha256:" + "b" * 64),
    ],
)
def test_financial_or_authority_mutation_never_qualifies(path, value):
    body = payload()
    target = body
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    assert not has_qualified_holdings(body, **SCOPE, day=LAST_DAY, reference_fx="2.5")


def test_duplicate_security_cannot_hide_missing_cash_position():
    body = payload()
    body["positions"] = [body["positions"][0], copy.deepcopy(body["positions"][0])]
    assert not has_qualified_holdings(body, **SCOPE, day=LAST_DAY, reference_fx="2.5")


def transactions():
    return {
        "transactions": [
            {
                "transaction_id": "BUY",
                "security_id": "EQ",
                "cash_entry_mode": "AUTO_GENERATE",
                "transaction_fx_rate": "2",
            },
            {
                "transaction_id": "BUY-CASHLEG",
                "security_id": "CASH",
                "originating_transaction_id": "BUY",
                "transaction_fx_rate": "2",
            },
        ]
    }


@pytest.mark.parametrize("mutation", ["duplicate_child", "foreign_parent", "changed_rate"])
def test_replay_must_preserve_exactly_one_linked_cash_effect(mutation):
    body = transactions()
    assert_linked_transactions(body, buy_id="BUY", equity="EQ", cash="CASH")
    if mutation == "duplicate_child":
        body["transactions"].append(copy.deepcopy(body["transactions"][1]))
    elif mutation == "foreign_parent":
        body["transactions"][1]["originating_transaction_id"] = "FOREIGN"
    else:
        body["transactions"][1]["transaction_fx_rate"] = "2.5"
    with pytest.raises(AssertionError):
        assert_linked_transactions(body, buy_id="BUY", equity="EQ", cash="CASH")


def test_cash_and_security_net_wealth_agrees_with_independent_timeseries():
    body = {
        "data_quality_status": "COMPLETE",
        "freshness_status": "CURRENT",
        "source_evidence_current": True,
        "reporting_currency": "USD",
        "portfolio_currency": "USD",
        "page": {"next_page_token": None},
        "observations": [
            {
                "valuation_date": FIRST_DAY,
                "beginning_market_value": "0",
                "ending_market_value": "0",
                "valuation_status": "final",
            },
            {
                "valuation_date": LAST_DAY,
                "beginning_market_value": "0",
                "ending_market_value": "250",
                "valuation_status": "final",
            },
        ],
    }
    assert_portfolio_marks(body, last_fx="2.5")
    body["observations"][1]["ending_market_value"] = "2750"  # Omitted negative cash.
    with pytest.raises(AssertionError):
        assert_portfolio_marks(body, last_fx="2.5")


class RuntimeRecorder:
    def __init__(self, *, foreign=False, unchanged_generation=False, exit_code=0):
        self.foreign = foreign
        self.unchanged_generation = unchanged_generation
        self.exit_code = exit_code
        self.state, self.calls = "before", []

    def __call__(self, command, **kwargs):
        assert kwargs["check"] is True and kwargs["timeout"] > 0
        self.calls.append(command)
        result = ""
        if command[-3:] == ["ps", "-q", "query_service"]:
            result = "container-1\n"
        elif command[:2] == ["docker", "inspect"]:
            running = self.state != "stopped"
            result = json.dumps(
                [
                    {
                        "Id": "container-1",
                        "Image": "immutable-image-1",
                        "Config": {
                            "Labels": {
                                "com.docker.compose.project": "foreign"
                                if self.foreign
                                else "owned",
                                "com.docker.compose.service": "query_service",
                            }
                        },
                        "State": {
                            "Running": running,
                            "Status": "running" if running else "exited",
                            "ExitCode": self.exit_code,
                            "StartedAt": "generation-2"
                            if self.state == "after" and not self.unchanged_generation
                            else "generation-1",
                        },
                    }
                ]
            )
        elif command[-2:] == ["stop", "query_service"]:
            self.state = "stopped"
        elif "up" in command:
            self.state = "after"
        return CompletedProcess(command, 0, result, "")


def test_owned_actual_generation_is_required_and_only_query_service_mutated():
    runner = RuntimeRecorder()
    ready = []
    result = restart_owned_query(
        project="owned", compose_file="owned.yml", ready=lambda: ready.append(True), runner=runner
    )
    assert result["before_started_at"] != result["after_started_at"]
    assert result["stopped_exit_code"] == 0 and result["healthy_restore"] is True
    assert ready == [True]
    assert [command[-2:] for command in runner.calls if "stop" in command] == [
        ["stop", "query_service"]
    ]
    assert runner.state == "after"


def test_foreign_container_refuses_before_any_runtime_mutation():
    runner = RuntimeRecorder(foreign=True)
    with pytest.raises(AssertionError):
        restart_owned_query(
            project="owned", compose_file="owned.yml", ready=lambda: None, runner=runner
        )
    assert all("stop" not in command and "up" not in command for command in runner.calls)


@pytest.mark.parametrize("kwargs", [{"unchanged_generation": True}, {"exit_code": 137}])
def test_missing_restart_or_nonzero_exit_fails_but_restores_owned_service(kwargs):
    runner = RuntimeRecorder(**kwargs)
    with pytest.raises(AssertionError):
        restart_owned_query(
            project="owned", compose_file="owned.yml", ready=lambda: None, runner=runner
        )
    assert runner.state == "after"
