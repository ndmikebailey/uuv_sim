# v3.2 Model Validation and Stockpile Planning Development Plan

## Purpose

The v3.2 branch should shift the project from UI/report stabilization toward simulation credibility. The main objective is to make clear what affects mission energy, what is manufacturer-sourced, what is model-estimated, and how single-mission outputs can roll up into stockpile or recharge planning.

## Immediate v3.2 priorities

1. Keep the active vehicle catalog aligned with the validated public vehicle baseline.
2. Add a speed-power relationship so increasing speed increases propulsion energy, not just mission duration.
3. Add a stockpile/recharge planning lens driven by mission frequency and planning horizon.
4. Add an optional contested-delay stochastic lens for hover/delay interruptions.
5. Add model-reasonableness tests to prevent future regressions.

## 1. Vehicle baseline data

Replace `data/vehicle_catalog.json` with the public baseline catalog provided in `vehicle_catalog_v3_2_public_baseline.json`.

Keep the current simple catalog schema unless the loader is deliberately updated. The current `VehicleState` loader expects these fields only:

- `battery_kwh`
- `estimated_endurance_hr`
- `nominal_speed_kts`
- `max_speed_kts`
- `recharge_hr`
- `usable_fraction`
- `usable_basis`
- `source_note`

Additional metadata should go into `data/vehicle_source_metadata_v3_2.json` or documentation, not the active catalog, unless the dataclass is updated.

## 2. Speed-power relationship

Current concern: if average power is treated as constant, increasing speed can reduce mission time without properly increasing energy demand. That is not a credible propulsion model.

Recommended planning model:

```python
def estimate_power_at_speed_kw(
    vehicle: VehicleState,
    speed_kts: float,
    hotel_fraction: float = 0.35,
    speed_exponent: float = 3.0,
) -> float:
    """Estimate total UUV power at speed using a simple cubic propulsion law.

    average_power_kw is derived from manufacturer battery/endurance.
    Split it into a fixed hotel/sensor component and a propulsion component.
    Propulsion power scales approximately with speed^3.
    """
    nominal_speed = max(vehicle.nominal_speed_kts, 0.1)
    requested_speed = max(speed_kts, 0.1)
    baseline_power = vehicle.average_power_kw
    hotel_kw = baseline_power * hotel_fraction
    propulsion_kw_nominal = baseline_power * (1.0 - hotel_fraction)
    speed_ratio = requested_speed / nominal_speed
    return hotel_kw + propulsion_kw_nominal * (speed_ratio ** speed_exponent)
```

Use this function anywhere mission energy currently uses `vehicle.average_power_kw * duration` for moving missions.

Recommended defaults:

- `hotel_fraction = 0.35`
- `speed_exponent = 3.0`

These should be documented as planning assumptions and later calibrated.

## 3. Stockpile and recharge planning lens

Add optional user inputs:

- `missions_per_week`
- `planning_horizon_days` or a dropdown: `1 day`, `1 week`, `1 month`, `3 months`
- `generator_efficiency`, default `0.84`
- `fuel_energy_kwh_per_gal`, default configurable and documented
- `available_chargers` optional, default 1

Recommended calculation:

```python
def compute_stockpile_requirement(
    conservative_energy_kwh: float,
    usable_battery_per_set_kwh: float,
    missions_per_week: float,
    planning_horizon_days: float,
    generator_efficiency: float = 0.84,
    fuel_energy_kwh_per_gal: float = 38.0,
) -> dict[str, float]:
    missions = missions_per_week * (planning_horizon_days / 7.0)
    total_mission_energy_kwh = conservative_energy_kwh * missions
    battery_sets_without_recharge = math.ceil(total_mission_energy_kwh / max(usable_battery_per_set_kwh, 0.001))
    generator_input_energy_kwh = total_mission_energy_kwh / max(generator_efficiency, 0.001)
    fuel_gallons_equivalent = generator_input_energy_kwh / max(fuel_energy_kwh_per_gal, 0.001)
    total_joules = total_mission_energy_kwh * 3_600_000.0
    return {
        "missions_in_horizon": missions,
        "total_mission_energy_kwh": total_mission_energy_kwh,
        "total_mission_energy_joules": total_joules,
        "battery_sets_without_recharge": battery_sets_without_recharge,
        "generator_input_energy_kwh": generator_input_energy_kwh,
        "fuel_gallons_equivalent": fuel_gallons_equivalent,
    }
```

Report wording should make clear this is an energy-equivalence planning lens, not a direct fuel logistics recommendation.

## 4. Contested-delay stochastic lens

Add an optional stochastic interruption/delay model.

Concept:

- A run may experience delay/interruption.
- During delay, the vehicle enters low-power hover/loiter state.
- Mission resumes at the point of interruption.
- The report shows average delay and extra energy burden.

Recommended simple implementation:

```python
def sample_contested_delay(
    rng,
    enabled: bool,
    probability: float,
    mean_delay_hr: float,
    sigma_delay_hr: float,
) -> float:
    if not enabled:
        return 0.0
    if rng.random() > probability:
        return 0.0
    return max(0.0, rng.normal(mean_delay_hr, sigma_delay_hr))
```

Energy impact:

```python
extra_hover_energy_kwh = delay_hr * hover_power_kw
```

Where:

```python
hover_power_kw = vehicle.average_power_kw * hover_power_fraction
```

Recommended default:

- `hover_power_fraction = 0.25`
- `delay_probability = 0.15`
- `mean_delay_hr = 1.0`
- `sigma_delay_hr = 0.25`

Report output:

- Average contested delay
- P80/P95 contested delay
- Extra hover energy
- Percent mission-energy increase from delay

## 5. Model-reasonableness tests

Add `tests/test_model_reasonableness.py` with guardrails:

- Increasing payload speed increases energy for the same route.
- Return-to-start increases payload energy.
- Larger search area increases energy.
- Smaller track spacing increases search energy.
- Higher current burden increases energy or duration.
- Lower usable battery fraction reduces available energy margin.
- ISR loop distance affects loop time and completed loops.
- Enabling contested delay increases average duration and energy.

These tests are not final validation. They prevent obvious model regressions.

## 6. Deferred items

- Multi-area Search/MCM geometry support should return, but it is a larger mission-builder feature and should not be mixed with speed-power or stockpile logic.
- REMUS 600/620-derived public-facing entries are now represented through the validated project-note catalog mappings where listed.
- Battery temperature modeling should remain a generalized penalty until a literature source or SME input is selected.
