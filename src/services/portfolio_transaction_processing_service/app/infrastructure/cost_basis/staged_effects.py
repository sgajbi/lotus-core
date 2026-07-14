"""Describe transaction and instrument effects staged by cost processing."""

from dataclasses import dataclass

from portfolio_common.events import TransactionEvent


@dataclass(frozen=True, slots=True)
class StagedCostEffects:
    """Carry emitted transaction effects and instrument-update cardinality."""

    emitted_transactions: tuple[TransactionEvent, ...]
    instrument_update_count: int
