"""Simplified sustainment energy-flow projection helpers."""

from __future__ import annotations

import math

import numpy as np


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


def compute_sustainment_projection_variance(
    planning_energy_kwh: float,
    total_missions: float,
    mission_energy_samples_kwh: np.ndarray | list[float],
    rng: np.random.Generator,
    trials: int,
) -> dict[str, float | str | bool]:
    """
    Resample mission-to-mission energy variation across a planning horizon.

    Each projected mission independently draws from the single-mission Monte
    Carlo distribution, including its bounded current variation. The samples
    are normalized to the planning recommendation so the established
    sustainment baseline remains planning energy multiplied by mission count.
    """
    planning_energy = max(float(planning_energy_kwh), 0.0)
    mission_count = max(float(total_missions), 0.0)
    samples = np.asarray(mission_energy_samples_kwh, dtype=float)
    samples = samples[np.isfinite(samples) & (samples >= 0.0)]
    trial_count = max(1, min(int(trials), 10_000))
    baseline_total = planning_energy * mission_count
    if planning_energy <= 0.0 or mission_count <= 0.0 or samples.size == 0:
        return {
            "projection_variance_enabled": False,
            "projection_variance_trials": float(trial_count),
            "projected_energy_std_kwh": 0.0,
            "projected_energy_p10_kwh": baseline_total,
            "projected_energy_p50_kwh": baseline_total,
            "projected_energy_p90_kwh": baseline_total,
            "projection_variance_basis": "No stochastic horizon variance was available.",
        }

    sample_mean = float(np.mean(samples))
    if samples.size == 1 or sample_mean <= 0.0:
        projected_totals = np.full(trial_count, baseline_total)
    else:
        normalized_samples = samples / sample_mean
        whole_missions = int(math.floor(mission_count))
        fractional_mission = mission_count - whole_missions
        if whole_missions <= 512:
            normalized_totals = np.zeros(trial_count)
            for _ in range(whole_missions):
                normalized_totals += rng.choice(normalized_samples, size=trial_count)
            if fractional_mission > 0.0:
                normalized_totals += (
                    rng.choice(normalized_samples, size=trial_count)
                    * fractional_mission
                )
            projected_totals = planning_energy * normalized_totals
        else:
            normalized_std = float(np.std(normalized_samples, ddof=1))
            projected_totals = rng.normal(
                loc=baseline_total,
                scale=planning_energy * normalized_std * math.sqrt(mission_count),
                size=trial_count,
            )
            projected_totals = np.clip(projected_totals, 0.0, None)

    return {
        "projection_variance_enabled": samples.size > 1,
        "projection_variance_trials": float(trial_count),
        "projected_energy_std_kwh": float(np.std(projected_totals, ddof=1))
        if projected_totals.size > 1
        else 0.0,
        "projected_energy_p10_kwh": float(np.percentile(projected_totals, 10)),
        "projected_energy_p50_kwh": float(np.percentile(projected_totals, 50)),
        "projected_energy_p90_kwh": float(np.percentile(projected_totals, 90)),
        "projection_variance_basis": (
            "Independent mission/day resampling from the single-mission Monte Carlo "
            "distribution, including bounded current variation and normalized to "
            "the planning-recommendation baseline."
        ),
    }
