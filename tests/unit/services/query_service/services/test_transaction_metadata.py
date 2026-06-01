from datetime import UTC, date, datetime
from types import SimpleNamespace

from portfolio_common.reconciliation_quality import COMPLETE, PARTIAL, UNKNOWN

from src.services.query_service.app.services.transaction_metadata import (
    latest_transaction_evidence_timestamp,
    ledger_data_quality_status,
    realized_tax_summary_filters,
    transaction_ledger_filters,
)


def test_ledger_data_quality_status_classifies_complete_partial_and_empty_windows() -> None:
    assert (
        ledger_data_quality_status(
            total_count=2,
            returned_count=2,
            skip=0,
        )
        == COMPLETE
    )
    assert (
        ledger_data_quality_status(
            total_count=25,
            returned_count=10,
            skip=0,
        )
        == PARTIAL
    )
    assert (
        ledger_data_quality_status(
            total_count=25,
            returned_count=10,
            skip=10,
        )
        == PARTIAL
    )
    assert (
        ledger_data_quality_status(
            total_count=0,
            returned_count=0,
            skip=0,
        )
        == UNKNOWN
    )


def test_latest_transaction_evidence_timestamp_uses_latest_available_update() -> None:
    latest = datetime(2025, 1, 17, 10, 30, tzinfo=UTC)

    assert (
        latest_transaction_evidence_timestamp(
            [
                SimpleNamespace(updated_at=datetime(2025, 1, 16, 9, 30, tzinfo=UTC)),
                SimpleNamespace(updated_at=None),
                SimpleNamespace(updated_at=latest),
                SimpleNamespace(),
            ]
        )
        == latest
    )


def test_latest_transaction_evidence_timestamp_returns_none_for_empty_evidence() -> None:
    assert latest_transaction_evidence_timestamp([]) is None
    assert latest_transaction_evidence_timestamp([SimpleNamespace(updated_at=None)]) is None


def test_transaction_ledger_filters_preserve_repository_filter_shape() -> None:
    assert transaction_ledger_filters(
        portfolio_id="P1",
        instrument_id="I1",
        security_id="S1",
        transaction_type="FX_FORWARD",
        component_type="FX_CONTRACT_OPEN",
        linked_transaction_group_id="LTG-FX-001",
        fx_contract_id="FXC-001",
        swap_event_id="FXSWAP-001",
        near_leg_group_id="FXSWAP-001-NEAR",
        far_leg_group_id="FXSWAP-001-FAR",
        start_date=date(2025, 1, 1),
        end_date=date(2025, 1, 31),
        as_of_date=date(2025, 1, 15),
    ) == {
        "portfolio_id": "P1",
        "instrument_id": "I1",
        "security_id": "S1",
        "transaction_type": "FX_FORWARD",
        "component_type": "FX_CONTRACT_OPEN",
        "linked_transaction_group_id": "LTG-FX-001",
        "fx_contract_id": "FXC-001",
        "swap_event_id": "FXSWAP-001",
        "near_leg_group_id": "FXSWAP-001-NEAR",
        "far_leg_group_id": "FXSWAP-001-FAR",
        "start_date": date(2025, 1, 1),
        "end_date": date(2025, 1, 31),
        "as_of_date": date(2025, 1, 15),
    }


def test_realized_tax_summary_filters_preserve_repository_filter_shape() -> None:
    assert realized_tax_summary_filters(
        portfolio_id="P1",
        start_date=date(2025, 1, 1),
        end_date=date(2025, 1, 31),
        as_of_date=date(2025, 1, 15),
    ) == {
        "portfolio_id": "P1",
        "start_date": date(2025, 1, 1),
        "end_date": date(2025, 1, 31),
        "as_of_date": date(2025, 1, 15),
    }
