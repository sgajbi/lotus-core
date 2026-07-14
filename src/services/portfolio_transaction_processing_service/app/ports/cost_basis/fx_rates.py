"""Framework-neutral port for effective-dated cost-basis FX rates."""

from datetime import date
from typing import Protocol

from ...domain.cost_basis import EffectiveFxRate


class CostBasisFxRatePort(Protocol):
    """Load the bounded effective-rate window required by cost processing."""

    async def get_fx_rate_window(
        self,
        from_currency: str,
        to_currency: str,
        *,
        start_date: date,
        end_date: date,
    ) -> list[EffectiveFxRate]: ...
