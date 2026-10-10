"""Adverse financial/qualification and ownership controls; no runtime execution."""

import copy
import json
from decimal import Decimal
from importlib import import_module
from subprocess import CompletedProcess

import pytest

from tests.e2e.test_booked_fx_cash_acceptance import admit_scenario_instruments
from tests.test_support.booked_fx_cash_oracle import (
    FIRST_DAY,
    LAST_DAY,
    assert_funded_cash_transactions,
    assert_linked_transactions,
    assert_portfolio_marks,
    assert_qualified_holdings,
    has_funded_cash_holdings,
    has_missing_valuation_fx,
    has_qualified_holdings,
    has_same_currency_funded_holdings,
)
from tests.test_support.booked_fx_cash_restart import restart_owned_query
from tests.test_support.booked_fx_cash_scenario import funded_cash_transactions, seed_scenario


@pytest.mark.parametrize("admission_mode", ["valid", "omitted", "unsettled"])
@pytest.mark.parametrize("same_currency", [False, True])
def test_synthetic_http_scenario_respects_registered_ingestion_schemas(
    admission_mode, same_currency
):
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

        def __init__(self):
            self.portfolio_ready = False
            self.admitted, self.settled = set(), set()

        def ingest(self, endpoint, body):
            if endpoint == "/ingest/fx-rates":
                assert body["fx_rates"] == [
                    {"from_currency": "XTS", "to_currency": "USD", "rate_date": day, "rate": "2.5"}
                    for day in (FIRST_DAY,)
                ]
            if endpoint == "/ingest/portfolios":
                for row in body["portfolios"]:
                    row["tenant_id"] = self.tenant_id  # Existing E2E client admission behavior.
            elif endpoint == "/ingest/instruments":
                assert self.portfolio_ready
                self.admitted = {row["security_id"] for row in body["instruments"]}
            else:
                assert self.portfolio_ready and len(self.admitted) == 2
                assert (
                    self.settled == self.admitted
                )  # Facts/transactions cannot overtake references.
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
            assert calls == ["/ingest/portfolios"]
            self.portfolio_ready = True

        def poll_for_data(self, url, predicate):
            assert url.startswith("/instruments/?security_id=")
            security = url.split("security_id=", 1)[1]
            assert security in self.admitted
            assert not predicate({"instruments": []})
            assert not predicate({"instruments": [{"security_id": "FOREIGN"}]})
            assert predicate({"instruments": [{"security_id": security}]})
            if admission_mode != "unsettled":
                self.settled.add(security)

    admission = (lambda *_: None) if admission_mode == "omitted" else admit_scenario_instruments
    if admission_mode != "valid":
        with pytest.raises(AssertionError):
            seed_scenario(
                SchemaOnlyClient(),
                "DTO_ONLY",
                admit_instruments=admission,
                same_currency=same_currency,
            )
        assert "/ingest/transactions" not in calls
        return
    scenario = seed_scenario(
        SchemaOnlyClient(), "DTO_ONLY", admit_instruments=admission, same_currency=same_currency
    )
    assert set(calls) == set(models) - ({"/ingest/fx-rates"} if same_currency else set())
    assert scenario["transaction"]["transaction_fx_rate"] == ("1" if same_currency else "2")
    assert scenario["transaction"]["trade_currency"] == ("USD" if same_currency else "XTS")


def test_scenario_requires_explicit_instrument_admission_owner():
    with pytest.raises(TypeError, match="admit_instruments"):
        seed_scenario(object(), "NO_OWNER")


SCOPE = {"portfolio": "P", "equity": "EQ", "cash": "CASH"}


