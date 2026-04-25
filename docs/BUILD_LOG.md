# UUV Mission Planning Tool Build Log

Configuration-controlled build history for the UUV mission planning and energy simulation tool.

Current active build: **v3.0-alpha**  
Date established: **2026-04-25**  
Current entrypoint: `app/main.py` with Hugging Face compatibility launcher `app.py`

## Archived Version Files

The repository old-version snapshots currently align to these monolithic Gradio builds:

| Version | Snapshot file | Build role |
| --- | --- | --- |
| v2.1 | `Old Versions/uuv_merged_gradio_app_v2_1.py` | Clean merged Gradio build for Colab review. |
| v2.2 | `Old Versions/uuv_merged_gradio_app_v2_2.py` | Expanded integrated Gradio mission-planning build. |
| v2.2.1 | `Old Versions/uuv_merged_gradio_app_v2_2_1.py` | Mission Builder callback output alignment fix. |
| v2.2.2 | `Old Versions/uuv_merged_gradio_app_v2_2_2.py` | Search-pattern/report overlay iteration. |
| v2.2.3 | `Old Versions/uuv_merged_gradio_app_v2_2_3.py` | Report cleanup: Monte Carlo chart scaling and swath overlay readability. |

## Rough Build History

### v0.1 - Original Basic UUV Simulator

Baseline Gradio/Colab simulator.

* Standalone single-UUV energy simulation.
* Primary purpose was to calculate basic endurance / energy use from user-entered UUV parameters.
* Original "simulator only" build, not yet a mission-planning tool.

### v0.2 - Colab Workflow Validation

Development moved through Google Colab.

* Confirmed Gradio app execution in Colab.
* Confirmed output could run interactively.
* Debug print/output was present but later identified as unnecessary.
* Established the working development path: Colab first, hosted app later.

### v0.3 - Basic Output / Table Display

Early simulator output formatting.

* Produced tabular outputs for UUV energy/load information.
* Display was functional but not fully readable.
* Later requirement: move output table below input area and use full page width.

### v0.4 - Environmental Sandbox, Separate from Simulator

Separate Streamlit environmental test app.

* Folium map with rectangle draw.
* Area and centroid calculation.
* Open-Meteo marine and weather API calls.
* Current, sea-surface temperature, sea level, wind, visibility, pressure, precipitation, and related hourly data.

### v0.5 - Environmental Uplift Preview

Environmental data began feeding energy assumptions.

* Added current-based power penalty.
* Added water-temperature penalty.
* Produced environmental power multiplier.
* Still separate from the original simulator.

### v0.6 - Streamlit Limitation Identified

Architecture issue identified.

* Streamlit worked for the sandbox.
* Decision made not to use Streamlit going forward.
* Target shifted to Gradio, Colab workflow, and later Hugging Face hosting.

### v0.7 - Gradio / Leaflet Map Proof of Concept

Map test rebuilt in Gradio.

* Leaflet map embedded in a Gradio iframe.
* Rectangle draw worked.
* Geometry output included centroid, width, height, area, and bounds.

### v1.0 - Integration Direction Established

Project direction changed from simulator-only to integrated planning tool.

* Keep single-UUV simulator standalone.
* Add optional mission builder.
* Mission builder should feed simulator only when used.
* Core app remains Gradio-based.

### v1.2 - Mission Builder Concept

Mission geometry requirements defined.

* Rectangle draw for ISR / MCM / area-search missions.
* Line draw planned for payload delivery missions.
* Geometry outputs: centroid, area, bounds; later distance and heading.
* Environmental data pulled from mission centroid.

### v1.5 - Simulator + Mission Builder Integration Plan

Defined how the two separate builds should merge.

* Mission Builder tab.
* Single-UUV Simulator tab.
* Report / analysis tab.
* Mission Builder pre-populates simulator inputs when available.
* Simulator remains manually operable without mission data.

### v1.7 - Reserve Margin Logic Change

User-facing reserve margin reduced.

* Reserve margin should move into background logic.
* It should be hard-coded from manufacturer recommendation when available.
* If no recommendation exists, estimate based on battery type, battery health, and return-to-base requirement.

