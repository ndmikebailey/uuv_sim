"""Vehicle state dataclass and vehicle catalog loader."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class VehicleState:
    """Vehicle and battery assumptions used by the energy model."""

    name: str
    battery_kwh: float
    estimated_endurance_hr: float
    nominal_speed_kts: float
    max_speed_kts: float
    recharge_hr: float
    usable_fraction: float
    usable_basis: str
    source_note: str

    @property
    def average_power_kw(self) -> float:
        """Estimate average hotel/propulsion power from battery and endurance."""
        return self.battery_kwh / max(self.estimated_endurance_hr, 0.1)

    @property
    def usable_battery_per_set_kwh(self) -> float:
        """Return usable planning energy per battery set."""
        return self.battery_kwh * self.usable_fraction


def load_vehicle_catalog(path: str | Path | None = None) -> dict[str, VehicleState]:
    """Load vehicle assumptions from the configuration-controlled data catalog."""
    catalog_path = Path(path) if path is not None else Path(__file__).resolve().parents[1] / "data" / "vehicle_catalog.json"
    raw_catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    return {
        name: VehicleState(name=name, **values)
        for name, values in raw_catalog.items()
    }


VEHICLE_CATALOG: dict[str, VehicleState] = load_vehicle_catalog()
