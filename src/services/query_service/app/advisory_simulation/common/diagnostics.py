"""
Shared diagnostics builders for engine pipelines.
"""

from ..models import DiagnosticsData


def make_empty_data_quality_log() -> dict[str, list[str]]:
    return {"price_missing": [], "fx_missing": [], "shelf_missing": []}


def make_diagnostics_data() -> DiagnosticsData:
    return DiagnosticsData(
        warnings=[],
        suppressed_intents=[],
        group_constraint_events=[],
        data_quality=make_empty_data_quality_log(),
    )
