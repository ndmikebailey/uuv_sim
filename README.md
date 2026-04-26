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

`v3.1-beta-dev` is a Gradio-based research tool for planning single-UUV missions, estimating energy requirements, and reviewing mission geometry with METOC context.

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
services/     Open-Meteo clients, METOC fusion, and run-record export
models/       Dataclasses for mission, vehicle, and environment state
utils/        Constants and parsing helpers
data/         Vehicle catalog and source register
docs/         Assumptions and validation planning notes
tests/        Regression tests
archive/      Archived monolithic builds
```

## Reproducibility

Each simulation records a Monte Carlo seed. If the operator leaves the seed blank, the app generates one and stores it in the output summary and run-record JSON. Re-entering that seed replays the same Monte Carlo sample sequence.

Run records also include the app version, energy model version, vehicle catalog version, git commit when available, mission geometry JSON, raw environmental API payloads, and API query parameters.

## Outputs

Each run exports:

* run-record JSON
* results CSV
* energy/battery tables
* METOC report card
* mission map snapshot
* search-pattern overlay for Area Search / MCM only

## Tests

```bash
python -m unittest discover -s tests
```
