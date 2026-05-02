from __future__ import annotations

import json
import sys
from collections.abc import Callable

import httpx

from scripts import validate_live_dpm_source_products as validator


def _response(status_code: int, body: dict | str) -> httpx.Response:
    if isinstance(body, str):
        return httpx.Response(status_code, text=body)
    return httpx.Response(status_code, json=body)


def _openapi(paths: set[str] | None = None) -> dict:
    return {"paths": {path: {} for path in paths or validator.EXPECTED_OPENAPI_PATHS}}


def _model_targets() -> dict:
    return {
        "product_name": "DpmModelPortfolioTarget",
        "supportability": {"state": "READY", "total_target_weight": "1.0000000000"},
        "targets": [
            {"security_id": "FO_EQ_AAPL_US", "target_weight": "0.1400000000"},
            {"security_id": "FO_BOND_UST_2030", "target_weight": "0.1100000000"},
        ],
    }


def _mandate_binding() -> dict:
    return {
        "product_name": "DiscretionaryMandateBinding",
        "supportability": {"state": "READY"},
        "mandate_type": "discretionary",
        "discretionary_authority_status": "active",
        "model_portfolio_id": validator.DEFAULT_MODEL_PORTFOLIO_ID,
    }


def _eligibility() -> dict:
    return {
        "product_name": "InstrumentEligibilityProfile",
        "supportability": {"state": "READY"},
        "records": [
            {
                "security_id": "FO_EQ_AAPL_US",
                "found": True,
                "buy_allowed": True,
                "sell_allowed": True,
            },
            {
                "security_id": "FO_PRIV_PRIVATE_CREDIT_A",
                "found": True,
                "buy_allowed": False,
                "sell_allowed": True,
                "restriction_reasons": ["PRIVATE_ASSET_REVIEW"],
            },
        ],
    }


def _tax_lots() -> dict:
    return {
        "product_name": "PortfolioTaxLotWindow",
        "portfolio_id": validator.DEFAULT_PORTFOLIO_ID,
        "supportability": {"state": "READY"},
        "lots": [{"security_id": "FO_EQ_AAPL_US", "tax_lot_status": "OPEN"}],
        "page": {"next_page_token": None},
    }


def _market_data() -> dict:
    return {
        "product_name": "MarketDataCoverageWindow",
        "supportability": {
            "state": "READY",
            "resolved_price_count": 3,
            "resolved_fx_count": 1,
            "missing_instrument_ids": [],
            "stale_instrument_ids": [],
            "missing_currency_pairs": [],
            "stale_currency_pairs": [],
        },
    }


def _source_readiness() -> dict:
    return {
        "product_name": "DpmSourceReadiness",
        "supportability": {
            "state": "READY",
            "reason": "DPM_SOURCE_READINESS_READY",
            "ready_family_count": 5,
            "degraded_family_count": 0,
            "incomplete_family_count": 0,
            "unavailable_family_count": 0,
        },
        "families": [
            {"family": "mandate", "state": "READY"},
            {"family": "model_targets", "state": "READY"},
            {"family": "eligibility", "state": "READY"},
            {"family": "tax_lots", "state": "READY"},
            {"family": "market_data", "state": "READY"},
        ],
    }


def _handler(overrides: dict[str, tuple[int, dict | str]] | None = None) -> Callable:
    responses: dict[tuple[str, str], tuple[int, dict | str]] = {
        ("GET", "/openapi.json"): (200, _openapi()),
        (
            "POST",
            f"/integration/model-portfolios/{validator.DEFAULT_MODEL_PORTFOLIO_ID}/targets",
        ): (200, _model_targets()),
        (
            "POST",
            f"/integration/portfolios/{validator.DEFAULT_PORTFOLIO_ID}/mandate-binding",
        ): (200, _mandate_binding()),
        ("POST", "/integration/instruments/eligibility-bulk"): (200, _eligibility()),
        (
            "POST",
            f"/integration/portfolios/{validator.DEFAULT_PORTFOLIO_ID}/tax-lots",
        ): (200, _tax_lots()),
        ("POST", "/integration/market-data/coverage"): (200, _market_data()),
        (
            "POST",
            f"/integration/portfolios/{validator.DEFAULT_PORTFOLIO_ID}/dpm-source-readiness",
        ): (200, _source_readiness()),
    }
    for path, response in (overrides or {}).items():
        responses[("GET" if path == "/openapi.json" else "POST", path)] = response

    def handle(request: httpx.Request) -> httpx.Response:
        key = (request.method, request.url.path)
        status_code, body = responses[key]
        return _response(status_code, body)

    return handle


