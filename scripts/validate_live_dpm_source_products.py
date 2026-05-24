from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import httpx

DEFAULT_PORTFOLIO_ID = "PB_SG_GLOBAL_BAL_001"
EXPECTED_DPM_UNIVERSE_PORTFOLIO_IDS = (
    "PB_SG_GLOBAL_BAL_001",
    "PB_SG_GLOBAL_INC_002",
    "PB_SG_GLOBAL_GROWTH_003",
)
DEFAULT_MODEL_PORTFOLIO_ID = "MODEL_PB_SG_GLOBAL_BAL_DPM"
DEFAULT_MANDATE_ID = "MANDATE_PB_SG_GLOBAL_BAL_001"
DEFAULT_AS_OF_DATE = "2026-04-10"
DEFAULT_TENANT_ID = "tenant_sg_pb"
DEFAULT_ELIGIBILITY_IDS = ("FO_EQ_AAPL_US", "FO_PRIV_PRIVATE_CREDIT_A")
DEFAULT_MARKET_IDS = ("FO_EQ_AAPL_US", "FO_BOND_UST_2030", "FO_EQ_SAP_DE")
DEFAULT_FX_PAIRS = (("EUR", "USD"),)
EXPECTED_OPENAPI_PATHS = {
    "/integration/dpm/portfolio-universe/candidates",
    "/integration/model-portfolios/{model_portfolio_id}/targets",
    "/integration/portfolios/{portfolio_id}/mandate-binding",
    "/integration/portfolios/{portfolio_id}/client-restriction-profile",
    "/integration/portfolios/{portfolio_id}/sustainability-preference-profile",
    "/integration/instruments/eligibility-bulk",
    "/integration/portfolios/{portfolio_id}/tax-lots",
    "/integration/market-data/coverage",
    "/integration/portfolios/{portfolio_id}/dpm-source-readiness",
}


@dataclass(frozen=True)
class ProbeResult:
    name: str
    ok: bool
    details: dict[str, Any]


def _result(name: str, ok: bool, details: dict[str, Any]) -> ProbeResult:
    return ProbeResult(name=name, ok=ok, details=details)


def _json_body(response: httpx.Response) -> Any:
    try:
        return response.json() if response.content else {}
    except ValueError:
        return response.text[:500]


def _dict_body(body: Any) -> dict[str, Any]:
    return body if isinstance(body, dict) else {}


def _supportability_state(body: Any) -> str | None:
    if not isinstance(body, dict):
        return None
    supportability = body.get("supportability")
    if not isinstance(supportability, dict):
        return None
    state = supportability.get("state")
    return state if isinstance(state, str) else None


def _decimal(value: Any) -> Decimal | None:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _probe_openapi_dpm_source_routes(client: httpx.Client) -> ProbeResult:
    response = client.get("/openapi.json")
    body = _dict_body(_json_body(response))
    published_paths = set(body.get("paths", {}))
    missing_paths = sorted(EXPECTED_OPENAPI_PATHS - published_paths)
    return _result(
        "openapi_dpm_source_routes",
        response.status_code == 200 and not missing_paths,
        {
            "status_code": response.status_code,
            "missing_paths": missing_paths,
        },
    )


def _probe_model_targets(
    client: httpx.Client,
    *,
    model_portfolio_id: str,
    as_of_date: str,
    tenant_id: str,
) -> ProbeResult:
    response = client.post(
        f"/integration/model-portfolios/{model_portfolio_id}/targets",
        json={
            "as_of_date": as_of_date,
            "include_inactive_targets": False,
            "tenant_id": tenant_id,
        },
    )
    body = _json_body(response)
    body_dict = _dict_body(body)
    supportability = _dict_body(body_dict.get("supportability"))
    total_weight = _decimal(supportability.get("total_target_weight"))
    targets = body_dict.get("targets", [])
    target_count = len(targets) if isinstance(targets, list) else 0
    ok = (
        response.status_code == 200
        and body_dict.get("product_name") == "DpmModelPortfolioTarget"
        and _supportability_state(body_dict) == "READY"
        and target_count >= 2
        and total_weight is not None
        and Decimal("0.999") <= total_weight <= Decimal("1.001")
    )
    return _result(
        "dpm_model_targets_ready",
        ok,
        {
            "status_code": response.status_code,
            "product_name": body_dict.get("product_name"),
            "supportability_state": _supportability_state(body_dict),
            "target_count": target_count,
            "total_target_weight": str(total_weight) if total_weight is not None else None,
        },
    )


