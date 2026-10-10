"""Refuse plausible-looking but financially/identity-invalid correction evidence."""

from copy import deepcopy

import pytest

from tests.test_support.analytics_correction_oracle import (
    DAYS,
    UNAVAILABLE,
    assert_corrected_read,
    assert_equivalent_read,
    has_economics,
)


def payload(dataset, corrected=False):
    values = ("1000", "1300" if corrected else "1100", "1200")
    suffix = "_reporting_currency" if dataset == "position" else ""
    rows = [
        {
            "valuation_date": day,
            "quantity": "10",
            "valuation_status": "final",
            f"beginning_market_value{suffix}": "0" if index == 0 else values[index - 1],
            f"ending_market_value{suffix}": values[index],
        }
        for index, day in enumerate(DAYS)
    ]
    digest = "sha256:" + ("b" if corrected else "a") * 64
    return {
        "rows" if dataset == "position" else "observations": rows,
        "content_hash": digest,
        "source_digest": digest,
        "source_cut_id": None,
        "source_lineage": {
            "content_identity_scope": "response_page",
            "source_cut_status": "UNAVAILABLE",
        },
        "lineage": {"request_fingerprint": "same-request", "generated_at": "first"},
        "page": {"next_page_token": None, "snapshot_epoch": 1},
        "portfolio_currency": "USD",
        "reporting_currency": "USD",
        "data_quality_status": "COMPLETE",
        "freshness_status": "CURRENT",
        "source_evidence_current": True,
    }


@pytest.mark.parametrize("dataset", ["portfolio", "position"])
def test_independent_correction_and_volatile_time_repeat(dataset):
    before, after = payload(dataset), payload(dataset, True)
    repeated = deepcopy(after)
    repeated["lineage"]["generated_at"] = "later"
    assert_corrected_read(before, after, dataset)
    assert_equivalent_read(after, repeated, dataset)


@pytest.mark.parametrize("dataset", ["portfolio", "position"])
@pytest.mark.parametrize("defect", ["economics", "unchanged_hash", "sentinel", "request", "cut"])
def test_false_correction_evidence_fails_closed(dataset, defect):
    before, after = payload(dataset), payload(dataset, True)
    if defect == "economics":
        key = "rows" if dataset == "position" else "observations"
        after[key] = before[key]
    elif defect in {"unchanged_hash", "sentinel"}:
        after["content_hash"] = after["source_digest"] = (
            before["content_hash"] if defect == "unchanged_hash" else UNAVAILABLE
        )
    elif defect == "request":
        after["lineage"]["request_fingerprint"] = "different-request"
    else:
        after["source_cut_id"] = "fabricated-qualified-cut"
    with pytest.raises(AssertionError):
        assert_corrected_read(before, after, dataset)


@pytest.mark.parametrize("malformed", [{}, {"observations": []}, {"observations": None}])
def test_readiness_never_accepts_missing_economics(malformed):
    assert not has_economics(malformed, "portfolio", ("100", "130", "120"))
