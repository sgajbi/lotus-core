from __future__ import annotations

import textwrap
from pathlib import Path

from scripts import qcp_problem_details_guard as guard


def _write_router(tmp_path: Path, content: str) -> Path:
    router_path = tmp_path / "router.py"
    router_path.write_text(textwrap.dedent(content), encoding="utf-8")
    return router_path


def test_evaluate_router_file_rejects_fastapi_http_exception(tmp_path: Path) -> None:
    router_path = _write_router(
        tmp_path,
        """
        from fastapi import HTTPException

        def route() -> None:
            raise HTTPException(status_code=404, detail="missing")
        """,
    )

    violations = guard.evaluate_router_file(router_path)

    assert len(violations) == 2
    assert "imports HTTPException" in violations[0]
    assert "calls HTTPException" in violations[1]


def test_evaluate_router_file_rejects_starlette_http_exception(tmp_path: Path) -> None:
    router_path = _write_router(
        tmp_path,
        """
        from starlette.exceptions import HTTPException
        """,
    )

    violations = guard.evaluate_router_file(router_path)

    assert len(violations) == 1
    assert "imports HTTPException" in violations[0]


def test_evaluate_router_file_rejects_raw_exception_detail_keyword(
    tmp_path: Path,
) -> None:
    router_path = _write_router(
        tmp_path,
        """
        def route(exc: Exception) -> object:
            return problem(status_code=400, detail=str(exc))
        """,
    )

    violations = guard.evaluate_router_file(router_path)

    assert len(violations) == 1
    assert "uses detail=str(...)" in violations[0]


def test_evaluate_router_file_rejects_raw_exception_detail_dict(tmp_path: Path) -> None:
    router_path = _write_router(
        tmp_path,
        """
        def route(exc: Exception) -> dict[str, str]:
            return {"detail": str(exc)}
        """,
    )

    violations = guard.evaluate_router_file(router_path)

    assert len(violations) == 1
    assert "builds {'detail': str(...)}" in violations[0]


def test_evaluate_router_file_accepts_bounded_problem_details(tmp_path: Path) -> None:
    router_path = _write_router(
        tmp_path,
        """
        from src.services.query_control_plane_service.app.routers.response_helpers import (
            QueryControlPlaneProblem,
        )

        def route() -> None:
            raise QueryControlPlaneProblem(
                status_code=404,
                title="Source data not found",
                detail="Source data is unavailable.",
                error_code="QCP_INTEGRATION_SOURCE_NOT_FOUND",
                metadata={"source_product": "Example:v1"},
            )
        """,
    )

    assert guard.evaluate_router_file(router_path) == []


def test_current_query_control_plane_routers_pass_problem_details_guard() -> None:
    assert guard.evaluate_qcp_routers() == []