### v1.8 - Output Readability Improvements

UI cleanup requirements added.

* Remove unnecessary debug print behavior.
* Clean simulator output table.
* Move table below main inputs.
* Use full-width layout for readability.

### v1.9 - METOC Report Concept

Report page expanded.

* Add METOC-style risk section.
* Include weather, tide/current, surf/sea condition proxy, and temperature.
* Initially informational; not necessarily part of energy equations.
* Purpose is to provide operational context for interpreting simulation results.

### v2.0 - Integrated Gradio Baseline

Integrated Gradio-based UUV mission-planning and single-mission simulation target baseline.

* Standalone single-UUV simulator.
* Optional mission builder.
* Leaflet map embedded in Gradio.
* Area mission geometry capture.
* Open-Meteo marine/weather pull from centroid.
* Environmental assumptions available to simulator.
* Reserve margin handled internally.
* Clean full-width output tables.
* METOC-style risk report.
* Ready for Git organization and later Hugging Face hosting.

### v2.1 - Clean Merged Gradio Build

First saved integrated Gradio snapshot.

* Consolidated Mission Builder, simulator, and results workflow into one Gradio script.
* Preserved standalone simulator operation.
* Used Leaflet / OpenStreetMap iframe geometry capture.
* Stored as `uuv_merged_gradio_app_v2_1.py`.

### v2.2 - Expanded Planning Build

Integrated mission-planning behavior matured.

* Improved mission-context handoff between builder and simulator.
* Added payload delivery line-route geometry path.
* Added richer environmental and report outputs.
* Stored as `uuv_merged_gradio_app_v2_2.py`.

### v2.2.1 - Callback Alignment Fix

Mission Builder output alignment fix.

* Corrected Gradio callback output ordering.
* Stabilized mission prefill values and state handoff.
* Stored as `uuv_merged_gradio_app_v2_2_1.py`.

### v2.2.2 - Search Overlay Iteration

Report overlay and geometry iteration.

* Added/expanded search-pattern visualization.
* Improved connection between swath spacing and search-lane report graphic.
* Stored as `uuv_merged_gradio_app_v2_2_2.py`.

### v2.2.3 - Report Cleanup Build

Last monolithic alpha precursor before modular refactor.

* Improved Monte Carlo chart scaling.
* Improved search-pattern overlay readability.
* Added polygon-search experimentation and mission-map snapshot direction.
* Stored as `uuv_merged_gradio_app_v2_2_3.py`.

## v3.0-alpha - Modular Research Codebase

Current active alpha build.

* Refactored monolithic script into modular architecture:
  * `app/` for Gradio entrypoint, UI wiring, and Leaflet component.
  * `core/` for pure geometry, mission, energy, and environmental uplift logic.
  * `services/` for Open-Meteo marine/weather clients and METOC fusion.
  * `models/` for dataclasses: `MissionArea`, `EnvironmentData`, and `VehicleState`.
  * `utils/` for constants and parsing helpers.
  * `tests/` for basic regression examples.
* Removed Streamlit dependency from active code.
* Added Hugging Face compatibility via `app.py` and `requirements.txt`.
* Preserved centroid behavior:
  * Rectangle centroid remains midpoint of bounds.
  * Payload route centroid remains midpoint between first and last route point.
  * Polygon centroid is computed in the Python geometry core from local projected coordinates.
* Preserved environmental uplift behavior:
  * Current-based route/search penalties remain consistent with v2 logic.
  * Temperature penalty remains consistent with v2 logic.
* Added full polygon support for ISR and Area Search / MCM mission loading.
* Added mission map snapshot report panel beside the search-pattern swath overlay.
* Added tests for geometry area and environmental uplift.

## Project Alignment

The academic project objective is to connect UUV mission profiles, platform characteristics, and long-term energy sustainment requirements for denied or limited logistics environments.

The PMP identifies the analytical models and Python scripts as configuration-controlled project artifacts, so the codebase is now treated as a formal project deliverable rather than an informal demo.
