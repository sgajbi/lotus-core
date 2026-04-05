from __future__ import annotations

from collections.abc import Iterable
from typing import Any

PARITY_SCENARIOS: tuple[dict[str, Any], ...] = (
    {
        "name": "fx_dependency_ready",
        "request_hash": "proposal_hash_fx_dep",
        "payload": {
            "portfolio_snapshot": {
                "portfolio_id": "pf_prop_fx_1",
                "base_currency": "SGD",
                "positions": [],
                "cash_balances": [{"currency": "SGD", "amount": "10000"}],
            },
            "market_data_snapshot": {
                "prices": [{"instrument_id": "US_EQ", "price": "100", "currency": "USD"}],
                "fx_rates": [{"pair": "USD/SGD", "rate": "1.35"}],
            },
            "shelf_entries": [{"instrument_id": "US_EQ", "status": "APPROVED"}],
            "options": {"enable_proposal_simulation": True},
            "proposed_cash_flows": [],
            "proposed_trades": [{"side": "BUY", "instrument_id": "US_EQ", "quantity": "50"}],
        },
        "expected": {
            "status": "READY",
            "intents": [
                {
                    "intent_type": "FX_SPOT",
                    "side": None,
                    "pair": "USD/SGD",
                    "instrument_id": None,
                    "quantity": None,
                    "buy_amount": "5000.00",
                    "sell_amount_estimated": "6750.00",
                    "dependencies": [],
                },
                {
                    "intent_type": "SECURITY_TRADE",
                    "side": "BUY",
                    "pair": None,
                    "instrument_id": "US_EQ",
                    "quantity": "50",
                    "buy_amount": None,
                    "sell_amount_estimated": None,
                    "dependencies": ["oi_fx_1"],
                },
            ],
            "after_total": "10000.0000",
            "after_cash": [("SGD", "3250.00"), ("USD", "0.00")],
            "after_positions": [("US_EQ", "50")],
            "rule_results": [
                ("CASH_BAND", "PASS", "OK"),
                ("DATA_QUALITY", "PASS", "OK"),
                ("INSUFFICIENT_CASH", "PASS", "OK"),
                ("MIN_TRADE_SIZE", "PASS", "OK"),
                ("NO_SHORTING", "PASS", "OK"),
                ("SINGLE_POSITION_MAX", "PASS", "NO_LIMIT_SET"),
            ],
            "gate_decision": {
                "gate": "COMPLIANCE_REVIEW_REQUIRED",
                "recommended_next_step": "COMPLIANCE_REVIEW",
                "reason_codes": [
                    "NEW_HIGH_SUITABILITY_ISSUE",
                    "NEW_MEDIUM_SUITABILITY_ISSUE",
                    "NEW_MEDIUM_SUITABILITY_ISSUE",
                ],
            },
            "suitability": {
                "persistent_count": 1,
                "issue_ids": [
                    "SUIT_SINGLE_POSITION_MAX",
                    "SUIT_DATA_QUALITY",
                    "SUIT_DATA_QUALITY",
                    "SUIT_CASH_BAND",
                ],
                "recommended_gate": "COMPLIANCE_REVIEW",
            },
            "drift_analysis": None,
            "lineage": {
                "request_hash": "proposal_hash_fx_dep",
                "simulation_contract_version": "advisory-simulation.v1",
            },
        },
    },
    {
        "name": "missing_fx_blocked",
        "request_hash": "proposal_hash_missing_fx_block",
        "payload": {
            "portfolio_snapshot": {
                "portfolio_id": "pf_prop_fx_5",
                "base_currency": "SGD",
                "positions": [],
                "cash_balances": [{"currency": "SGD", "amount": "10000"}],
            },
            "market_data_snapshot": {
                "prices": [{"instrument_id": "US_EQ", "price": "100", "currency": "USD"}],
                "fx_rates": [],
            },
            "shelf_entries": [{"instrument_id": "US_EQ", "status": "APPROVED"}],
            "options": {"enable_proposal_simulation": True, "block_on_missing_fx": True},
            "proposed_cash_flows": [],
            "proposed_trades": [{"side": "BUY", "instrument_id": "US_EQ", "quantity": "1"}],
        },
        "expected": {
            "status": "BLOCKED",
            "intents": [],
            "after_total": "10000",
            "after_cash": [("SGD", "10000"), ("USD", "0")],
            "after_positions": [],
            "rule_results": [
                ("CASH_BAND", "PASS", "OK"),
                ("DATA_QUALITY", "FAIL", "MISSING_DATA"),
                ("INSUFFICIENT_CASH", "PASS", "OK"),
                ("MIN_TRADE_SIZE", "PASS", "OK"),
                ("NO_SHORTING", "PASS", "OK"),
                (
                    "PROPOSAL_INPUT_GUARDS",
                    "FAIL",
                    "PROPOSAL_MISSING_FX_FOR_FUNDING",
                ),
                ("SINGLE_POSITION_MAX", "PASS", "NO_LIMIT_SET"),
            ],
            "gate_decision": {
                "gate": "BLOCKED",
                "recommended_next_step": "FIX_INPUT",
                "reason_codes": [
                    "DATA_QUALITY_MISSING_FX",
                    "HARD_RULE_FAIL:DATA_QUALITY",
                    "HARD_RULE_FAIL:PROPOSAL_INPUT_GUARDS",
                ],
            },
            "suitability": {
                "persistent_count": 1,
                "issue_ids": ["SUIT_CASH_BAND"],
                "recommended_gate": "NONE",
            },
            "drift_analysis": None,
            "lineage": {
                "request_hash": "proposal_hash_missing_fx_block",
                "simulation_contract_version": "advisory-simulation.v1",
            },
        },
    },
    {
        "name": "drift_reference_model",
        "request_hash": "proposal_hash_14c_asset",
        "payload": {
            "portfolio_snapshot": {
                "portfolio_id": "pf_prop_14c_a",
                "base_currency": "USD",
                "positions": [
                    {"instrument_id": "EQ_OLD", "quantity": "7"},
                    {"instrument_id": "BD_OLD", "quantity": "2"},
                ],
                "cash_balances": [{"currency": "USD", "amount": "100"}],
            },
            "market_data_snapshot": {
                "prices": [
                    {"instrument_id": "EQ_OLD", "price": "100", "currency": "USD"},
                    {"instrument_id": "BD_OLD", "price": "100", "currency": "USD"},
                    {"instrument_id": "EQ_NEW", "price": "100", "currency": "USD"},
                ],
                "fx_rates": [],
            },
            "shelf_entries": [
                {
                    "instrument_id": "EQ_OLD",
                    "status": "APPROVED",
                    "asset_class": "EQUITY",
                },
                {
                    "instrument_id": "BD_OLD",
                    "status": "APPROVED",
                    "asset_class": "FIXED_INCOME",
                },
                {
                    "instrument_id": "EQ_NEW",
                    "status": "APPROVED",
                    "asset_class": "EQUITY",
                },
            ],
            "options": {"enable_proposal_simulation": True},
            "proposed_cash_flows": [],
            "proposed_trades": [{"side": "BUY", "instrument_id": "EQ_NEW", "quantity": "1"}],
            "reference_model": {
                "model_id": "mdl_14c_1",
                "as_of": "2026-02-18",
                "base_currency": "USD",
                "asset_class_targets": [
                    {"asset_class": "EQUITY", "weight": "0.60"},
                    {"asset_class": "FIXED_INCOME", "weight": "0.35"},
                    {"asset_class": "CASH", "weight": "0.05"},
                ],
            },
        },
        "expected": {
            "status": "READY",
            "intents": [
                {
                    "intent_type": "SECURITY_TRADE",
                    "side": "BUY",
                    "pair": None,
                    "instrument_id": "EQ_NEW",
                    "quantity": "1",
                    "buy_amount": None,
                    "sell_amount_estimated": None,
                    "dependencies": [],
                }
            ],
            "after_total": "1000.0",
            "after_cash": [("USD", "0")],
            "after_positions": [("BD_OLD", "2"), ("EQ_NEW", "1"), ("EQ_OLD", "7")],
            "rule_results": [
                ("CASH_BAND", "PASS", "OK"),
                ("DATA_QUALITY", "PASS", "OK"),
                ("INSUFFICIENT_CASH", "PASS", "OK"),
                ("MIN_TRADE_SIZE", "PASS", "OK"),
                ("NO_SHORTING", "PASS", "OK"),
                ("SINGLE_POSITION_MAX", "PASS", "NO_LIMIT_SET"),
            ],
            "gate_decision": {
                "gate": "RISK_REVIEW_REQUIRED",
                "recommended_next_step": "RISK_REVIEW",
                "reason_codes": [
                    "NEW_MEDIUM_SUITABILITY_ISSUE",
                    "NEW_MEDIUM_SUITABILITY_ISSUE",
                ],
            },
            "suitability": {
                "persistent_count": 7,
                "issue_ids": [
                    "SUIT_DATA_QUALITY",
                    "SUIT_DATA_QUALITY",
                    "SUIT_SINGLE_POSITION_MAX",
                    "SUIT_SINGLE_POSITION_MAX",
                    "SUIT_CASH_BAND",
                    "SUIT_DATA_QUALITY",
                    "SUIT_DATA_QUALITY",
                    "SUIT_DATA_QUALITY",
                    "SUIT_DATA_QUALITY",
                ],
                "recommended_gate": "RISK_REVIEW",
            },
            "drift_analysis": {
                "reference_model_id": "mdl_14c_1",
                "asset_before": "0.150",
                "asset_after": "0.200",
                "instrument_present": False,
            },
            "lineage": {
                "request_hash": "proposal_hash_14c_asset",
                "simulation_contract_version": "advisory-simulation.v1",
            },
        },
    },
    {
        "name": "suitability_output",
        "request_hash": "proposal_hash_14d_default_suitability",
        "payload": {
            "portfolio_snapshot": {
                "portfolio_id": "pf_prop_14d_a",
                "base_currency": "USD",
                "positions": [{"instrument_id": "EQ_A", "quantity": "10"}],
                "cash_balances": [],
            },
            "market_data_snapshot": {
                "prices": [
                    {"instrument_id": "EQ_A", "price": "10", "currency": "USD"},
                    {"instrument_id": "EQ_B", "price": "10", "currency": "USD"},
                ],
                "fx_rates": [],
            },
            "shelf_entries": [
                {
                    "instrument_id": "EQ_A",
                    "status": "APPROVED",
                    "issuer_id": "ISSUER_X",
                    "liquidity_tier": "L1",
                },
                {
                    "instrument_id": "EQ_B",
                    "status": "APPROVED",
                    "issuer_id": "ISSUER_Y",
                    "liquidity_tier": "L2",
                },
            ],
            "options": {
                "enable_proposal_simulation": True,
                "suitability_thresholds": {
                    "single_position_max_weight": "0.80",
                    "issuer_max_weight": "1.0",
                    "max_weight_by_liquidity_tier": {},
                    "cash_band_min_weight": "0",
                    "cash_band_max_weight": "1",
                },
            },
            "proposed_cash_flows": [],
            "proposed_trades": [{"side": "BUY", "instrument_id": "EQ_B", "quantity": "1"}],
        },
        "expected": {
            "status": "BLOCKED",
            "intents": [],
            "after_total": "100.0",
            "after_cash": [("USD", "0")],
            "after_positions": [("EQ_A", "10")],
            "rule_results": [
                ("CASH_BAND", "PASS", "OK"),
                ("DATA_QUALITY", "PASS", "OK"),
                ("INSUFFICIENT_CASH", "PASS", "OK"),
                ("MIN_TRADE_SIZE", "PASS", "OK"),
                ("NO_SHORTING", "PASS", "OK"),
                (
                    "PROPOSAL_INPUT_GUARDS",
                    "FAIL",
                    "PROPOSAL_INSUFFICIENT_FUNDING_CASH",
                ),
                ("SINGLE_POSITION_MAX", "PASS", "NO_LIMIT_SET"),
            ],
            "gate_decision": {
                "gate": "BLOCKED",
                "recommended_next_step": "FIX_INPUT",
                "reason_codes": ["HARD_RULE_FAIL:PROPOSAL_INPUT_GUARDS"],
            },
            "suitability": {
                "persistent_count": 1,
                "issue_ids": ["SUIT_SINGLE_POSITION_MAX"],
                "recommended_gate": "NONE",
            },
            "drift_analysis": None,
            "lineage": {
                "request_hash": "proposal_hash_14d_default_suitability",
                "simulation_contract_version": "advisory-simulation.v1",
            },
        },
    },
)


