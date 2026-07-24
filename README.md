---
title: UUV Mission Planning and Energy Simulator
emoji: 🌊
colorFrom: blue
colorTo: gray
sdk: gradio
sdk_version: 6.16.0
python_version: 3.11
app_file: app.py
pinned: false
---

# UUV Mission Planning and Energy Simulator

Release `v1` is an academic planning tool for estimating unmanned underwater vehicle (UUV) mission energy, endurance, battery or vehicle inventory, and sustainment demand.

[Open the hosted application on Hugging Face](https://huggingface.co/spaces/reddiverdown/uuv-sim)

## What the Application Does

The application supports three mission types:

- `ISR` patrols using a line, rectangle, or polygon
- `Area Search / MCM` using one or more rectangles or polygons
- `Route / Transit` using a line route

Users can draw a mission on the map or enter a mission manually. The simulator combines the selected geometry, vehicle, battery inventory, environmental conditions, and simulation settings to produce:

- A mission decision brief
- Energy and endurance estimates
- Battery or vehicle inventory requirements
- Mission and uncertainty graphics
- A meteorological and oceanographic assessment
- A multi-mission sustainment outlook for `1 week`, `1 month`, `3 months`, or `6 months`
- A downloadable HTML mission report
- A downloadable mission package that can be loaded into a later session

## Use the Hosted Application

No installation is required.

1. Open the [UUV Simulator](https://huggingface.co/spaces/reddiverdown/uuv-sim).
2. Confirm that the build label shows `Current build: v1`.
3. Select `1. Mission Builder` to draw a mission or `2. Single-UUV Simulator` to enter it manually.
4. Configure the vehicle, battery inventory, environment, and simulation mode.
5. Select `Run UUV Energy Simulation`.
6. Select `Go to Results` when the run completes.

Use `Download Mission Report` to save the report as HTML. Use `Download Mission Package` to save the report, mission record, and energy-planner data together. Load that ZIP file under `Saved mission package` to restore the mission in a later session.

Session files are temporary. Select `Delete Session Files` after downloading them when immediate removal is required. They are also removed when the application session expires.

## Run a Local Copy on Windows

1. Select `Code` and `Download ZIP` on the [GitHub repository](https://github.com/ndmikebailey/uuv_sim).
2. Extract the ZIP file.
3. Double-click `start_uuv_sim.bat`.
4. Allow the first startup to create the local Python environment and install the required packages.

The application opens in the default browser. Press `Ctrl+C` in the Python window, or close that window, to stop the local application.

Python 3.10 or later and an internet connection are required for the first local startup. The map and live environmental services also require internet access.

### Command-Line Startup

```powershell
python -m pip install -r requirements.txt
python app.py
```

The local application normally opens at `http://127.0.0.1:7860`.

## Important Use Notes

- Review every retained default before using a result.
- Changing the simulator mission type clears an incompatible loaded map mission.
- Environmental lookup can use current conditions or a user-selected UTC date and time.
- Multi-area Search/MCM calculations preserve each area’s lane plan and include center-to-center transit in the order the areas were drawn.
- Select `Multi-mission planning` to display the sustainment outlook near the top of the report.
- The model rejects invalid negative, nonfinite, out-of-range, and noninteger inputs where those values are not mathematically valid.
- The application is a research and planning aid. It is not an operational navigation, tactical approval, safety, or meteorological and oceanographic authority.

## Verification

Run the complete automated test suite from the project folder:

```powershell
python -m pytest -q
```

The tests cover geometry, environmental data handling, mission calculations, energy and battery logic, sustainment projections, report generation, saved mission packages, and application callbacks.

## Repository Contents

```text
app/          User interface, report presentation, and map component
core/         Mission geometry, energy, battery, and sustainment calculations
data/         Vehicle catalog and public-source register
models/       Mission, vehicle, and environmental data structures
services/     Environmental providers and session report packaging
tests/        Automated verification suite
utils/        Shared constants and input parsing
```

## License and Notice

See [LICENSE](LICENSE) and [NOTICE.md](NOTICE.md). The software is provided for academic research, review, and educational use without operational approval or warranty.
