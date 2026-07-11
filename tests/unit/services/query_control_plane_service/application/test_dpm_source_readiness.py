"""Aggregate application policy tests for DPM source readiness."""

from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.services.query_control_plane_service.app.application.dpm_source_readiness import readiness
from src.services.query_control_plane_service.app.contracts.dpm_source_readiness import (
    DpmSourceFamilyReadiness,
    DpmSourceReadinessRequest,
)

GENERATED_AT = datetime(2026, 4, 10, 12, tzinfo=UTC)
EARLIER_EVIDENCE = datetime(2026, 4, 10, 9, tzinfo=UTC)
LATEST_EVIDENCE = datetime(2026, 4, 10, 10, tzinfo=UTC)


def _request() -> DpmSourceReadinessRequest:
    return DpmSourceReadinessRequest(
        as_of_date=date(2026, 4, 10),
        tenant_id="tenant-1",
        instrument_ids=["HELD_1"],
        valuation_currency="SGD",
    )


def _family(
    family: str,
    state: str = "READY",
) -> DpmSourceFamilyReadiness:
    return DpmSourceFamilyReadiness(
        family=family,
        product_name=f"{family}-product",
        state=state,
        reason=f"{family.upper()}_{state}",
        evidence_count=1,
    )


def _ready_families() -> list[DpmSourceFamilyReadiness]:
    return [
        _family("mandate"),
        _family("model_targets"),
        _family("eligibility"),
        _family("tax_lots"),
        _family("market_data"),
    ]


def test_all_ready_families_produce_current_deterministic_aggregate_proof() -> None:
    kwargs = {
        "portfolio_id": "PB_SG_GLOBAL_BAL_001",
        "request": _request(),
        "identity": readiness.DpmSourceIdentity("MANDATE_1", "MODEL_1"),
        "evaluated_instrument_ids": ["HELD_1", "TARGET_1"],
        "families": _ready_families(),
        "source_responses": (
            SimpleNamespace(latest_evidence_timestamp=EARLIER_EVIDENCE),
            SimpleNamespace(latest_evidence_timestamp=LATEST_EVIDENCE),
        ),
    }
    first = readiness.build_dpm_source_readiness_response(
        **kwargs,
        generated_at=GENERATED_AT,
    )
    second = readiness.build_dpm_source_readiness_response(
        **kwargs,
        generated_at=datetime(2026, 4, 10, 13, tzinfo=UTC),
    )

    assert first.supportability.state == "READY"
    assert first.latest_evidence_timestamp == LATEST_EVIDENCE
    assert first.source_evidence_current is True
    assert first.freshness_status == "CURRENT"
    assert first.content_hash == second.content_hash
    assert first.source_batch_fingerprint == first.content_hash == first.source_digest


@pytest.mark.parametrize(
    ("family_state", "expected_state"),
    [
        ("DEGRADED", "DEGRADED"),
        ("INCOMPLETE", "INCOMPLETE"),
        ("UNAVAILABLE", "UNAVAILABLE"),
    ],
)
def test_non_ready_family_prevents_current_aggregate_claim(
    family_state: str,
    expected_state: str,
) -> None:
    families = _ready_families()
    families[-1] = _family("market_data", family_state)

    response = readiness.build_dpm_source_readiness_response(
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        request=_request(),
        identity=readiness.DpmSourceIdentity("MANDATE_1", "MODEL_1"),
        evaluated_instrument_ids=["HELD_1"],
        families=families,
        source_responses=(SimpleNamespace(latest_evidence_timestamp=LATEST_EVIDENCE),),
        generated_at=GENERATED_AT,
    )

    assert response.supportability.state == expected_state
    assert response.source_evidence_current is False
    assert response.freshness_status == "PARTIAL"


def test_worst_family_state_precedence_is_fail_closed() -> None:
    families = _ready_families()
    families[1] = _family("model_targets", "DEGRADED")
    families[2] = _family("eligibility", "INCOMPLETE")
    families[3] = _family("tax_lots", "UNAVAILABLE")

    supportability = readiness._aggregate_supportability(families)

    assert supportability.state == "UNAVAILABLE"
    assert supportability.ready_family_count == 2
    assert supportability.degraded_family_count == 1
    assert supportability.incomplete_family_count == 1
    assert supportability.unavailable_family_count == 1


@pytest.mark.asyncio
async def test_service_resolves_identity_unions_target_scope_and_orders_families() -> None:
    mandates = SimpleNamespace(
        resolve=AsyncMock(
            return_value=SimpleNamespace(
                mandate_id="MANDATE_1",
                model_portfolio_id="MODEL_FROM_MANDATE",
                latest_evidence_timestamp=EARLIER_EVIDENCE,
                supportability=SimpleNamespace(
                    state="READY",
                    reason="MANDATE_BINDING_READY",
                    missing_data_families=[],
                ),
            )
        )
    )
    models = SimpleNamespace(
        resolve=AsyncMock(
            return_value=SimpleNamespace(
                targets=[SimpleNamespace(instrument_id="TARGET_1")],
                latest_evidence_timestamp=LATEST_EVIDENCE,
                supportability=SimpleNamespace(
                    state="READY",
                    reason="MODEL_TARGETS_READY",
                    target_count=1,
                ),
            )
        )
    )
    eligibility = SimpleNamespace(
        resolve=AsyncMock(
            return_value=SimpleNamespace(
                latest_evidence_timestamp=LATEST_EVIDENCE,
                supportability=SimpleNamespace(
                    state="READY",
                    reason="INSTRUMENT_ELIGIBILITY_READY",
                    missing_security_ids=[],
                    resolved_count=2,
                ),
            )
        )
    )
    tax_lots = SimpleNamespace(
        resolve=AsyncMock(
            return_value=SimpleNamespace(
                latest_evidence_timestamp=LATEST_EVIDENCE,
                supportability=SimpleNamespace(
                    state="READY",
                    reason="TAX_LOTS_READY",
                    missing_security_ids=[],
                    returned_lot_count=2,
                ),
            )
        )
    )
    market_data = SimpleNamespace(
        resolve=AsyncMock(
            return_value=SimpleNamespace(
                latest_evidence_timestamp=LATEST_EVIDENCE,
                supportability=SimpleNamespace(
                    state="READY",
                    reason="MARKET_DATA_READY",
                    missing_instrument_ids=[],
                    missing_currency_pairs=[],
                    stale_instrument_ids=[],
                    stale_currency_pairs=[],
                    resolved_price_count=2,
                    resolved_fx_count=0,
                ),
            )
        )
    )

    response = await readiness.DpmSourceReadinessService(
        mandates=mandates,  # type: ignore[arg-type]
        model_targets=models,  # type: ignore[arg-type]
        eligibility=eligibility,  # type: ignore[arg-type]
        tax_lots=tax_lots,  # type: ignore[arg-type]
        market_data=market_data,  # type: ignore[arg-type]
        clock=lambda: GENERATED_AT,
    ).resolve(portfolio_id="PB_SG_GLOBAL_BAL_001", request=_request())

    assert response.model_portfolio_id == "MODEL_FROM_MANDATE"
    assert response.evaluated_instrument_ids == ["HELD_1", "TARGET_1"]
    assert [family.family for family in response.families] == [
        "mandate",
        "model_targets",
        "eligibility",
        "tax_lots",
        "market_data",
    ]
    eligibility_request = eligibility.resolve.await_args.args[0]
    assert eligibility_request.security_ids == ["HELD_1", "TARGET_1"]