def _probe_dpm_portfolio_universe_candidates(
    client: httpx.Client,
    *,
    portfolio_id: str,
    model_portfolio_id: str,
    as_of_date: str,
    tenant_id: str,
) -> ProbeResult:
    response = client.post(
        "/integration/dpm/portfolio-universe/candidates",
        json={
            "as_of_date": as_of_date,
            "tenant_id": tenant_id,
            "booking_center_code": "Singapore",
            "model_portfolio_ids": [model_portfolio_id],
            "include_inactive_mandates": False,
            "page": {"page_size": 50},
        },
    )
    body = _json_body(response)
    body_dict = _dict_body(body)
    supportability = _dict_body(body_dict.get("supportability"))
    candidates = body_dict.get("candidates", [])
    candidate_rows = [row for row in candidates if isinstance(row, dict)]
    contains_portfolio = any(
        row.get("portfolio_id") == portfolio_id
        and row.get("model_portfolio_id") == model_portfolio_id
        for row in candidate_rows
    )
    returned_portfolio_ids = {
        str(row.get("portfolio_id")) for row in candidate_rows if row.get("portfolio_id")
    }
    missing_expected_portfolio_ids = sorted(
        set(EXPECTED_DPM_UNIVERSE_PORTFOLIO_IDS) - returned_portfolio_ids
    )
    return _result(
        "dpm_portfolio_universe_candidates_ready",
        response.status_code == 200
        and supportability.get("state") in {"READY", "DEGRADED"}
        and contains_portfolio
        and not missing_expected_portfolio_ids,
        {
            "status_code": response.status_code,
            "product_name": body_dict.get("product_name"),
            "supportability_state": supportability.get("state"),
            "candidate_count": len(candidate_rows),
            "contains_portfolio": contains_portfolio,
            "missing_expected_portfolio_ids": missing_expected_portfolio_ids,
            "next_page_token": _dict_body(body_dict.get("page")).get("next_page_token"),
        },
    )


