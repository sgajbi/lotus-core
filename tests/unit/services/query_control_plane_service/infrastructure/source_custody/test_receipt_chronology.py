"""Synthetic receipt chronology controls; no acquisition, database or financial authority."""

import base64
import io
import json

import pytest
from portfolio_common.domain.portfolio_financial_source_cuts import source_product_bytes

from src.services.query_control_plane_service.app.infrastructure import (
    portfolio_financial_source_cuts as retained,
)
from tests.unit.services.query_control_plane_service.infrastructure import (
    test_portfolio_financial_source_cuts as fixtures,
)


@pytest.mark.parametrize("role", ["CASH", "READINESS", "FLOWS"])
@pytest.mark.parametrize(
    ("completed_at", "accepted"),
    [
        ("2026-10-15T00:00:00+00:00", False),
        ("2026-10-16T00:00:00+00:00", True),
        ("2026-10-16T00:00:01+00:00", True),
        ("2026-10-16T08:00:00+08:00", True),
    ],
)
def test_retained_native_receipt_chronology_uses_aware_instants_without_freshness(
    role, completed_at, accepted
):
    _, _, cut, selected, rows = fixtures.native_vector_fixture()
    artifact = next(row for row in rows if row.role == role)
    payload = json.loads(base64.b64decode(artifact.bytes_base64))["payload"]
    assert payload["received_at"] == "2026-10-16T00:00:00+00:00"
    payload["receipt"]["completed_at"] = completed_at
    raw = source_product_bytes(payload, serializer=artifact.serializer_id)
    recaptured = fixtures.recaptured_artifact(artifact, raw)
    assert recaptured.typed_content_hash == artifact.typed_content_hash
    assert recaptured.capture_id == artifact.capture_id
    assert recaptured.selector_hash == artifact.selector_hash
    assert recaptured.source_context == artifact.source_context
    verifier = retained.RetainedSourceCaptureVerifier()
    if accepted:
        verifier.verify(
            recaptured,
            io.BytesIO(raw),
            identity=cut.header.manifest.identity,
            financial_input=selected,
        )
    else:
        with pytest.raises(ValueError, match="receipt chronology"):
            verifier.verify(
                recaptured,
                io.BytesIO(raw),
                identity=cut.header.manifest.identity,
                financial_input=selected,
            )


@pytest.mark.parametrize(
    ("completed_at", "accepted"),
    [
        ("2026-10-15T00:00:00+00:00", False),
        ("2026-10-16T00:00:00+00:00", True),
        ("2026-10-16T00:00:01+00:00", True),
    ],
)
def test_retained_flow_member_receipt_independently_requires_chronology(completed_at, accepted):
    _, _, cut, selected, rows = fixtures.native_vector_fixture()
    artifact = next(row for row in rows if row.role == "FLOWS")
    payload = json.loads(base64.b64decode(artifact.bytes_base64))["payload"]
    member = payload["events"][0]
    assert member["received_at"] == "2026-10-16T00:00:00+00:00"
    member["receipt"]["completed_at"] = completed_at
    raw = source_product_bytes(payload, serializer=artifact.serializer_id)
    recaptured = fixtures.recaptured_artifact(artifact, raw)
    assert recaptured.typed_content_hash == artifact.typed_content_hash
    verifier = retained.RetainedSourceCaptureVerifier()
    if accepted:
        verifier.verify(
            recaptured,
            io.BytesIO(raw),
            identity=cut.header.manifest.identity,
            financial_input=selected,
        )
    else:
        with pytest.raises(ValueError, match="receipt chronology"):
            verifier.verify(
                recaptured,
                io.BytesIO(raw),
                identity=cut.header.manifest.identity,
                financial_input=selected,
            )
