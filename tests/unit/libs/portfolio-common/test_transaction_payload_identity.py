from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from portfolio_common.domain.transaction import (
    TRANSACTION_PAYLOAD_MATERIAL_FIELDS,
    TRANSACTION_PAYLOAD_NON_MATERIAL_FIELDS,
    build_transaction_payload_identity,
    transaction_payload_fingerprint,
)
from portfolio_common.domain.transaction.payload_identity import (
    FX_UPSTREAM_PNL_FIELDS,
    transaction_payload_pre_upstream_fingerprint,
)
from portfolio_common.events import TransactionEvent


def _event(**updates: object) -> TransactionEvent:
    payload: dict[str, object] = {
        "transaction_id": "TX-PAYLOAD-001",
        "portfolio_id": "PORT-001",
        "tenant_id": "tenant-a",
        "instrument_id": "INST-001",
        "security_id": "SEC-001",
        "transaction_date": datetime(2026, 9, 27, 10, 15, tzinfo=UTC),
        "settlement_date": datetime(2026, 9, 29, 0, 0, tzinfo=UTC),
        "transaction_type": "BUY",
        "quantity": Decimal("10.0000000000"),
        "price": Decimal("125.50"),
        "gross_transaction_amount": Decimal("1255"),
        "trade_currency": "USD",
        "currency": "USD",
        "brokerage": Decimal("2.50"),
        "source_system": "BOOKING_SOURCE",
        "source_transaction_reference": "BOOKING-001",
    }
    payload.update(updates)
    return TransactionEvent.model_validate(payload)


def test_transaction_payload_field_contract_classifies_every_event_field() -> None:
    assert TRANSACTION_PAYLOAD_MATERIAL_FIELDS.isdisjoint(TRANSACTION_PAYLOAD_NON_MATERIAL_FIELDS)
    assert set(TransactionEvent.model_fields) == (
        TRANSACTION_PAYLOAD_MATERIAL_FIELDS
        | (TRANSACTION_PAYLOAD_NON_MATERIAL_FIELDS & set(TransactionEvent.model_fields))
    )


def test_transaction_payload_identity_is_stable_for_metadata_and_timezone_only_changes() -> None:
    original = _event(
        correlation_id="corr-a",
        traceparent="00-0123456789abcdef0123456789abcdef-0123456789abcdef-01",
        epoch=1,
        created_at=datetime(2026, 9, 27, 10, 16, tzinfo=UTC),
    )
    same_instant = _event(
        tenant_id="tenant-b",
        correlation_id="corr-b",
        traceparent="00-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-bbbbbbbbbbbbbbbb-01",
        epoch=99,
        created_at=datetime(2026, 9, 28, 11, 0, tzinfo=UTC),
        transaction_date=datetime(
            2026,
            9,
            27,
            18,
            15,
            tzinfo=timezone(timedelta(hours=8)),
        ),
    )

    original_identity = build_transaction_payload_identity(
        original.model_dump(mode="python"), tenant_id="tenant-a"
    )
    other_tenant_identity = build_transaction_payload_identity(
        same_instant.model_dump(mode="python"), tenant_id="tenant-b"
    )

    assert original_identity.payload_fingerprint == other_tenant_identity.payload_fingerprint
    assert original_identity.semantic_key != other_tenant_identity.semantic_key
    assert original_identity.payload_fingerprint == (
        "sha256:0d3dc27caf1667513c34f0f1e406b4466bb977e759e4b7f685da06432deeddc8"
    )


@pytest.mark.parametrize(
    ("field_name", "changed_value"),
    [
        ("quantity", Decimal("11")),
        ("trade_currency", "EUR"),
        ("source_system", "CORRECTED_SOURCE"),
        ("source_transaction_reference", "BOOKING-002"),
        ("brokerage", Decimal("3.00")),
    ],
)
def test_transaction_payload_identity_changes_for_material_restatement(
    field_name: str,
    changed_value: object,
) -> None:
    original = _event()
    changed = _event(**{field_name: changed_value})

    assert transaction_payload_fingerprint(original.model_dump(mode="python")) != (
        transaction_payload_fingerprint(changed.model_dump(mode="python"))
    )


def test_source_booked_fx_rate_is_material_to_raw_payload_identity() -> None:
    original = _event(
        transaction_fx_rate=Decimal("2.0"),
        transaction_fx_rate_origin="SOURCE_BOOKED",
    )
    replay = _event(
        transaction_fx_rate=Decimal("2.00"),
        transaction_fx_rate_origin="SOURCE_BOOKED",
    )
    correction = _event(
        transaction_fx_rate=Decimal("2.5"),
        transaction_fx_rate_origin="SOURCE_BOOKED",
    )

    assert transaction_payload_fingerprint(original.model_dump(mode="python")) == (
        transaction_payload_fingerprint(replay.model_dump(mode="python"))
    )
    assert transaction_payload_fingerprint(original.model_dump(mode="python")) != (
        transaction_payload_fingerprint(correction.model_dump(mode="python"))
    )
    original_identity = build_transaction_payload_identity(
        original.model_dump(mode="python"), tenant_id="tenant-a"
    )
    assert original_identity.semantic_key.startswith("transaction-persistence:v2:")
    assert original_identity.legacy_payload_fingerprint == (
        "sha256:0d3dc27caf1667513c34f0f1e406b4466bb977e759e4b7f685da06432deeddc8"
    )


