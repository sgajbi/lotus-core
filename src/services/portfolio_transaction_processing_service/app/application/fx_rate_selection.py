"""Shared deterministic selection for effective-dated FX windows."""

from datetime import date

from ..domain.cost_basis import EffectiveFxRate


def select_latest_effective_fx_rate(
    rate_window: list[EffectiveFxRate], effective_date: date
) -> EffectiveFxRate | None:
    """Select the latest eligible row, breaking same-date ties by repository order."""

    selected: EffectiveFxRate | None = None
    for rate in rate_window:
        if rate.effective_date <= effective_date:
            selected = rate
    return selected
