"""Simplified sustainment energy-flow projection helpers."""

from __future__ import annotations

import math


def compute_sustainment_projection(
    planning_energy_kwh: float,
    missions_per_week: float,
    planning_weeks: float,
    usable_battery_per_set_kwh: float,
    battery_sets_available: int,
    generator_efficiency: float = 0.84,
    generator_kwh_per_gallon: float = 10.0,
) -> dict[str, float]:
    """
    Compute simplified sustainment energy-flow planning outputs.

    This estimates total energy over a planning window and approximate full-inventory
    recharge cycles needed to support that demand.
    """
    energy_per_mission = max(float(planning_energy_kwh), 0.0)
    ops_per_week = max(float(missions_per_week), 0.0)
    weeks = max(float(planning_weeks), 0.0)
    usable_per_set = max(float(usable_battery_per_set_kwh), 0.001)
    sets_available = max(int(battery_sets_available), 1)
    generator_eff = min(max(float(generator_efficiency), 0.001), 1.0)
    kwh_per_gallon = max(float(generator_kwh_per_gallon), 0.001)

    total_missions = ops_per_week * weeks
    total_energy = energy_per_mission * total_missions
    inventory_energy = usable_per_set * sets_available
    inventory_cycles = total_energy / inventory_energy if inventory_energy > 0 else 0.0
    recharge_energy = max(total_energy - inventory_energy, 0.0)
    generator_input_energy = total_energy / generator_eff if total_energy > 0 else 0.0
    fuel_gallons_equivalent = generator_input_energy / kwh_per_gallon

    return {
        "missions_per_week": ops_per_week,
        "planning_weeks": weeks,
        "total_missions": total_missions,
        "conservative_energy_per_mission_kwh": energy_per_mission,
        "total_conservative_energy_kwh": total_energy,
        "usable_inventory_energy_per_cycle_kwh": inventory_energy,
        "inventory_cycles_required": float(math.ceil(inventory_cycles)) if inventory_cycles > 0 else 0.0,
        "generator_input_energy_kwh": generator_input_energy,
        "generator_efficiency": generator_eff,
        "generator_kwh_per_gallon": kwh_per_gallon,
        "fuel_gallons_equivalent": fuel_gallons_equivalent,
        "fuel_type_label": "JP-8/diesel tactical-generator planning factor",
        "recharge_energy_required_kwh": recharge_energy,
    }