def payload(day=LAST_DAY, fx="2.5"):
    # Literal independently derived table, not values computed by the oracle under test.
    values = {
        (FIRST_DAY, "2"): (("2000", "0", "0", "0"), ("-2000", "0", "0", "0")),
        (FIRST_DAY, "2.5"): (("2500", "500", "0", "500"), ("-2500", "-500", "0", "-500")),
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


@pytest.mark.parametrize(
    "day,fx", [(FIRST_DAY, "2"), (FIRST_DAY, "2.5"), (LAST_DAY, "2.5"), (LAST_DAY, "3")]
)
def test_independent_two_date_and_reference_corrected_cash_table(day, fx):
    assert_qualified_holdings(payload(day, fx), **SCOPE, day=day, reference_fx=fx)


@pytest.mark.parametrize("mutation", [None, "unrelated", "complete", "fabricated_mark", "basis"])
def test_missing_exact_date_fx_requires_specific_lineage_and_no_fabricated_economics(mutation):
    body = payload()
    body["data_quality_status"] = "PARTIAL"
    body["degradation"]["reason_codes"] = ["VALUATION_CURRENCY_LINEAGE_MISSING"]
    for row in body["positions"]:
        row["valuation"]["market_value"] = None
        row["valuation"]["unrealized_gain_loss"] = None
    if mutation == "unrelated":
        body["degradation"]["reason_codes"] = ["VALUATION_PENDING"]
    elif mutation == "complete":
        body["data_quality_status"] = "COMPLETE"
    elif mutation == "fabricated_mark":
        body["positions"][1]["valuation"]["market_value"] = "-2500"
    elif mutation == "basis":
        body["positions"][1]["cost_basis"] = "-1000"
    assert has_missing_valuation_fx(body, **SCOPE) is (mutation is None)


@pytest.mark.parametrize(
    "stage", ["funded_buy", "funded_fee_buy", "funded_sell", "funded_income", "funded_interest"]
)
def test_funded_cash_literal_tables_and_meaningful_adverse_controls(stage):
    body = payload(LAST_DAY, "3")
    # Independent literals, not generated from the oracle's expected table.
    tables = {
        "funded_buy": [
            ("10", "1000", "2000", "1100", "3300", "100", "1300", "300", "1000"),
            ("1000", "1000", "2000", "1000", "3000", "0", "1000", "0", "1000"),
        ],
        "funded_fee_buy": [
            ("11", "1102", "2204", "1210", "3630", "108", "1426", "324", "1102"),
            ("898", "898", "1796", "898", "2694", "0", "898", "0", "898"),
        ],
        "funded_sell": [
            ("6", "602", "1204", "660", "1980", "58", "776", "174", "602"),
            ("1446", "1446", "2892", "1446", "4338", "0", "1446", "0", "1446"),
        ],
        "funded_income": [
            ("6", "602", "1204", "660", "1980", "58", "776", "174", "602"),
            ("1544", "1544", "3088", "1544", "4632", "0", "1544", "0", "1544"),
        ],
        "funded_interest": [
            ("6", "602", "1204", "660", "1980", "58", "776", "174", "602"),
            ("1592", "1592", "3184", "1592", "4776", "0", "1592", "0", "1592"),
        ],
    }
    fields = (
        "market_value_local",
        "market_value",
        "unrealized_gain_loss_local",
        "unrealized_gain_loss",
        "unrealized_price_gain_loss",
        "unrealized_fx_gain_loss",
    )
    for row, values in zip(body["positions"], tables[stage], strict=True):
        row.update(zip(("quantity", "cost_basis_local", "cost_basis"), values[:3], strict=True))
        row["valuation"].update(zip(fields, values[3:], strict=True))
    assert has_funded_cash_holdings(body, **SCOPE, stage=stage)
    for key, value in (("cost_basis", "1000"), ("quantity", "-1000")):
        wrong = copy.deepcopy(body)
        wrong["positions"][1][key] = value
        assert not has_funded_cash_holdings(wrong, **SCOPE, stage=stage)
    wrong = copy.deepcopy(body)
    wrong["positions"][1]["valuation"]["unrealized_fx_gain_loss"] = "0"
    assert not has_funded_cash_holdings(wrong, **SCOPE, stage=stage)


@pytest.mark.parametrize(
    "mutation", [None, "foreign_currency", "wrong_basis", "nonzero_fx", "negative_cash"]
)
def test_same_currency_funded_control_requires_identity_cost_and_zero_fx_pnl(mutation):
    body = payload()
    for index, (quantity, mark, gain) in enumerate((("10", "1100", "100"), ("1000", "1000", "0"))):
        row = body["positions"][index]
        row.update(currency="USD", quantity=quantity, cost_basis="1000", cost_basis_local="1000")
        row["valuation"].update(
            market_value_local=mark,
            market_value=mark,
            unrealized_gain_loss_local=gain,
            unrealized_gain_loss=gain,
            unrealized_price_gain_loss=gain,
            unrealized_fx_gain_loss="0",
        )
    if mutation == "foreign_currency":
        body["positions"][1]["currency"] = "XTS"
    elif mutation == "wrong_basis":
        body["positions"][1]["cost_basis"] = "2000"
    elif mutation == "nonzero_fx":
        body["positions"][1]["valuation"]["unrealized_fx_gain_loss"] = "1"
    elif mutation == "negative_cash":
        body["positions"][1]["quantity"] = "-1000"
    assert has_same_currency_funded_holdings(body, **SCOPE) is (mutation is None)


@pytest.mark.parametrize("currency,rate", [("XTS", "2"), ("USD", "1")])
def test_funded_commands_use_public_schema_trade_currency_fees_and_distinct_settlement_dates(
    currency, rate
):
    from portfolio_common.events import TransactionEvent

    from src.services.ingestion_service.app.DTOs.transaction_model_dto import Transaction
    from src.services.portfolio_transaction_processing_service.app.domain.transaction import (
        build_generated_settlement_cash_leg,
    )
    from src.services.portfolio_transaction_processing_service.app.infrastructure import (
        transaction_mapping,
    )

    scenario = {
        **SCOPE,
        "buy_id": "BUY",
        "transaction": {
            "transaction_id": "BUY",
            "portfolio_id": "P",
            "instrument_id": "EQ",
            "security_id": "EQ",
            "transaction_date": f"{FIRST_DAY}T10:00:00Z",
            "settlement_date": f"{FIRST_DAY}T10:00:00Z",
            "transaction_type": "BUY",
            "quantity": "10",
            "price": "100",
            "gross_transaction_amount": "1000",
            "trade_currency": currency,
            "currency": currency,
            "transaction_fx_rate": rate,
            "cash_entry_mode": "AUTO_GENERATE",
            "settlement_cash_account_id": "CASH",
            "settlement_cash_instrument_id": "CASH",
        },
    }
    commands = funded_cash_transactions(scenario)
    assert [stage for stage, _ in commands] == [
        "funded_buy",
        "funded_fee_buy",
        "funded_sell",
        "funded_income",
        "funded_interest",
    ]
    models = [Transaction(**command) for _, command in commands]
    assert models[0].transaction_type == "DEPOSIT" and models[0].security_id == "CASH"
    assert str(models[0].quantity) == "2000"
    assert models[0].trade_currency == currency and models[0].transaction_fx_rate == Decimal(rate)
    assert models[1].transaction_date.date().isoformat() == LAST_DAY
    for model in models[2:]:
        assert model.transaction_date.date().isoformat() == FIRST_DAY
    for model in models[1:]:
        assert model.settlement_date.date().isoformat() == LAST_DAY
        assert model.trade_currency == currency and model.trade_fee == 2
        assert model.transaction_fx_rate == Decimal(rate)
    for model, amount, base in zip(
        models[1:], ("102", "548", "98", "48"), ("-102", "548", "98", "48"), strict=True
    ):
        event = TransactionEvent(
            **model.model_dump(),
            tenant_id="synthetic-fx-authority",
            transaction_fx_rate_origin="SOURCE_BOOKED",
        )
        child = build_generated_settlement_cash_leg(
            transaction_mapping.booked_transaction.to_booked_transaction(event)
        )
        assert child.gross_transaction_amount == Decimal(amount)
        assert child.net_cost == Decimal(base) * Decimal(rate)
        assert child.transaction_date.date().isoformat() == LAST_DAY
        assert child.trade_currency == currency and child.transaction_fx_rate == Decimal(rate)
        assert child.transaction_fx_rate_origin == "SOURCE_BOOKED" and child.trade_fee == 0


@pytest.mark.parametrize(
    "mutation", [None, "duplicate_child", "wrong_fee", "wrong_date", "wrong_pnl", "wrong_account"]
)
def test_funded_transaction_proof_rejects_duplicate_fee_date_disposal_and_account_errors(mutation):
    parents = ("BUY", "BUY-FEE-BUY", "BUY-SELL", "BUY-DIVIDEND", "BUY-INTEREST")
    rows = [{"transaction_id": "BUY-FUND", "transaction_fx_rate": "2"}]
    for parent, amount, direction in zip(
        parents,
        ("1000", "102", "548", "98", "48"),
        ("OUTFLOW", "OUTFLOW", "INFLOW", "INFLOW", "INFLOW"),
        strict=True,
    ):
        day = FIRST_DAY if parent == "BUY" else LAST_DAY
        rows.extend(
            [
                {
                    "transaction_id": parent,
                    "transaction_fx_rate": "2",
                    "trade_fee": "2",
                    "trade_currency": "XTS",
                    "realized_gain_loss": "96",
                    "realized_gain_loss_local": "48",
                },
                {
                    "transaction_id": f"{parent}-CASHLEG",
                    "transaction_fx_rate": "2",
                    "originating_transaction_id": parent,
                    "security_id": "CASH",
                    "trade_fee": "0",
                    "settlement_cash_account_id": "CASH",
                    "movement_direction": direction,
                    "gross_transaction_amount": amount,
                    "transaction_date": f"{day}T10:00:00Z",
                    "settlement_date": f"{day}T10:00:00Z",
                },
            ]
        )
    if mutation == "duplicate_child":
        rows.append(copy.deepcopy(rows[-1]))
    elif mutation == "wrong_fee":
        rows[-1]["trade_fee"] = "2"
    elif mutation == "wrong_date":
        rows[-1]["transaction_date"] = f"{FIRST_DAY}T18:00:00Z"
    elif mutation == "wrong_pnl":
        rows[5]["realized_gain_loss"] = "100"
    elif mutation == "wrong_account":
        rows[-1]["settlement_cash_account_id"] = "FOREIGN"
    if mutation is None:
        assert_funded_cash_transactions({"transactions": rows}, {**SCOPE, "buy_id": "BUY"})
    else:
        with pytest.raises(AssertionError):
            assert_funded_cash_transactions({"transactions": rows}, {**SCOPE, "buy_id": "BUY"})


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
