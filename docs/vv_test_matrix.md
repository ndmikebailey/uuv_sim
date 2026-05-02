# V&V Test Matrix

This matrix supports manual testing and later thesis/V&V evidence collection. Tests should use stable geometry, saved screenshots, run summaries, and recorded input values where possible.

| Test ID | Mission type | Feature under test | Inputs to vary | Expected behavior | Evidence to capture | Pass/fail notes |
|---|---|---|---|---|---|---|
| VV-001 | Payload Delivery | Payload delivery route | Draw line route; vary route length and heading | Route distance and heading populate mission geometry; energy scales with route length | Mission Builder text, Mission Geometry Summary, Energy Summary |  |
| VV-002 | Payload Delivery | Return-to-start | Toggle return-to-start on/off for same route | Total distance and energy increase when return-to-start is enabled | Payload report with total distance, P50/P80/P95 energy |  |
| VV-003 | Payload Delivery | Payload weight effect | Future payload weight values when implemented | Heavier payload should increase energy or be explicitly documented as not modeled | UI control, report note, model output delta | Future feature; currently no payload weight UI/model |
| VV-004 | ISR | ISR line patrol | Draw line route; vary patrol length and speed | ISR uses out-and-back loop distance; reports endurance, loop time, and patrol distance | Loaded mission text, ISR planner summary, Mission Visual Summary |  |
| VV-005 | ISR | ISR polygon patrol | Draw polygon patrol boundary | ISR uses perimeter patrol loop and first patrol point METOC lookup | Loaded mission text, ISR loop distance, METOC lookup point |  |
| VV-006 | ISR | ISR partial-loop reporting | Choose geometry/speed/vehicle where endurance leaves partial loop | Report states endurance, partial next-loop distance, and total patrol distance without overstating full loops | Energy Planner Summary, Mission Geometry Summary |  |
| VV-007 | Area Search / MCM | Single-area search | Draw one rectangle or polygon; vary track spacing | Single-area behavior remains unchanged; search area, lane count, orientation, and energy populate | Search report, map visual, uncertainty chart |  |
| VV-008 | Area Search / MCM | Multi-area search | Draw two or more rectangles/polygons | Number of areas and total area are shown; energy uses aggregate area | Loaded mission text, Mission Geometry Summary, Energy Summary |  |
| VV-009 | Area Search / MCM | Multi-area METOC centroid averaging | Draw areas far enough apart to create separate centroids; use mocked or known METOC values if possible | One METOC sample per area centroid; aggregate current uses vector average | METOC sampled points, aggregation method, raw traceability |  |
| VV-010 | Any energy mission | Long battery-swap mission | Select high energy demand, low battery inventory, recharge allowed on/off | Battery shortfall and recharge/swap messaging appear and remain internally consistent | Battery and Sustainment Summary, Energy Planner Summary |  |
| VV-011 | Payload/Search/MCM | Speed-power correction | Run same geometry at low and high speed | Higher speed should not appear unrealistically energy efficient; energy should rise when speed burden dominates | Energy Summary at two speeds, chart screenshots |  |
| VV-012 | All modes | Energy Storage Equivalence Lens | Run small and larger energy missions | kWh, Wh, J, MJ, GJ, TOE, BOE display with useful precision and no misleading zero rounding | Equivalence Lens table screenshot |  |
| VV-013 | All modes | View Results shortcut | Complete simulation then click View Results | Button activates and opens Results/Report tab or gives clear instruction | UI recording or screenshot sequence |  |
| VV-014 | Mission Builder | Load Mission and Go to Simulator shortcut | Draw valid mission geometry and click shortcut | Mission loads, simulator fields prefill, and Single-UUV Simulator tab opens if JS succeeds | UI recording or screenshots before/after click |  |

