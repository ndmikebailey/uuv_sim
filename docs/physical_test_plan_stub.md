# Physical Test Plan Stub

## Purpose

Define the minimum planning record needed to compare UUV Sustainment Simulation predictions with later physical-test observations.

## Scope

This stub supports academic research, planning-support analysis, and early model validation. It is not an operational test procedure.

## Pre-test Configuration Record

Record the exact app version, model version, vehicle catalog version, git commit, test date, operator, vehicle configuration, payload assumptions, and environment data source.

## Vehicle/platform Assumptions

Document vehicle name, battery capacity, usable mission energy, endurance speed, transit speed, hotel load, propulsion assumptions, reserve policy, payload mass, and any manufacturer or measured data used.

## Environmental Data Capture

Capture location, time window, water temperature, current speed and direction, wind, weather, salinity if available, sea-state notes, data source, API query parameters, and raw API payload references when available.

## Test Run Record Fields

At minimum, record mission type, geometry type, geometry coordinates, start point, target point if applicable, planned route distance, predicted energy use, predicted time on station, reserve margin, Monte Carlo seed, and output file names.

## Actual vs Predicted Comparison

Compare planned distance, observed distance, planned duration, observed duration, predicted energy use, observed energy use if measured, environmental assumptions, and any deviations from the planned profile.

## Known Limitations

The simulation is a planning-support model. It may not capture all hydrodynamic effects, navigation corrections, vehicle control behavior, battery aging, payload-specific loads, launch/recovery losses, or local environmental variability.

## Safety and Non-operational-use Disclaimer

This software is an academic research and planning-support prototype. It is not approved for operational, tactical, navigational, or safety-critical use.
