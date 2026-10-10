"""Controlled synthetic classification evidence; no live-provider authority."""

from datetime import UTC, datetime

from portfolio_common.api_contract.classification_history import (
    ClassificationHistorySelection,
    InstrumentClassificationCut,
    RetainedClassificationCut,
)


def source_cut(**overrides):
    payload = {
        "producer_id": "SYNTHETIC_REFERENCE",
        "classification_set_id": "SYNTHETIC_SECTOR",
        "source_record_id": "SYNTHETIC_JANUARY",
        "source_version": 1,
        "taxonomy_revision": "SYNTHETIC_V1",
        "dimension_name": "sector",
        "coverage_from": "2026-01-01",
        "coverage_to": "2026-02-01",
        "observed_at": "2026-02-01T00:00:00Z",
        "generated_at": "2026-02-01T01:00:00Z",
        "expected_security_ids": ["SYNTHETIC_A", "SYNTHETIC_B"],
        "expected_group_ids": ["TECHNOLOGY", "FINANCE"],
        "assignments": [
            {
                "security_id": security,
                "group_id": group,
                "effective_from": "2026-01-01",
                "effective_to": "2026-02-01",
                "source_record_id": "SYNTHETIC_ROW_" + security,
                "observed_at": "2026-02-01T00:00:00Z",
            }
            for security, group in (("SYNTHETIC_A", "TECHNOLOGY"), ("SYNTHETIC_B", "FINANCE"))
        ],
    }
    return InstrumentClassificationCut.model_validate(payload | overrides)


def retained_cut(source=None, *, received_at=None):
    source = source or source_cut()
    cut_id, content_hash = source.identity()
    return RetainedClassificationCut(
        cut_id=cut_id,
        content_hash=content_hash,
        received_at=received_at or datetime(2026, 2, 2, tzinfo=UTC),
        source=source,
    )


def selection(retained=None, **overrides):
    retained = retained or retained_cut()
    return ClassificationHistorySelection.model_validate(
        {
            **{
                name: getattr(retained.source, name)
                for name in (
                    "producer_id",
                    "classification_set_id",
                    "source_record_id",
                    "source_version",
                    "expected_security_ids",
                    "expected_group_ids",
                )
            },
            "cut_id": retained.cut_id,
            "content_hash": retained.content_hash,
            "period_start": "2026-01-01",
            "period_end": "2026-01-31",
            "source_as_of": "2026-03-01T00:00:00Z",
            "known_at": "2026-12-01T00:00:00Z",
        }
        | overrides
    )