def _probe_dpm_portfolio_universe_candidate_paging(
    client: httpx.Client,
    *,
    model_portfolio_id: str,
    as_of_date: str,
    tenant_id: str,
) -> ProbeResult:
    response = client.post(
        "/integration/dpm/portfolio-universe/candidates",
        json={
            "as_of_date": as_of_date,
            "tenant_id": tenant_id,
            "booking_center_code": "Singapore",
            "model_portfolio_ids": [model_portfolio_id],
            "include_inactive_mandates": False,
            "page": {"page_size": 1},
        },
    )
    body = _json_body(response)
    body_dict = _dict_body(body)
    candidates = body_dict.get("candidates", [])
    candidate_rows = [row for row in candidates if isinstance(row, dict)]
    page = _dict_body(body_dict.get("page"))
    next_page_token = page.get("next_page_token")
    second_response: httpx.Response | None = None
    second_body_dict: dict[str, Any] = {}
    second_candidate_rows: list[dict[str, Any]] = []
    second_page_token: Any = None
    if isinstance(next_page_token, str) and next_page_token:
        second_response = client.post(
            "/integration/dpm/portfolio-universe/candidates",
            json={
                "as_of_date": as_of_date,
                "tenant_id": tenant_id,
                "booking_center_code": "Singapore",
                "model_portfolio_ids": [model_portfolio_id],
                "include_inactive_mandates": False,
                "page": {"page_size": 1, "page_token": next_page_token},
            },
        )
        second_body = _json_body(second_response)
        second_body_dict = _dict_body(second_body)
        second_candidates = second_body_dict.get("candidates", [])
        second_candidate_rows = [row for row in second_candidates if isinstance(row, dict)]
        second_page_token = _dict_body(second_body_dict.get("page")).get("next_page_token")

    first_page_ids = {
        str(row.get("portfolio_id")) for row in candidate_rows if row.get("portfolio_id")
    }
    second_page_ids = {
        str(row.get("portfolio_id")) for row in second_candidate_rows if row.get("portfolio_id")
    }
    expected_second_page_ids = second_page_ids & set(EXPECTED_DPM_UNIVERSE_PORTFOLIO_IDS)
    duplicate_page_ids = sorted(first_page_ids & second_page_ids)
    return _result(
        "dpm_portfolio_universe_candidate_paging",
        response.status_code == 200
        and body_dict.get("product_name") == "DpmPortfolioUniverseCandidate"
        and len(candidate_rows) == 1
        and isinstance(next_page_token, str)
        and bool(next_page_token)
        and second_response is not None
        and second_response.status_code == 200
        and second_body_dict.get("product_name") == "DpmPortfolioUniverseCandidate"
        and len(second_candidate_rows) == 1
        and bool(expected_second_page_ids)
        and not duplicate_page_ids,
        {
            "status_code": response.status_code,
            "product_name": body_dict.get("product_name"),
            "candidate_count": len(candidate_rows),
            "first_page_portfolio_ids": sorted(first_page_ids),
            "next_page_token_present": bool(next_page_token),
            "second_status_code": second_response.status_code
            if second_response is not None
            else None,
            "second_product_name": second_body_dict.get("product_name"),
            "second_candidate_count": len(second_candidate_rows),
            "second_page_portfolio_ids": sorted(second_page_ids),
            "second_page_expected_portfolio_ids": sorted(expected_second_page_ids),
            "second_next_page_token_present": bool(second_page_token),
            "duplicate_page_portfolio_ids": duplicate_page_ids,
        },
    )


def _probe_mandate_binding(
    client: httpx.Client,
    *,
    portfolio_id: str,
    mandate_id: str,
    model_portfolio_id: str,
    as_of_date: str,
    tenant_id: str,
) -> ProbeResult:
    response = client.post(
        f"/integration/portfolios/{portfolio_id}/mandate-binding",
        json={
            "as_of_date": as_of_date,
            "tenant_id": tenant_id,
            "mandate_id": mandate_id,
            "include_policy_pack": True,
        },
    )
    body = _json_body(response)
    body_dict = _dict_body(body)
    ok = (
        response.status_code == 200
        and body_dict.get("product_name") == "DiscretionaryMandateBinding"
        and _supportability_state(body_dict) == "READY"
        and body_dict.get("mandate_type") == "discretionary"
        and body_dict.get("discretionary_authority_status") == "active"
        and body_dict.get("model_portfolio_id") == model_portfolio_id
        and bool(body_dict.get("mandate_objective"))
        and bool(body_dict.get("review_cadence"))
        and bool(body_dict.get("last_review_date"))
        and bool(body_dict.get("next_review_due_date"))
    )
    return _result(
        "dpm_mandate_binding_ready",
        ok,
        {
            "status_code": response.status_code,
            "product_name": body_dict.get("product_name"),
            "supportability_state": _supportability_state(body_dict),
            "mandate_type": body_dict.get("mandate_type"),
            "model_portfolio_id": body_dict.get("model_portfolio_id"),
            "mandate_objective_present": bool(body_dict.get("mandate_objective")),
            "review_cadence": body_dict.get("review_cadence"),
            "last_review_date": body_dict.get("last_review_date"),
            "next_review_due_date": body_dict.get("next_review_due_date"),
        },
    )


