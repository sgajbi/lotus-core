import pytest
from portfolio_common.cost_basis import CostBasisMethod, normalize_cost_basis_method


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [
        (None, CostBasisMethod.FIFO),
        ("FIFO", CostBasisMethod.FIFO),
        (CostBasisMethod.FIFO, CostBasisMethod.FIFO),
        ("AVCO", CostBasisMethod.AVCO),
    ],
)
def test_normalize_cost_basis_method_accepts_canonical_values(
    raw_value: str | CostBasisMethod | None,
    expected: CostBasisMethod,
) -> None:
    assert normalize_cost_basis_method(raw_value) is expected


@pytest.mark.parametrize("raw_value", ["LIFO", "AVERAGE_COST", "average cost"])
def test_normalize_cost_basis_method_rejects_unknown_value(raw_value: str) -> None:
    with pytest.raises(ValueError, match="Unsupported cost basis method"):
        normalize_cost_basis_method(raw_value)
