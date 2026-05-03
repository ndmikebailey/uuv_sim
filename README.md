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

`v3.3-research-dev` is a Gradio-based research tool for planning single-UUV missions, estimating energy requirements, and reviewing mission geometry with METOC context.

## Status

This repository is an academic research artifact. It is intended for controlled dry runs, early physical-test planning, and model-development review. It is not an operational navigation, safety, or tactical decision tool.

## Run Locally

```bash
pip install -r requirements.txt
python app.py
```

## Structure

```text
app/          Gradio entrypoint, UI wiring, and Leaflet map component
core/         Pure geometry, mission, energy, and environmental uplift logic
services/     Open-Meteo clients, Copernicus salinity enrichment, METOC fusion, and internal traceability logging
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

```bash
python test.py
```
