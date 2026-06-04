from __future__ import annotations

import gzip
import json
from dataclasses import dataclass
from typing import Any

NDJSON_MEDIA_TYPE = "application/x-ndjson"


class AnalyticsExportNdjsonError(ValueError):
    pass


@dataclass(frozen=True)
class AnalyticsExportNdjsonResult:
    content: bytes
    media_type: str
    content_encoding: str


def analytics_export_ndjson_result(
    *,
    job_id: str,
    dataset_type: str,
    result_payload: dict[str, object],
    compression: str,
) -> AnalyticsExportNdjsonResult:
    payload_data = result_payload.get("data")
    if not isinstance(payload_data, list):
        raise AnalyticsExportNdjsonError("Export payload data is malformed.")

    encoded = _encode_ndjson_document(
        metadata={
            "record_type": "metadata",
            "job_id": job_id,
            "dataset_type": dataset_type,
            "generated_at": result_payload.get("generated_at"),
            "contract_version": result_payload.get("contract_version"),
        },
        records=payload_data,
    )
    if compression == "gzip":
        return AnalyticsExportNdjsonResult(
            content=gzip.compress(encoded),
            media_type=NDJSON_MEDIA_TYPE,
            content_encoding="gzip",
        )
    return AnalyticsExportNdjsonResult(
        content=encoded,
        media_type=NDJSON_MEDIA_TYPE,
        content_encoding="none",
    )


def _encode_ndjson_document(*, metadata: dict[str, object], records: list[Any]) -> bytes:
    lines = [json.dumps(metadata, separators=(",", ":"))]
    lines.extend(
        json.dumps({"record_type": "data", "record": record}, separators=(",", ":"))
        for record in records
    )
    return ("\n".join(lines) + "\n").encode("utf-8")
