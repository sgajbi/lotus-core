from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class ValuationData(BaseModel):
    """
    Represents the valuation details for a position.
    """

    market_price: Decimal | None = Field(
        None,
        description="Market price used for the position valuation snapshot.",
        examples=[185.42],
    )

    # In portfolio base currency
    market_value: Decimal | None = Field(
        None,
        description="Position market value translated into portfolio base currency.",
        examples=[23177.5],
    )
    unrealized_gain_loss: Decimal | None = Field(
        None,
        description="Unrealized gain or loss in portfolio base currency.",
        examples=[3177.5],
    )

    # In instrument's local currency
    market_value_local: Decimal | None = Field(
        None,
        description="Position market value in local instrument currency.",
        examples=[23177.5],
    )
    unrealized_gain_loss_local: Decimal | None = Field(
        None,
        description="Unrealized gain or loss in local instrument currency.",
        examples=[3177.5],
    )

    model_config = ConfigDict(from_attributes=True)