@pytest.mark.parametrize("origin", ["REFERENCE_DERIVED", "LEGACY_UNKNOWN", None])
def test_processor_or_legacy_fx_rate_is_not_material_to_raw_payload_identity(
    origin: str | None,
) -> None:
    original = _event(
        transaction_fx_rate=Decimal("2.0"),
        transaction_fx_rate_origin=origin,
    )
    replay = _event(
        transaction_fx_rate=Decimal("2.5"),
        transaction_fx_rate_origin=origin,
    )

    assert transaction_payload_fingerprint(original.model_dump(mode="python")) == (
        transaction_payload_fingerprint(replay.model_dump(mode="python"))
    )
    assert build_transaction_payload_identity(
        original.model_dump(mode="python"), tenant_id="tenant-a"
    ).semantic_key.startswith("transaction-persistence:v1:")


def test_transaction_payload_identity_rejects_unclassified_fields() -> None:
    payload = _event().model_dump(mode="python")
    payload["future_unclassified_field"] = "unsafe-default"

    with pytest.raises(ValueError, match="future_unclassified_field"):
        transaction_payload_fingerprint(payload)


@pytest.mark.parametrize("field", FX_UPSTREAM_PNL_FIELDS)
@pytest.mark.parametrize("amount", [Decimal(0), Decimal("12"), Decimal("-12")])
def test_upstream_raw_identity_distinguishes_missing_zero_and_signed_source(field, amount) -> None:
    original = _event(transaction_type="FX_FORWARD", fx_realized_pnl_mode="UPSTREAM_PROVIDED")
    changed = original.model_copy(update={field: amount})
    before = original.model_dump(mode="python")
    after = changed.model_dump(mode="python")
    identity = build_transaction_payload_identity(before, tenant_id="tenant-a")
    assert identity.semantic_key.startswith("transaction-persistence:v3:")
    assert identity.payload_fingerprint != transaction_payload_fingerprint(after)
    assert transaction_payload_pre_upstream_fingerprint(before) == (
        transaction_payload_pre_upstream_fingerprint(after)
    )
    assert (
        identity.legacy_payload_fingerprint
        == build_transaction_payload_identity(
            after, tenant_id="tenant-a"
        ).legacy_payload_fingerprint
    )


@pytest.mark.parametrize("mode", [None, "NONE"])
def test_non_upstream_raw_identity_preserves_processor_output_exclusion(mode) -> None:
    original = _event(transaction_type="FX_FORWARD", fx_realized_pnl_mode=mode)
    changed = original.model_copy(update={name: Decimal(12) for name in FX_UPSTREAM_PNL_FIELDS})
    assert transaction_payload_fingerprint(original.model_dump(mode="python")) == (
        transaction_payload_fingerprint(changed.model_dump(mode="python"))
    )


def test_upstream_raw_identity_preserves_numeric_and_metadata_replay() -> None:
    original = _event(
        transaction_type="FX_FORWARD",
        fx_realized_pnl_mode="UPSTREAM_PROVIDED",
        realized_fx_pnl_local=Decimal("0"),
        realized_fx_pnl_base=Decimal("12"),
    )
    replay = original.model_copy(
        update={
            "realized_fx_pnl_local": Decimal("0.00"),
            "realized_fx_pnl_base": Decimal("12.000"),
            "correlation_id": "another-attempt",
        }
    )
    assert transaction_payload_fingerprint(original.model_dump(mode="python")) == (
        transaction_payload_fingerprint(replay.model_dump(mode="python"))
    )


@pytest.mark.parametrize("origin", [None, "SOURCE_BOOKED"])
def test_pre_upstream_hash_preserves_exact_existing_version_policy(origin) -> None:
    event = _event(transaction_fx_rate=Decimal("1.1"), transaction_fx_rate_origin=origin)
    payload = event.model_dump(mode="python")
    assert transaction_payload_pre_upstream_fingerprint(payload) == (
        transaction_payload_fingerprint(payload)
    )
    upstream = {
        **payload,
        "transaction_type": "FX_FORWARD",
        "fx_realized_pnl_mode": "UPSTREAM_PROVIDED",
    }
    changed = {**upstream, **{name: Decimal(12) for name in FX_UPSTREAM_PNL_FIELDS}}
    assert transaction_payload_pre_upstream_fingerprint(upstream) == (
        transaction_payload_pre_upstream_fingerprint(changed)
    )
    if origin == "SOURCE_BOOKED":
        assert transaction_payload_pre_upstream_fingerprint(upstream) != (
            transaction_payload_pre_upstream_fingerprint(
                {**upstream, "transaction_fx_rate": Decimal("1.2")}
            )
        )
