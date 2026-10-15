"""New source registration preserves old posture and never authenticates by grant."""

from dataclasses import replace

import pytest
from portfolio_common.source_data_products import (
    get_source_data_product,
    source_data_product_openapi_extra,
)
from portfolio_common.source_data_security import (
    get_source_data_security_profile,
    validate_source_data_security_profiles,
)

pytestmark = [pytest.mark.unit, pytest.mark.security]


def test_flow_profile_matches_existing_scoping_and_preserves_other_profiles():
    old = get_source_data_security_profile("PortfolioFinancialSourceObservations")
    new = get_source_data_security_profile("PortfolioFinancialFlowObservations")
    assert replace(new, product_name=old.product_name) == old
    assert new.tenant_required and new.entitlement_required
    validate_source_data_security_profiles()
    product = get_source_data_product("PortfolioFinancialFlowObservations")
    assert product.consumers == ("lotus-manage",)
    extension = source_data_product_openapi_extra(product.product_name)
    assert extension["x-lotus-source-data-security"]["tenant_required"] is True
    for unknown in ("PortfolioFinancialFlowObservations/v2", "UnqualifiedFlowAlias"):
        with pytest.raises(KeyError):
            get_source_data_security_profile(unknown)
