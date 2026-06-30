from src.services.query_control_plane_service.app.routers.response_helpers import (
    FASTAPI_VALIDATION_ERROR_EXAMPLE,
    FASTAPI_VALIDATION_ERROR_SCHEMA,
    LEGACY_DETAIL_RESPONSE_SCHEMA,
    problem_example,
    problem_or_validation_response,
    problem_response,
)


def test_problem_response_documents_problem_media_type_for_problem_examples() -> None:
    example = problem_example(
        status_code=404,
        title="Snapshot not found",
        detail="Portfolio or simulation session was not found.",
        error_code="QCP_CORE_SNAPSHOT_NOT_FOUND",
    )

    response = problem_response("Snapshot not found.", example)

    assert set(response["content"]) == {"application/problem+json"}
    problem_content = response["content"]["application/problem+json"]
    assert problem_content["example"]["error_code"] == "QCP_CORE_SNAPSHOT_NOT_FOUND"
    assert problem_content["schema"]["properties"]["correlation_id"]


def test_problem_response_preserves_legacy_json_for_bare_detail_examples() -> None:
    example = {"detail": "Portfolio with id PORT-OPS-001 not found"}

    response = problem_response("Portfolio not found.", example)

    assert response == {
        "description": "Portfolio not found.",
        "content": {
            "application/json": {
                "schema": LEGACY_DETAIL_RESPONSE_SCHEMA,
                "example": example,
            }
        },
    }


def test_problem_or_validation_response_documents_both_422_media_types() -> None:
    example = problem_example(
        status_code=422,
        title="Integration source request is invalid",
        detail="DPM portfolio-universe request is invalid.",
        error_code="QCP_INTEGRATION_SOURCE_INVALID_REQUEST",
    )

    response = problem_or_validation_response("Invalid request.", example)

    assert set(response["content"]) == {"application/problem+json", "application/json"}
    assert response["content"]["application/problem+json"]["example"]["error_code"] == (
        "QCP_INTEGRATION_SOURCE_INVALID_REQUEST"
    )
    assert response["content"]["application/json"] == {
        "schema": FASTAPI_VALIDATION_ERROR_SCHEMA,
        "example": FASTAPI_VALIDATION_ERROR_EXAMPLE,
    }