def _probe_instrument_eligibility(
    client: httpx.Client,
    *,
    as_of_date: str,
    tenant_id: str,
    security_ids: tuple[str, ...],
) -> ProbeResult:
    response = client.post(
        "/integration/instruments/eligibility-bulk",
        json={
            "as_of_date": as_of_date,
            "security_ids": list(security_ids),
            "tenant_id": tenant_id,
            "include_restricted_rationale": True,
        },
    )
    body = _json_body(response)
    body_dict = _dict_body(body)
    rows = body_dict.get("records", body_dict.get("eligibility", []))
    rows = rows if isinstance(rows, list) else []
    by_id = {row.get("security_id"): row for row in rows if isinstance(row, dict)}
    restricted = by_id.get("FO_PRIV_PRIVATE_CREDIT_A", {})
    ok = (
        response.status_code == 200
        and body_dict.get("product_name") == "InstrumentEligibilityProfile"
        and _supportability_state(body_dict) == "READY"
        and set(security_ids).issubset(by_id)
        and all(row.get("found") for row in by_id.values())
        and restricted.get("buy_allowed") is False
        and restricted.get("sell_allowed") is True
    )
    return _result(
        "dpm_instrument_eligibility_ready",
        ok,
        {
            "status_code": response.status_code,
            "product_name": body_dict.get("product_name"),
            "supportability_state": _supportability_state(body_dict),
            "requested_count": len(security_ids),
            "found_count": sum(1 for row in by_id.values() if row.get("found")),
            "restricted_buy_allowed": restricted.get("buy_allowed"),
            "restricted_sell_allowed": restricted.get("sell_allowed"),
        },
    )


def _probe_client_restrictions(
    client: httpx.Client,
    *,
    portfolio_id: str,
    mandate_id: str,
    as_of_date: str,
    tenant_id: str,
) -> ProbeResult:
    response = client.post(
        f"/integration/portfolios/{portfolio_id}/client-restriction-profile",
        json={
            "as_of_date": as_of_date,
            "tenant_id": tenant_id,
            "mandate_id": mandate_id,
            "include_inactive_restrictions": False,
        },
    )
    body = _json_body(response)
    body_dict = _dict_body(body)
    supportability = _dict_body(body_dict.get("supportability"))
    restrictions = body_dict.get("restrictions", [])
    restrictions = restrictions if isinstance(restrictions, list) else []
    restriction_codes = {
        row.get("restriction_code") for row in restrictions if isinstance(row, dict)
    }
    ok = (
        response.status_code == 200
        and body_dict.get("product_name") == "ClientRestrictionProfile"
        and supportability.get("state") == "READY"
        and "NO_PRIVATE_CREDIT_BUY" in restriction_codes
    )
    return _result(
        "dpm_client_restrictions_ready",
        ok,
        {
            "status_code": response.status_code,
            "product_name": body_dict.get("product_name"),
            "supportability_state": supportability.get("state"),
            "restriction_count": supportability.get("restriction_count"),
            "restriction_codes": sorted(code for code in restriction_codes if code),
        },
    )


def _probe_sustainability_preferences(
    client: httpx.Client,
    *,
    portfolio_id: str,
    mandate_id: str,
    as_of_date: str,
    tenant_id: str,
) -> ProbeResult:
    response = client.post(
        f"/integration/portfolios/{portfolio_id}/sustainability-preference-profile",
        json={
            "as_of_date": as_of_date,
            "tenant_id": tenant_id,
            "mandate_id": mandate_id,
            "include_inactive_preferences": False,
        },
    )
    body = _json_body(response)
    body_dict = _dict_body(body)
    supportability = _dict_body(body_dict.get("supportability"))
    preferences = body_dict.get("preferences", [])
    preferences = preferences if isinstance(preferences, list) else []
    preference_codes = {row.get("preference_code") for row in preferences if isinstance(row, dict)}
    ok = (
        response.status_code == 200
        and body_dict.get("product_name") == "SustainabilityPreferenceProfile"
        and supportability.get("state") == "READY"
        and "MIN_SUSTAINABLE_ALLOCATION" in preference_codes
    )
    return _result(
        "dpm_sustainability_preferences_ready",
        ok,
        {
            "status_code": response.status_code,
            "product_name": body_dict.get("product_name"),
            "supportability_state": supportability.get("state"),
            "preference_count": supportability.get("preference_count"),
            "preference_codes": sorted(code for code in preference_codes if code),
        },
    )


