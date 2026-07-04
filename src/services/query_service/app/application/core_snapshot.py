from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any


@dataclass(frozen=True, slots=True)
class CoreSnapshotOptionsCommand:
    include_zero_quantity_positions: bool
    include_cash_positions: bool
    position_basis: str
    weight_basis: str

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "include_zero_quantity_positions": self.include_zero_quantity_positions,
            "include_cash_positions": self.include_cash_positions,
            "position_basis": self.position_basis,
            "weight_basis": self.weight_basis,
        }


@dataclass(frozen=True, slots=True)
class CoreSnapshotSimulationCommand:
    session_id: str
    expected_version: int | None

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "expected_version": self.expected_version,
        }


@dataclass(frozen=True, slots=True)
class CoreSnapshotIdentityCommand:
    as_of_date: date
    snapshot_mode: str
    reporting_currency: str | None
    consumer_system: str
    tenant_id: str
    sections: list[str]
    simulation: CoreSnapshotSimulationCommand | None
    options: CoreSnapshotOptionsCommand

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "as_of_date": self.as_of_date.isoformat(),
            "snapshot_mode": self.snapshot_mode,
            "reporting_currency": self.reporting_currency,
            "consumer_system": self.consumer_system,
            "tenant_id": self.tenant_id,
            "sections": list(self.sections),
            "simulation": (
                self.simulation.canonical_payload() if self.simulation is not None else None
            ),
            "options": self.options.canonical_payload(),
        }
