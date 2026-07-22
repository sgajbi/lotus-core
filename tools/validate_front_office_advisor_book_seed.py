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
PORTFOLIO_COMMON_ROOT = REPO_ROOT / "src" / "libs" / "portfolio-common"
if str(PORTFOLIO_COMMON_ROOT) not in sys.path:
    sys.path.insert(0, str(PORTFOLIO_COMMON_ROOT))

from portfolio_common.source_data_products import get_source_data_product  # noqa: E402

from tools.front_office_portfolio_seed import (  # noqa: E402
    FRONT_OFFICE_SEED_CONTRACT,
    build_front_office_portfolio_bundle,
    build_reference_ingestion_requests,
)

ADVISOR_BOOK_INGESTION_ENDPOINT = "/ingest/portfolio-party-role-assignments"
ADVISOR_BOOK_SOURCE_PRODUCT_NAME = "PortfolioManagerBookMembership"
ADVISOR_BOOK_SOURCE_PRODUCT_ROUTE = (
    "/integration/portfolio-manager-books/{portfolio_manager_id}/memberships"
)
ADVISOR_BOOK_SOURCE_PRODUCT_CONSUMERS = ("lotus-gateway", "lotus-manage")
ADVISOR_BOOK_SOURCE_PRODUCT_OWNER = "lotus-core"
ADVISOR_BOOK_SOURCE_PRODUCT_SERVING_PLANE = "query_control_plane_service"
ADVISOR_BOOK_SOURCE_PRODUCT_ROUTE_FAMILY = "Analytics Input"


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

    source_product = get_source_data_product(ADVISOR_BOOK_SOURCE_PRODUCT_NAME)
    executable_source_product = f"{source_product.product_name}:{source_product.product_version}"
    if contract.advisor_book_source_product != executable_source_product:
        raise ValueError(
            "canonical advisor-book source product must match the executable Core registry: "
            f"expected {executable_source_product}, observed "
            f"{contract.advisor_book_source_product}"
        )
    if source_product.current_routes != (ADVISOR_BOOK_SOURCE_PRODUCT_ROUTE,):
        raise ValueError(
            "canonical advisor-book source product must expose only the governed PM-book route: "
            f"observed {source_product.current_routes}"
        )
    if tuple(sorted(source_product.consumers)) != ADVISOR_BOOK_SOURCE_PRODUCT_CONSUMERS:
        raise ValueError(
            "canonical advisor-book source product must retain the governed consumers: "
            f"observed {source_product.consumers}"
        )
    if source_product.owner != ADVISOR_BOOK_SOURCE_PRODUCT_OWNER:
        raise ValueError(
            "canonical advisor-book source product must remain Core-owned: "
            f"observed {source_product.owner}"
        )
    if source_product.serving_plane != ADVISOR_BOOK_SOURCE_PRODUCT_SERVING_PLANE:
        raise ValueError(
            "canonical advisor-book source product must remain on the query control plane: "
            f"observed {source_product.serving_plane}"
        )
    if source_product.route_family != ADVISOR_BOOK_SOURCE_PRODUCT_ROUTE_FAMILY:
        raise ValueError(
            "canonical advisor-book source product must remain an analytics input: "
            f"observed {source_product.route_family}"
        )

    return {
        "status": "pass",
        "portfolio_id": expected["portfolio_id"],
        "portfolio_manager_id": expected["party_id"],
        "as_of_date": contract.canonical_as_of_date,
        "role_type": expected["role_type"],
        "role_scope": expected["role_scope"],
        "effective_from": expected["effective_from"],
        "effective_to": expected["effective_to"],
        "assignment_version": expected["assignment_version"],
        "source_system": expected["source_system"],
        "source_record_id": expected["source_record_id"],
        "observed_at": expected["observed_at"],
        "quality_status": expected["quality_status"],
        "source_product": executable_source_product,
        "source_product_route": ADVISOR_BOOK_SOURCE_PRODUCT_ROUTE,
        "source_product_consumers": list(ADVISOR_BOOK_SOURCE_PRODUCT_CONSUMERS),
        "source_product_owner": source_product.owner,
        "source_product_serving_plane": source_product.serving_plane,
        "source_product_route_family": source_product.route_family,
        "ingestion_endpoint": ADVISOR_BOOK_INGESTION_ENDPOINT,
        "assignment_count": 1,
    }


def main() -> int:
    print(json.dumps(validate_advisor_book_seed(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