def _probe_tax_lots(
    client: httpx.Client,
    *,
    portfolio_id: str,
    as_of_date: str,
    tenant_id: str,
) -> ProbeResult:
    response = client.post(
        f"/integration/portfolios/{portfolio_id}/tax-lots",
        json={
            "as_of_date": as_of_date,
            "security_ids": ["FO_EQ_AAPL_US"],
            "lot_status_filter": "OPEN",
            "include_closed_lots": False,
            "page": {"page_size": 250, "page_token": None},
            "tenant_id": tenant_id,
        },
    )
    body = _json_body(response)
    body_dict = _dict_body(body)
    lots = body_dict.get("lots", [])
    lots = lots if isinstance(lots, list) else []
    ok = (
        response.status_code == 200
        and body_dict.get("product_name") == "PortfolioTaxLotWindow"
        and body_dict.get("portfolio_id") == portfolio_id
        and _supportability_state(body_dict) == "READY"
        and len(lots) >= 1
        and all(lot.get("tax_lot_status") == "OPEN" for lot in lots if isinstance(lot, dict))
    )
    return _result(
        "dpm_tax_lots_ready",
        ok,
        {
            "status_code": response.status_code,
            "product_name": body_dict.get("product_name"),
            "supportability_state": _supportability_state(body_dict),
            "lot_count": len(lots),
            "next_page_token": _dict_body(body_dict.get("page")).get("next_page_token"),
        },
    )


def _probe_market_data_coverage(
    client: httpx.Client,
    *,
    as_of_date: str,
    tenant_id: str,
    instrument_ids: tuple[str, ...],
    fx_pairs: tuple[tuple[str, str], ...],
) -> ProbeResult:
    response = client.post(
        "/integration/market-data/coverage",
        json={
            "as_of_date": as_of_date,
            "instrument_ids": list(instrument_ids),
            "currency_pairs": [
                {"from_currency": from_currency, "to_currency": to_currency}
                for from_currency, to_currency in fx_pairs
            ],
            "valuation_currency": "USD",
            "max_staleness_days": 5,
            "tenant_id": tenant_id,
        },
    )
    body = _json_body(response)
    body_dict = _dict_body(body)
    supportability = _dict_body(body_dict.get("supportability"))
    ok = (
        response.status_code == 200
        and body_dict.get("product_name") == "MarketDataCoverageWindow"
        and _supportability_state(body_dict) == "READY"
        and supportability.get("resolved_price_count") == len(instrument_ids)
        and supportability.get("resolved_fx_count") == len(fx_pairs)
        and not supportability.get("missing_instrument_ids")
        and not supportability.get("missing_currency_pairs")
        and not supportability.get("stale_instrument_ids")
        and not supportability.get("stale_currency_pairs")
    )
    return _result(
        "dpm_market_data_coverage_ready",
        ok,
        {
            "status_code": response.status_code,
            "product_name": body_dict.get("product_name"),
            "supportability_state": _supportability_state(body_dict),
            "resolved_price_count": supportability.get("resolved_price_count"),
            "resolved_fx_count": supportability.get("resolved_fx_count"),
            "missing_instrument_ids": supportability.get("missing_instrument_ids"),
            "stale_instrument_ids": supportability.get("stale_instrument_ids"),
            "missing_currency_pairs": supportability.get("missing_currency_pairs"),
            "stale_currency_pairs": supportability.get("stale_currency_pairs"),
        },
    )


