from __future__ import annotations

from types import SimpleNamespace

from src.services.query_service.app.services.core_snapshot_instrument_enrichment import (
    instrument_enrichment_records,
    requested_instrument_security_ids,
)


def _instrument(security_id: str) -> SimpleNamespace:
    return SimpleNamespace(
        security_id=security_id,
        issuer_id=f"ISSUER_{security_id}",
        issuer_name=f"{security_id} issuer",
        ultimate_parent_issuer_id=f"PARENT_{security_id}",
        ultimate_parent_issuer_name=f"{security_id} parent",
        liquidity_tier="L2",
    )


def test_requested_instrument_security_ids_strips_blanks() -> None:
    assert requested_instrument_security_ids([" SEC_A ", "", "  ", "SEC_B"]) == [
        "SEC_A",
        "SEC_B",
    ]


def test_instrument_enrichment_records_preserve_order_and_unknowns() -> None:
    records = instrument_enrichment_records(
        requested_ids=["SEC_A", "SEC_UNKNOWN", "SEC_B"],
        instruments=[_instrument("SEC_B"), _instrument("SEC_A")],
    )

    assert [record.security_id for record in records] == ["SEC_A", "SEC_UNKNOWN", "SEC_B"]
    assert records[0].issuer_id == "ISSUER_SEC_A"
    assert records[1].issuer_id is None
    assert records[1].liquidity_tier is None
    assert records[2].issuer_id == "ISSUER_SEC_B"


def test_instrument_enrichment_records_normalizes_returned_security_ids() -> None:
    records = instrument_enrichment_records(
        requested_ids=["SEC_A"],
        instruments=[_instrument(" SEC_A ")],
    )

    assert records[0].issuer_id == "ISSUER_ SEC_A "
    assert records[0].liquidity_tier == "L2"
