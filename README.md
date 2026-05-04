---
title: UUV Mission Planning and Energy Simulator
emoji: 🌊
colorFrom: blue
colorTo: gray
sdk: gradio
sdk_version: 6.13.0
python_version: 3.11
app_file: app.py
pinned: false
---
# UUV Mission Planning and Energy Simulator

`v3.5-beta` is a Gradio-based research tool for planning single-UUV missions, estimating energy requirements, and reviewing mission geometry with METOC context.

## Status

This repository is an academic research artifact. It is intended for controlled dry runs, early physical-test planning, and model-development review. It is not an operational navigation, safety, or tactical decision tool.

## v3.5-beta Highlights

The v3.5-beta release candidate includes the Mission Builder, Single-UUV Simulator, and Results workflow for Payload, ISR, and Search/MCM mission modes; GPS mission map overlays with engineering snapshots; the NOAA CO-OPS / NOAA WOA23 / standard seawater salinity chain; recharge feasibility and fuel-equivalent sustainment lenses; one-way/non-rechargeable vehicle inventory wording; and report decision brief plus technical traceability sections.

## Run Locally

```bash
pip install -r requirements.txt
python app.py
```

## Structure

```text
app/          Gradio entrypoint, UI wiring, and Leaflet map component
core/         Pure geometry, mission, energy, and environmental uplift logic
services/     Open-Meteo clients, NOAA CO-OPS/WOA23 salinity provider hooks, METOC fusion, and internal traceability logging
models/       Dataclasses for mission, vehicle, and environment state
utils/        Constants and parsing helpers
data/         Vehicle catalog and source register
docs/         Assumptions and validation planning notes
tests/        Regression tests
archive/      Archived monolithic builds
```

## Reproducibility

Each simulation records a Monte Carlo seed. If the operator leaves the seed blank, the app generates one and stores it in the output summary. Re-entering that seed replays the same Monte Carlo sample sequence.

Internal run records preserve traceability for app version, energy model version, vehicle catalog version, git commit when available, mission geometry, raw environmental API payloads, and API query parameters. These records are not advertised as the primary user product.

## Outputs

Current user-facing outputs include:

* Energy Planner Summary
* Energy Storage Equivalence Lens
* METOC Assessment
* Energy Summary
* Battery and Sustainment Summary
* Mission Geometry Summary
* Environmental Inputs
* Sustainment Projection Lens
* Mission Energy Progress and Battery Lens
* Mission Energy Uncertainty Distribution
* Mission Visual Summary

## Tests

Salinity follows the active v3.5 planning hierarchy: NOAA CO-OPS station data when available, NOAA WOA23 climatology when available, and standard seawater assumption otherwise. Copernicus was evaluated during development and removed from the active v3.5 salinity chain. HYCOM/GOFS, SMAP, and Argo remain future enhancement or V&V sources only. Salinity and density are planning modifiers only and are not tactical oceanographic authority. The Sustainment Projection Lens includes a secondary fuel-equivalent estimate using a conservative 10.0 kWh/gal JP-8/diesel tactical-generator planning factor.

```bash
python test.py
```