def _probe_dpm_source_readiness(
    client: httpx.Client,
    *,
    portfolio_id: str,
    mandate_id: str,
    model_portfolio_id: str,
    as_of_date: str,
    tenant_id: str,
    instrument_ids: tuple[str, ...],
    fx_pairs: tuple[tuple[str, str], ...],
) -> ProbeResult:
    response = client.post(
        f"/integration/portfolios/{portfolio_id}/dpm-source-readiness",
        json={
            "as_of_date": as_of_date,
            "tenant_id": tenant_id,
            "mandate_id": mandate_id,
            "model_portfolio_id": model_portfolio_id,
            "instrument_ids": list(instrument_ids),
            "currency_pairs": [
                {"from_currency": from_currency, "to_currency": to_currency}
                for from_currency, to_currency in fx_pairs
            ],
            "valuation_currency": "USD",
            "max_staleness_days": 5,
        },
    )
    body = _json_body(response)
    body_dict = _dict_body(body)
    supportability = _dict_body(body_dict.get("supportability"))
    families = body_dict.get("families", [])
    families = families if isinstance(families, list) else []
    family_states = {
        family.get("family"): family.get("state") for family in families if isinstance(family, dict)
    }
    ok = (
        response.status_code == 200
        and body_dict.get("product_name") == "DpmSourceReadiness"
        and supportability.get("state") == "READY"
        and supportability.get("ready_family_count") == 5
        and family_states.get("mandate") == "READY"
        and family_states.get("model_targets") == "READY"
        and family_states.get("eligibility") == "READY"
        and family_states.get("tax_lots") == "READY"
        and family_states.get("market_data") == "READY"
    )
    return _result(
        "dpm_source_readiness_ready",
        ok,
        {
            "status_code": response.status_code,
            "product_name": body_dict.get("product_name"),
            "supportability_state": supportability.get("state"),
            "supportability_reason": supportability.get("reason"),
            "ready_family_count": supportability.get("ready_family_count"),
            "family_states": family_states,
        },
    )