def _run(overrides: dict[str, tuple[int, dict | str]] | None = None) -> dict:
    results = validator.run_validation(
        "http://core-control.test",
        transport=httpx.MockTransport(_handler(overrides)),
    )
    return validator.summarize(results)


def test_live_dpm_source_validator_accepts_ready_canonical_products() -> None:
    summary = _run()

    assert summary["failed"] == 0
    assert [result["name"] for result in summary["results"]] == [
        "openapi_dpm_source_routes",
        "dpm_model_targets_ready",
        "dpm_mandate_binding_ready",
        "dpm_instrument_eligibility_ready",
        "dpm_tax_lots_ready",
        "dpm_market_data_coverage_ready",
        "dpm_source_readiness_ready",
    ]


def test_live_dpm_source_validator_reports_missing_openapi_route() -> None:
    paths = validator.EXPECTED_OPENAPI_PATHS - {"/integration/market-data/coverage"}
    summary = _run({"/openapi.json": (200, _openapi(paths))})

    assert summary["failed"] == 1
    assert summary["failures"][0]["name"] == "openapi_dpm_source_routes"
    assert summary["failures"][0]["details"]["missing_paths"] == [
        "/integration/market-data/coverage"
    ]


def test_live_dpm_source_validator_reports_stale_market_data_coverage() -> None:
    market_data = _market_data()
    market_data["supportability"] = {
        **market_data["supportability"],
        "state": "STALE",
        "resolved_price_count": 2,
        "stale_instrument_ids": ["FO_EQ_SAP_DE"],
    }

    summary = _run({"/integration/market-data/coverage": (200, market_data)})

    assert summary["failed"] == 1
    failure = summary["failures"][0]
    assert failure["name"] == "dpm_market_data_coverage_ready"
    assert failure["details"]["supportability_state"] == "STALE"
    assert failure["details"]["stale_instrument_ids"] == ["FO_EQ_SAP_DE"]


def test_live_dpm_source_validator_keeps_probe_name_on_bad_response_shape() -> None:
    summary = _run(
        {
            f"/integration/model-portfolios/{validator.DEFAULT_MODEL_PORTFOLIO_ID}/targets": (
                502,
                "upstream unavailable",
            )
        }
    )

    assert summary["failed"] == 1
    failure = summary["failures"][0]
    assert failure["name"] == "dpm_model_targets_ready"
    assert failure["details"]["status_code"] == 502
    assert failure["details"]["product_name"] is None


def test_live_dpm_source_validator_cli_writes_evidence_and_returns_failure(
    tmp_path, capsys, monkeypatch
) -> None:
    output = tmp_path / "evidence.json"
    results = [
        validator.ProbeResult("ready", True, {"status_code": 200}),
        validator.ProbeResult("stale", False, {"supportability_state": "STALE"}),
    ]
    monkeypatch.setattr(validator, "run_validation", lambda *_args, **_kwargs: results)
    monkeypatch.setattr(
        sys,
        "argv",
        ["validate_live_dpm_source_products.py", "--json-output", str(output)],
    )

    assert validator.main() == 1
    rendered = json.loads(output.read_text(encoding="utf-8"))
    assert rendered["failed"] == 1
    assert json.loads(capsys.readouterr().out)["failures"][0]["name"] == "stale"
