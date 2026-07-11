"""Schema-parity tests for QCP-owned DPM readiness contract families."""

from types import ModuleType

import pytest
from pydantic import BaseModel

from src.services.query_control_plane_service.app.contracts import (
    discretionary_mandate_binding,
    dpm_source_readiness,
    instrument_eligibility,
    market_data_coverage,
    model_portfolio_targets,
    portfolio_tax_lots,
)
from src.services.query_service.app.dtos import (
    reference_integration_dpm_source_readiness_dto,
    reference_integration_dto,
    reference_integration_instrument_eligibility_dto,
    reference_integration_market_data_coverage_dto,
    reference_integration_portfolio_tax_lot_dto,
)


@pytest.mark.parametrize(
    ("qcp_module", "legacy_module"),
    [
        (dpm_source_readiness, reference_integration_dpm_source_readiness_dto),
        (instrument_eligibility, reference_integration_instrument_eligibility_dto),
        (market_data_coverage, reference_integration_market_data_coverage_dto),
        (portfolio_tax_lots, reference_integration_portfolio_tax_lot_dto),
    ],
)
def test_dpm_readiness_contract_families_preserve_all_public_schemas(
    qcp_module: ModuleType,
    legacy_module: ModuleType,
) -> None:
    qcp_models = _declared_models(qcp_module)
    legacy_models = _declared_models(legacy_module)

    assert qcp_models.keys() == legacy_models.keys()
    for model_name, qcp_model in qcp_models.items():
        assert qcp_model.model_json_schema() == legacy_models[model_name].model_json_schema()


@pytest.mark.parametrize(
    ("qcp_module", "model_names"),
    [
        (
            discretionary_mandate_binding,
            (
                "DiscretionaryMandateBindingRequest",
                "RebalanceBandContext",
                "DiscretionaryMandateBindingSupportability",
                "DiscretionaryMandateBindingResponse",
            ),
        ),
        (
            model_portfolio_targets,
            (
                "ModelPortfolioTargetRequest",
                "ModelPortfolioTargetRow",
                "ModelPortfolioSupportability",
                "ModelPortfolioTargetResponse",
            ),
        ),
    ],
)
def test_embedded_dpm_contracts_preserve_public_schemas(
    qcp_module: ModuleType,
    model_names: tuple[str, ...],
) -> None:
    for model_name in model_names:
        qcp_model = getattr(qcp_module, model_name)
        legacy_model = getattr(reference_integration_dto, model_name)

        assert qcp_model.model_json_schema() == legacy_model.model_json_schema()


def _declared_models(module: ModuleType) -> dict[str, type[BaseModel]]:
    return {
        name: value
        for name, value in vars(module).items()
        if isinstance(value, type)
        and issubclass(value, BaseModel)
        and value.__module__ == module.__name__
    }
