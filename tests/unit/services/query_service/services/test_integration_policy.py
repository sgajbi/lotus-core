from src.services.query_service.app.services.integration_policy import (
    resolve_effective_policy_response,
)


def test_resolve_effective_policy_response_owns_generated_timestamp() -> None:
    response = resolve_effective_policy_response(
        consumer_system="LOTUS-MANAGE",
        tenant_id="TENANT_SG",
        include_sections=["summary"],
    )

    assert response.consumer_system == "lotus-manage"
    assert response.tenant_id == "TENANT_SG"
    assert response.generated_at is not None
    assert response.policy_provenance.policy_version
