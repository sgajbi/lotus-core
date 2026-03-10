from __future__ import annotations

from enum import Enum


class CostBasisMethod(str, Enum):
    FIFO = "FIFO"
    AVCO = "AVCO"


def normalize_cost_basis_method(value: str | CostBasisMethod | None) -> CostBasisMethod:
    if isinstance(value, CostBasisMethod):
        return value
    if value is None:
        return CostBasisMethod.FIFO

    normalized = str(value).strip().upper().replace("-", "_")
    try:
        return CostBasisMethod(normalized)
    except ValueError as exc:
        raise ValueError(f"Unsupported cost basis method: {value}") from exc
