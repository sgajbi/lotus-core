"""Independent financial and content-identity assertions for live correction proof."""

import re
from decimal import Decimal

UNAVAILABLE = "sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
DAYS = ("2026-04-08", "2026-04-09", "2026-04-10")


def assert_economics(payload: dict, dataset: str, prices: tuple[str, ...]) -> None:
    """One USD equity, ten shares, no later trades; no production calculation reuse."""
    rows = payload["observations" if dataset == "portfolio" else "rows"]
    assert len(rows) == len(DAYS)
    assert [row["valuation_date"] for row in rows] == list(DAYS)
    expected = [Decimal("10") * Decimal(price) for price in prices]
    beginning = "beginning_market_value"
    ending = "ending_market_value"
    if dataset == "position":
        beginning += "_reporting_currency"
        ending += "_reporting_currency"
        assert all(Decimal(str(row["quantity"])) == Decimal("10") for row in rows)
    assert [Decimal(str(row[ending])) for row in rows] == expected
    assert [Decimal(str(row[beginning])) for row in rows] == [Decimal("0"), *expected[:-1]]
    assert all(row["valuation_status"] in {"final", "restated"} for row in rows)
    assert payload["reporting_currency"] == payload["portfolio_currency"] == "USD"
    assert payload["page"]["next_page_token"] is None
    assert payload["data_quality_status"] == "COMPLETE"
    assert payload["freshness_status"] == "CURRENT"
    assert payload["source_evidence_current"] is True


def has_economics(payload: dict, dataset: str, prices: tuple[str, ...]) -> bool:
    """Readiness predicate, never a successful proof on malformed/partial economics."""
    try:
        assert_economics(payload, dataset, prices)
    except (AssertionError, KeyError, TypeError, ValueError, ArithmeticError):
        return False
    return True


def assert_content_identity(payload: dict) -> None:
    digest = payload["content_hash"]
    assert isinstance(digest, str) and re.fullmatch(r"sha256:[0-9a-f]{64}", digest)
    assert digest != UNAVAILABLE
    assert digest == payload["source_digest"]
    assert payload["lineage"]["request_fingerprint"]
    assert payload["source_lineage"]["content_identity_scope"] == "response_page"
    assert payload["source_lineage"]["source_cut_status"] == "UNAVAILABLE"
    assert payload["source_cut_id"] is None


def assert_equivalent_read(first: dict, repeated: dict, dataset: str) -> None:
    for payload in (first, repeated):
        assert_content_identity(payload)
    rows_key = "observations" if dataset == "portfolio" else "rows"
    assert first[rows_key] == repeated[rows_key]
    assert first["content_hash"] == repeated["content_hash"]
    assert first["lineage"]["request_fingerprint"] == repeated["lineage"]["request_fingerprint"]
    assert first["page"]["snapshot_epoch"] == repeated["page"]["snapshot_epoch"]


def assert_corrected_read(before: dict, after: dict, dataset: str) -> None:
    assert_economics(before, dataset, ("100", "110", "120"))
    assert_economics(after, dataset, ("100", "130", "120"))
    for payload in (before, after):
        assert_content_identity(payload)
    assert before["content_hash"] != after["content_hash"]
    assert before["lineage"]["request_fingerprint"] == after["lineage"]["request_fingerprint"]
    # The actual epoch is retained in evidence, never presumed to be a content revision.
