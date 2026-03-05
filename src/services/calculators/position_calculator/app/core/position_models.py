from decimal import Decimal

from pydantic import BaseModel


class PositionState(BaseModel):
    """
    Represents the state of a position at a point in time, tracking
    cost basis in both local and portfolio-base currency.
    """
    quantity: Decimal = Decimal(0)
    cost_basis: Decimal = Decimal(0)
    cost_basis_local: Decimal = Decimal(0)