def normalize_result_for_parity(result: Any) -> dict[str, Any]:
    return {
        "status": result.status,
        "intents": [
            {
                "intent_type": intent.intent_type,
                "side": getattr(intent, "side", None),
                "pair": getattr(intent, "pair", None),
                "instrument_id": getattr(intent, "instrument_id", None),
                "quantity": _decimal_to_string(getattr(intent, "quantity", None)),
                "buy_amount": _decimal_to_string(getattr(intent, "buy_amount", None)),
                "sell_amount_estimated": _decimal_to_string(
                    getattr(intent, "sell_amount_estimated", None)
                ),
                "dependencies": list(getattr(intent, "dependencies", [])),
            }
            for intent in result.intents
        ],
        "after_total": str(result.after_simulated.total_value.amount),
        "after_cash": sorted(
            (balance.currency, str(balance.amount))
            for balance in result.after_simulated.cash_balances
        ),
        "after_positions": sorted(
            (position.instrument_id, str(position.quantity))
            for position in result.after_simulated.positions
        ),
        "rule_results": sorted(
            (rule.rule_id, rule.status, rule.reason_code) for rule in result.rule_results
        ),
        "gate_decision": _normalize_gate_decision(result.gate_decision),
        "suitability": _normalize_suitability(result.suitability),
        "drift_analysis": _normalize_drift_analysis(result.drift_analysis),
        "lineage": {
            "request_hash": result.lineage.request_hash,
            "simulation_contract_version": result.lineage.simulation_contract_version,
        },
    }


def _decimal_to_string(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _normalize_gate_decision(gate_decision: Any) -> dict[str, Any] | None:
    if gate_decision is None:
        return None
    return {
        "gate": gate_decision.gate,
        "recommended_next_step": gate_decision.recommended_next_step,
        "reason_codes": [reason.reason_code for reason in gate_decision.reasons],
    }


def _normalize_suitability(suitability: Any) -> dict[str, Any] | None:
    if suitability is None:
        return None
    return {
        "persistent_count": suitability.summary.persistent_count,
        "issue_ids": [issue.issue_id for issue in suitability.issues],
        "recommended_gate": suitability.recommended_gate,
    }


def _normalize_drift_analysis(drift_analysis: Any) -> dict[str, Any] | None:
    if drift_analysis is None:
        return None
    return {
        "reference_model_id": drift_analysis.reference_model.model_id,
        "asset_before": str(drift_analysis.asset_class.drift_total_before),
        "asset_after": str(drift_analysis.asset_class.drift_total_after),
        "instrument_present": drift_analysis.instrument is not None,
    }


def iter_parity_scenarios() -> Iterable[dict[str, Any]]:
    return PARITY_SCENARIOS
