from __future__ import annotations

from typing import Any, NoReturn

from pydantic import BaseModel, Field

QUERY_CONTROL_PLANE_PROBLEM_TYPE_PREFIX = "https://lotus-platform.dev/problems/query-control-plane"
LEGACY_DETAIL_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {"detail": {"type": "string"}},
    "required": ["detail"],
}


class QueryControlPlaneProblemDetails(BaseModel):
    type: str = Field(
        description="Problem type URI.",
        examples=[
            "https://lotus-platform.dev/problems/query-control-plane/qcp_core_snapshot_not_found"
        ],
    )
    title: str = Field(
        description="Short human-readable problem summary.",
        examples=["Core snapshot not found"],
    )
    status: int = Field(description="HTTP status code.", examples=[404])
    detail: str = Field(
        description="Bounded product-safe problem detail.",
        examples=["Portfolio or simulation session was not found."],
    )
    instance: str = Field(
        description="Request path for the failing control-plane call.",
        examples=["/integration/portfolios/PORT-INT-404/core-snapshot"],
    )
    error_code: str = Field(
        description="Stable query-control-plane application error code.",
        examples=["QCP_CORE_SNAPSHOT_NOT_FOUND"],
    )
    correlation_id: str = Field(
        description="Correlation identifier for supportability.",
        examples=["QCP:1a2b3c4d-1234-5678-9abc-000000000001"],
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional bounded source-safe metadata for support diagnostics.",
        examples=[{"source_product": "PortfolioStateSnapshot"}],
    )


class QueryControlPlaneProblem(Exception):
    def __init__(
        self,
        *,
        status_code: int,
        title: str,
        detail: str,
        error_code: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.title = title
        self.detail = detail
        self.error_code = error_code
        self.metadata = metadata or {}


def problem_example(
    *,
    status_code: int,
    title: str,
    detail: str,
    error_code: str,
    instance: str = "/integration/portfolios/PORT-INT-001/core-snapshot",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "type": f"{QUERY_CONTROL_PLANE_PROBLEM_TYPE_PREFIX}/{error_code.lower()}",
        "title": title,
        "status": status_code,
        "detail": detail,
        "instance": instance,
        "error_code": error_code,
        "correlation_id": "QCP:1a2b3c4d-1234-5678-9abc-000000000001",
        "metadata": metadata or {},
    }


def build_problem_payload(
    *,
    problem: QueryControlPlaneProblem,
    instance: str,
    correlation_id: str,
) -> dict[str, Any]:
    return {
        "type": f"{QUERY_CONTROL_PLANE_PROBLEM_TYPE_PREFIX}/{problem.error_code.lower()}",
        "title": problem.title,
        "status": problem.status_code,
        "detail": problem.detail,
        "instance": instance,
        "error_code": problem.error_code,
        "correlation_id": correlation_id,
        "metadata": problem.metadata,
    }


def raise_problem(
    *,
    status_code: int,
    title: str,
    detail: str,
    error_code: str,
    metadata: dict[str, Any] | None = None,
) -> NoReturn:
    raise QueryControlPlaneProblem(
        status_code=status_code,
        title=title,
        detail=detail,
        error_code=error_code,
        metadata=metadata,
    )


def problem_response(description: str, example: dict[str, Any]) -> dict[str, object]:
    if _is_problem_details_example(example):
        schema = QueryControlPlaneProblemDetails.model_json_schema()
        return {
            "description": description,
            "content": {"application/problem+json": {"schema": schema, "example": example}},
        }

    return {
        "description": description,
        "content": {
            "application/json": {
                "schema": LEGACY_DETAIL_RESPONSE_SCHEMA,
                "example": example,
            }
        },
    }


def _is_problem_details_example(example: dict[str, Any]) -> bool:
    return {
        "type",
        "title",
        "status",
        "detail",
        "error_code",
        "correlation_id",
    } <= set(example)
