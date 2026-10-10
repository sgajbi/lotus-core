"""Classification cut identity and exact half-open interval coverage."""

import hashlib
import json
from datetime import date
from typing import Any


class ClassificationHistoryConflict(ValueError):
    """Bounded reference conflict, without exposing supplied identifiers."""


def classification_cut_identity(payload: dict[str, Any]) -> tuple[str, str]:
    """Derive identities from the complete retained source command, never current labels."""
    canonical = dict(payload)
    for name in ("expected_security_ids", "expected_group_ids"):
        canonical[name] = sorted(canonical[name])
    canonical["assignments"] = sorted(
        canonical["assignments"],
        key=lambda row: (row["security_id"], row["effective_from"], row["group_id"]),
    )
    wire = json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    if len(wire.encode("utf-8")) > 524288:
        raise ClassificationHistoryConflict("CLASSIFICATION_CUT_TOO_LARGE")
    content = "sha256:" + hashlib.sha256(wire.encode("utf-8")).hexdigest()
    cut = (
        "sha256:"
        + hashlib.sha256(("instrument-classification-cut-v1:" + content).encode()).hexdigest()
    )
    return cut, content


def missing_assignment_coverage(
    rows: list[dict[str, Any]], *, securities: tuple[str, ...], start: date, until: date
) -> tuple[str, ...]:
    """Report every expected security lacking uninterrupted coverage; never fill labels."""
    missing = []
    for security in securities:
        cursor = start
        selected = sorted(
            (row for row in rows if row["security_id"] == security),
            key=lambda row: row["effective_from"],
        )
        for row in selected:
            if row["effective_to"] <= cursor or row["effective_from"] >= until:
                continue
            if row["effective_from"] > cursor:
                break
            cursor = max(cursor, row["effective_to"])
        if cursor < until:
            missing.append(security)
    return tuple(missing)
