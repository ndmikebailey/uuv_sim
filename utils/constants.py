"""Application constants and static planning data."""

from __future__ import annotations

APP_NAME = "UUV Mission Planning and Energy Simulator"
APP_VERSION = "v4-beta"
ENERGY_MODEL_VERSION = "energy_model_v4_beta"
VEHICLE_CATALOG_VERSION = "vehicle_catalog_v4_public_baseline"
USER_AGENT = "uuv-capstone-gradio/0.3 (planning-scale research tool)"
REQUEST_TIMEOUT = 25
MONTE_CARLO_RUNS = 100
EARTH_RADIUS_KM = 6371.0088

OPEN_METEO_WEATHER_URL = "https://api.open-meteo.com/v1/forecast"
OPEN_METEO_MARINE_URL = "https://marine-api.open-meteo.com/v1/marine"

MISSION_TYPES = ["ISR", "Area Search / MCM", "Route / Transit"]
ISR_MISSIONS = {"ISR", "Intelligence, Surveillance, and Reconnaissance"}
PAYLOAD_MISSIONS = {"Payload", "Payload Delivery", "Delivery", "Route / Transit", "Endurance / Transit", "Transit"}
SEARCH_MISSIONS = {"Area Search / MCM", "Area Search", "MCM", "Mine Countermeasures", "Search"}

REGION_PRESETS = {
    "Guam": (13.4443, 144.7937, 8),
    "Saipan": (15.1778, 145.7500, 9),
    "Tinian": (14.9997, 145.6197, 10),
    "Rota": (14.1693, 145.2444, 10),
    "Palau": (7.5150, 134.5825, 8),
    "Yap": (9.5167, 138.1167, 8),
    "Chuuk": (7.4167, 151.7833, 8),
    "Pohnpei": (6.9667, 158.2167, 8),
    "Majuro": (7.1164, 171.1850, 8),
}
