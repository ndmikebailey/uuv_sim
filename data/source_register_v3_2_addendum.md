# Source Register Addendum - v3.2 Public Vehicle Baseline

This addendum records the open-source vehicle data used to update `data/vehicle_catalog.json` for the v3.2 model-validation branch.

| Vehicle catalog entry | Public source basis | Values used in model | Notes |
| --- | --- | --- | --- |
| REMUS 100B - 1.5 kWh | Public REMUS 100B datasheet | 1.5 kWh, 8 hr endurance, 3 kt nominal speed, 4.5 kt max speed, 6 hr recharge | Included as provisional until the final official HII/Hydroid source file is attached to the repo. |
| REMUS 300 - 1.5 kWh | HII REMUS 300 datasheet | 1.5 kWh, 10 hr endurance, 3 kt nominal speed, 4 kt max speed, 6 hr recharge | Manufacturer source. |
| REMUS 300 - 3.0 kWh Standard | HII REMUS 300 datasheet | 3.0 kWh, 20 hr endurance, 3 kt nominal speed, 4 kt max speed, 12 hr recharge | Manufacturer source. |
| REMUS 300 - 4.5 kWh | HII REMUS 300 datasheet | 4.5 kWh, 30 hr endurance, 3 kt nominal speed, 4 kt max speed, 18 hr recharge | Manufacturer source. |
| Bluefin-9 - 1.5 kWh | Bluefin-9 public technical sheet | 1.5 kWh, 12 hr endurance at 3 kt, 5 kt max speed | Recharge time not published; uses 4 hr/kWh planning estimate. |
| Bluefin-12D - 7.5 kWh | Bluefin-12D public technical sheet | 7.5 kWh, 30 hr endurance at 3 kt, 5 kt max speed | Recharge time not published; uses 4 hr/kWh planning estimate. |
| Iver3 EP - 0.8 kWh | L3Harris Iver3 public specification page | 0.8 kWh, 8 hr conservative endurance from 8-14 hr range, 2.5 kt nominal speed, 4 kt max speed | Recharge time not published; uses 4 hr/kWh planning estimate. |
| Iver4 580 - 0.78 kWh | L3Harris Iver4 public specification page | 0.78 kWh, 6 hr endurance, 4.5 kt survey speed, 5 kt max speed | Recharge time not published; uses 4 hr/kWh planning estimate. |

## Shared planning factors

| Factor | Value | Basis |
| --- | ---: | --- |
| Usable battery fraction | 0.88 | Project engineering planning factor for reserve and battery-health allowance. |
| Missing recharge-time estimate | `4 * battery_kwh` hours | Project planning estimate until manufacturer recharge data are available. |

## Data gaps

- REMUS 600 is not included in this addendum because no source file or hard-number JSON block was provided in the current artifact set.
- Knifefish was removed from the recommended active vehicle catalog until an approved public baseline is identified.
- Any export-controlled, CUI, or distribution-limited compiled table should remain out of the codebase unless release authority confirms it can be used.
