"""Validate executable canonical advisor-book seed evidence.

The validator exercises the same bundle and request builders used by the live seed command. This
keeps cross-repository governance tied to executable Core behavior instead of source-code markers.
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.front_office_portfolio_seed import (  # noqa: E402
    FRONT_OFFICE_SEED_CONTRACT,
    build_front_office_portfolio_bundle,
    build_reference_ingestion_requests,
)

ADVISOR_BOOK_INGESTION_ENDPOINT = "/ingest/portfolio-party-role-assignments"


def _expected_assignment() -> dict[str, Any]:
    contract = FRONT_OFFICE_SEED_CONTRACT
    return {
        "portfolio_id": contract.portfolio_id,
        "party_id": contract.portfolio_manager_id,
        "role_type": contract.advisor_book_role_type,
        "role_scope": contract.advisor_book_role_scope,
        "effective_from": contract.advisor_book_assignment_effective_from,
        "effective_to": None,
        "assignment_version": contract.advisor_book_assignment_version,
        "source_system": contract.advisor_book_source_system,
        "source_record_id": contract.advisor_book_source_record_id,
        "observed_at": f"{contract.canonical_as_of_date}T09:00:00Z",
        "quality_status": contract.advisor_book_quality_status,
    }


def validate_advisor_book_seed() -> dict[str, Any]:
    """Return structured proof or raise when canonical executable seed behavior drifts."""
    contract = FRONT_OFFICE_SEED_CONTRACT
    bundle = build_front_office_portfolio_bundle(
        portfolio_id=contract.portfolio_id,
        start_date=date.fromisoformat(contract.seed_start_date),
        end_date=date.fromisoformat(contract.canonical_as_of_date),
        benchmark_start_date=date.fromisoformat(contract.benchmark_start_date),
        benchmark_id=contract.benchmark_id,
    )
    expected = _expected_assignment()
    assignments = bundle.get("portfolio_party_role_assignments")
    if assignments != [expected]:
        raise ValueError(
            "canonical bundle must contain exactly the governed advisor-book assignment"
        )

    requests = dict(build_reference_ingestion_requests(bundle))
    expected_payload = {"party_role_assignments": [expected]}
    if requests.get(ADVISOR_BOOK_INGESTION_ENDPOINT) != expected_payload:
        raise ValueError(
            "canonical ingestion plan must persist the governed advisor-book assignment"
        )

    return {
        "status": "pass",
        "portfolio_id": expected["portfolio_id"],
        "portfolio_manager_id": expected["party_id"],
        "source_record_id": expected["source_record_id"],
        "ingestion_endpoint": ADVISOR_BOOK_INGESTION_ENDPOINT,
        "assignment_count": 1,
    }


def main() -> int:
    print(json.dumps(validate_advisor_book_seed(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
