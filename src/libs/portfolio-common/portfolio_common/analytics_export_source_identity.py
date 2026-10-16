"""Existing acquired analytics-export selection identity over JSON-mode rows/evidence."""

from collections.abc import Mapping
from typing import Any, cast

from .source_data_product_metadata import stable_content_hash


def export_source_selection_digest(
    data_rows: list[dict[str, object]], source_evidence: Mapping[str, Any]
) -> str:
    """Preserve analytics-export-selection-v1; this digest creates no source authority."""
    pages = []
    for page in source_evidence["pages"]:
        metadata = dict(page["source_metadata"])
        metadata.pop("generated_at", None)
        metadata.pop("correlation_id", None)
        lineage = metadata.get("lineage")
        if isinstance(lineage, dict):
            metadata["lineage"] = {
                key: value
                for key, value in lineage.items()
                if key not in {"generated_at", "request_fingerprint"}
            }
        paging = metadata.get("page")
        if isinstance(paging, dict):
            metadata["page"] = {
                key: value for key, value in paging.items() if key != "next_page_token"
            }
        pages.append({**page, "source_metadata": metadata})
    return cast(
        str,
        stable_content_hash(
            {
                "identity_version": "analytics-export-selection-v1",
                "rows": data_rows,
                "source_evidence": {
                    key: value
                    for key, value in source_evidence.items()
                    if key not in {"pages", "selection_digest"}
                },
                "pages": pages,
            }
        ),
    )
