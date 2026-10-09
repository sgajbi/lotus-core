from datetime import date
from decimal import Decimal

import pytest

from src.services.query_control_plane_service.app.application.analytics import (
    analytics_input_errors,
)
from src.services.query_control_plane_service.app.application.analytics.analytics_traversal import (
    TRAVERSAL_VERSION,
    selected_inputs_fingerprint,
    validate_traversal_continuation,
)


def test_selected_dependency_identity_preserves_values_not_representation():
    day = date(2026, 7, 2)
    first = selected_inputs_fingerprint(
        snapshot_epoch=0, dates=[day], reporting_fx={day: Decimal("1.50")}
    )
    assert first == selected_inputs_fingerprint(
        reporting_fx={day: Decimal("1.5")}, dates=[day], snapshot_epoch=0
    )
    assert first != selected_inputs_fingerprint(
        snapshot_epoch=0, dates=[day], reporting_fx={day: Decimal("1.51")}
    )
    assert first != selected_inputs_fingerprint(
        snapshot_epoch=0, dates=[day, day], reporting_fx={day: Decimal("1.5")}
    )
    assert selected_inputs_fingerprint(keyed={("SEC_A", "SEC_B"): Decimal("1")}) != (
        selected_inputs_fingerprint(keyed={("SEC_B", "SEC_A"): Decimal("1")})
    )


@pytest.mark.parametrize(
    "change", ["missing", "legacy", "version", "epoch", "boolean_epoch", "hash", "nonascii"]
)
def test_continuation_refuses_unbound_or_changed_inputs(change):
    fingerprint = selected_inputs_fingerprint(snapshot_epoch=0, dates=[])
    cursor = {
        "valuation_date": "2026-07-02",
        "traversal_version": TRAVERSAL_VERSION,
        "snapshot_epoch": 0,
        "selected_inputs_fingerprint": fingerprint,
    }
    validate_traversal_continuation(cursor=cursor, snapshot_epoch=0, fingerprint=fingerprint)
    if change == "missing":
        del cursor["selected_inputs_fingerprint"]
    elif change == "legacy":
        del cursor["traversal_version"]
    elif change == "version":
        cursor["traversal_version"] = "unrecognized"
    elif change == "epoch":
        cursor["snapshot_epoch"] = 1
    elif change == "boolean_epoch":
        cursor["snapshot_epoch"] = False
    else:
        cursor["selected_inputs_fingerprint"] = ("0" if change == "hash" else "é") * 64
    with pytest.raises(analytics_input_errors.AnalyticsInputError) as refusal:
        validate_traversal_continuation(cursor=cursor, snapshot_epoch=0, fingerprint=fingerprint)
    assert refusal.value.code == "STALE_CONTINUATION"
