from datetime import date, datetime, timezone
from decimal import Decimal, localcontext

import pytest
from pydantic import BaseModel

from src.services.query_control_plane_service.app.application.analytics.analytics_content_identity import (  # noqa: E501
    analytics_page_content_identity,
    analytics_page_runtime_metadata,
)
from src.services.query_control_plane_service.app.application.analytics.analytics_quality import (  # noqa: E501
    analytics_source_runtime_metadata,
    timeseries_source_evidence_current,
)


class EconomicRow(BaseModel):
    valuation_date: date
    value: Decimal


def identity(rows: list[EconomicRow], **changes):
    basis = dict(
        product="PortfolioTimeseriesInput", request_scope="scope", data_quality_status="COMPLETE"
    )
    basis.update(changes)
    return analytics_page_content_identity(rows=rows, **basis)


def row(amount: str, day: int = 1) -> EconomicRow:
    return EconomicRow(valuation_date=date(2026, 4, day), value=Decimal(amount))


def test_identity_is_content_sensitive_not_request_only():
    original = identity([row("2100"), row("2250", 2)])
    corrected = identity([row("2100"), row("2400", 2)])
    assert original["content_hash"] != corrected["content_hash"]
    assert original == identity([row("2100"), row("2250", 2)])
    assert original["lineage"] == {
        "content_identity_scope": "response_page",
        "source_cut_status": "UNAVAILABLE",
    }
    assert "source_cut_id" not in original


def test_order_decimal_scale_and_signed_zero_are_canonical_without_rounding():
    with localcontext() as context:
        context.prec = 2
        assert identity([row("123456.700"), row("-0.00", 2)]) == identity(
            [row("0", 2), row("123456.7")]
        )
    assert identity([row("123456.7")]) != identity([row("123456.8")])


def test_empty_rows_have_real_identity_and_duplicates_remain_counted():
    assert identity([])["content_hash"] != (
        "sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    )
    assert identity([row("1")]) != identity([row("1"), row("1")])


@pytest.mark.parametrize(
    "field,value",
    [
        ("product", "PositionTimeseriesInput"),
        ("request_scope", "other"),
        ("data_quality_status", "PARTIAL"),
    ],
)
def test_economic_basis_and_quality_are_bound(field, value):
    assert identity([row("1")]) != identity([row("1")], **{field: value})


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity"])
def test_nonfinite_values_fail_closed(value):
    unvalidated = EconomicRow.model_construct(valuation_date=date(2026, 4, 1), value=Decimal(value))
    with pytest.raises(ValueError, match="finite decimals"):
        identity([unvalidated])


@pytest.mark.parametrize("status", ["COMPLETE", "PARTIAL", "STALE"])
@pytest.mark.parametrize("product", ["PortfolioTimeseriesInput", "PositionTimeseriesInput"])
def test_extracted_metadata_preserves_native_builder_and_evidence_policy(status, product):
    generated_at = datetime(2026, 10, 8, tzinfo=timezone.utc)
    basis = dict(product=product, request_scope="scope", rows=[row("2400")])
    expected = analytics_source_runtime_metadata(
        **analytics_page_content_identity(**basis, data_quality_status=status),
        as_of_date=date(2026, 4, 1),
        generated_at=generated_at,
        data_quality_status=status,
        source_evidence_current=timeseries_source_evidence_current(data_quality_status=status),
    )
    actual = analytics_page_runtime_metadata(
        **basis,
        as_of_date=date(2026, 4, 1),
        generated_at=generated_at,
        data_quality_status=status,
    )
    assert actual == expected
    assert actual["content_hash"] == actual["source_digest"]
    assert actual["source_cut_id"] is None
    assert "lineage" not in actual