def run_validation(
    control_base_url: str,
    *,
    portfolio_id: str = DEFAULT_PORTFOLIO_ID,
    model_portfolio_id: str = DEFAULT_MODEL_PORTFOLIO_ID,
    mandate_id: str = DEFAULT_MANDATE_ID,
    as_of_date: str = DEFAULT_AS_OF_DATE,
    tenant_id: str = DEFAULT_TENANT_ID,
    transport: httpx.BaseTransport | None = None,
) -> list[ProbeResult]:
    timeout = httpx.Timeout(30.0)
    with httpx.Client(base_url=control_base_url, timeout=timeout, transport=transport) as client:
        probes = [
            ("openapi_dpm_source_routes", lambda: _probe_openapi_dpm_source_routes(client)),
            (
                "dpm_model_targets_ready",
                lambda: _probe_model_targets(
                    client,
                    model_portfolio_id=model_portfolio_id,
                    as_of_date=as_of_date,
                    tenant_id=tenant_id,
                ),
            ),
            (
                "dpm_mandate_binding_ready",
                lambda: _probe_mandate_binding(
                    client,
                    portfolio_id=portfolio_id,
                    mandate_id=mandate_id,
                    model_portfolio_id=model_portfolio_id,
                    as_of_date=as_of_date,
                    tenant_id=tenant_id,
                ),
            ),
            (
                "dpm_portfolio_universe_candidates_ready",
                lambda: _probe_dpm_portfolio_universe_candidates(
                    client,
                    portfolio_id=portfolio_id,
                    model_portfolio_id=model_portfolio_id,
                    as_of_date=as_of_date,
                    tenant_id=tenant_id,
                ),
            ),
            (
                "dpm_portfolio_universe_candidate_paging",
                lambda: _probe_dpm_portfolio_universe_candidate_paging(
                    client,
                    model_portfolio_id=model_portfolio_id,
                    as_of_date=as_of_date,
                    tenant_id=tenant_id,
                ),
            ),
            (
                "dpm_instrument_eligibility_ready",
                lambda: _probe_instrument_eligibility(
                    client,
                    as_of_date=as_of_date,
                    tenant_id=tenant_id,
                    security_ids=DEFAULT_ELIGIBILITY_IDS,
                ),
            ),
            (
                "dpm_client_restrictions_ready",
                lambda: _probe_client_restrictions(
                    client,
                    portfolio_id=portfolio_id,
                    mandate_id=mandate_id,
                    as_of_date=as_of_date,
                    tenant_id=tenant_id,
                ),
            ),
            (
                "dpm_sustainability_preferences_ready",
                lambda: _probe_sustainability_preferences(
                    client,
                    portfolio_id=portfolio_id,
                    mandate_id=mandate_id,
                    as_of_date=as_of_date,
                    tenant_id=tenant_id,
                ),
            ),
            (
                "dpm_tax_lots_ready",
                lambda: _probe_tax_lots(
                    client,
                    portfolio_id=portfolio_id,
                    as_of_date=as_of_date,
                    tenant_id=tenant_id,
                ),
            ),
            (
                "dpm_market_data_coverage_ready",
                lambda: _probe_market_data_coverage(
                    client,
                    as_of_date=as_of_date,
                    tenant_id=tenant_id,
                    instrument_ids=DEFAULT_MARKET_IDS,
                    fx_pairs=DEFAULT_FX_PAIRS,
                ),
            ),
            (
                "dpm_source_readiness_ready",
                lambda: _probe_dpm_source_readiness(
                    client,
                    portfolio_id=portfolio_id,
                    mandate_id=mandate_id,
                    model_portfolio_id=model_portfolio_id,
                    as_of_date=as_of_date,
                    tenant_id=tenant_id,
                    instrument_ids=DEFAULT_MARKET_IDS,
                    fx_pairs=DEFAULT_FX_PAIRS,
                ),
            ),
        ]
        results: list[ProbeResult] = []
        for probe_name, probe in probes:
            try:
                results.append(probe())
            except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError) as exc:
                results.append(_result(probe_name, False, {"error": str(exc)}))
        return results


def summarize(results: list[ProbeResult]) -> dict[str, Any]:
    failures = [asdict(result) for result in results if not result.ok]
    return {
        "total": len(results),
        "failed": len(failures),
        "failures": failures,
        "results": [asdict(result) for result in results],
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate live RFC-087 DPM source-data products on lotus-core."
    )
    parser.add_argument(
        "--control-base-url",
        default="http://core-control.dev.lotus",
        help="lotus-core query-control-plane base URL.",
    )
    parser.add_argument("--portfolio-id", default=DEFAULT_PORTFOLIO_ID)
    parser.add_argument("--model-portfolio-id", default=DEFAULT_MODEL_PORTFOLIO_ID)
    parser.add_argument("--mandate-id", default=DEFAULT_MANDATE_ID)
    parser.add_argument("--as-of-date", default=DEFAULT_AS_OF_DATE)
    parser.add_argument("--tenant-id", default=DEFAULT_TENANT_ID)
    parser.add_argument("--json-output", type=Path)
    args = parser.parse_args()

    results = run_validation(
        args.control_base_url,
        portfolio_id=args.portfolio_id,
        model_portfolio_id=args.model_portfolio_id,
        mandate_id=args.mandate_id,
        as_of_date=args.as_of_date,
        tenant_id=args.tenant_id,
    )
    summary = summarize(results)
    rendered = json.dumps(summary, indent=2, sort_keys=True)
    print(rendered)
    if args.json_output is not None:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(rendered + "\n", encoding="utf-8")
    return 1 if summary["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
