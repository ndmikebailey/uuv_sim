"""Optional Copernicus Marine salinity and density provider."""

from __future__ import annotations

import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from models.environment_model import EnvironmentData
from utils.constants import (
    COPERNICUS_DENSITY_VARIABLE_CANDIDATES,
    COPERNICUS_SALINITY_DATASET_ID,
    COPERNICUS_SALINITY_PRODUCT_ID,
    COPERNICUS_SALINITY_VARIABLE_CANDIDATES,
)


def _iso_day(when_utc: datetime | None) -> str:
    """Return a UTC day string for a compact Copernicus query."""
    when = when_utc or datetime.now(timezone.utc)
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return when.astimezone(timezone.utc).date().isoformat()


def _as_float(value: Any) -> float | None:
    """Return a float when possible."""
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def _available_variables(dataset: Any) -> list[str]:
    """Return variable names from an xarray-like dataset."""
    names: list[str] = []
    for attr in ("data_vars", "variables"):
        values = getattr(dataset, attr, None)
        if values is None:
            continue
        try:
            names.extend([str(name) for name in values.keys()])
        except AttributeError:
            names.extend([str(name) for name in values])
    return sorted(set(names))


def _nearest_value(dataset: Any, names: list[str]) -> tuple[float | None, str | None]:
    """Extract a mean/nearest scalar from the first available variable candidate."""
    available = _available_variables(dataset)
    for name in names:
        if name not in available:
            continue
        variable = dataset[name]
        try:
            value = variable.mean(skipna=True).item()
        except Exception:
            try:
                value = variable.values
                while hasattr(value, "flat"):
                    value = value.flat[0]
                    break
            except Exception:
                value = None
        numeric = _as_float(value)
        if numeric is not None:
            return numeric, name
    return None, None


def get_copernicus_salinity_density(
    lat: float,
    lon: float,
    when_utc: datetime | None = None,
    depth_m: float = 0.0,
    enabled: bool = True,
) -> EnvironmentData:
    """
    Retrieve salinity and density from Copernicus Marine when configured.

    Credentials are never hardcoded or written by this provider. The Copernicus Marine
    toolbox may use environment variables or its own local login configuration.
    """
    query_day = _iso_day(when_utc)
    query_params: dict[str, object] = {
        "provider": "copernicus_marine",
        "product_id": COPERNICUS_SALINITY_PRODUCT_ID,
        "dataset_id": COPERNICUS_SALINITY_DATASET_ID,
        "latitude": lat,
        "longitude": lon,
        "depth_m": depth_m,
        "query_day": query_day,
        "enabled": enabled,
        "bbox_half_degree": 0.05,
    }
    if not enabled:
        return EnvironmentData(
            salinity_source="off",
            salinity_error="Copernicus Marine salinity provider is disabled.",
            salinity_query_params=query_params,
        )

    try:
        import copernicusmarine  # type: ignore[import-not-found]
    except ImportError:
        return EnvironmentData(
            salinity_source="copernicus_unavailable",
            salinity_error="Copernicus Marine toolbox is not installed.",
            salinity_query_params=query_params,
        )

    username = os.environ.get("COPERNICUSMARINE_USERNAME")
    password = os.environ.get("COPERNICUSMARINE_PASSWORD")
    kwargs: dict[str, object] = {
        "dataset_id": COPERNICUS_SALINITY_DATASET_ID,
        "minimum_longitude": float(lon) - 0.05,
        "maximum_longitude": float(lon) + 0.05,
        "minimum_latitude": float(lat) - 0.05,
        "maximum_latitude": float(lat) + 0.05,
        "start_datetime": f"{query_day}T00:00:00Z",
        "end_datetime": f"{query_day}T23:59:59Z",
        "variables": list(COPERNICUS_SALINITY_VARIABLE_CANDIDATES) + list(COPERNICUS_DENSITY_VARIABLE_CANDIDATES),
    }
    if depth_m is not None:
        kwargs["minimum_depth"] = max(float(depth_m) - 0.5, 0.0)
        kwargs["maximum_depth"] = max(float(depth_m) + 0.5, 0.0)
    if username and password:
        kwargs["username"] = username
        kwargs["password"] = password
        query_params["credential_source"] = "environment"
    else:
        query_params["credential_source"] = "toolbox_local_config_or_public"

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            kwargs["output_directory"] = tmpdir
            kwargs["force_download"] = True
            subset_result = copernicusmarine.subset(**kwargs)
            dataset: Any | None = None
            if hasattr(subset_result, "open_dataset"):
                dataset = subset_result.open_dataset()
            elif hasattr(subset_result, "file_path"):
                try:
                    import xarray as xr  # type: ignore[import-not-found]

                    dataset = xr.open_dataset(subset_result.file_path)
                except Exception:
                    dataset = None
            elif isinstance(subset_result, (str, Path)):
                try:
                    import xarray as xr  # type: ignore[import-not-found]

                    dataset = xr.open_dataset(subset_result)
                except Exception:
                    dataset = None
            elif hasattr(subset_result, "__getitem__"):
                dataset = subset_result

            if dataset is None:
                return EnvironmentData(
                    salinity_source="copernicus_error",
                    salinity_error="Copernicus Marine subset completed but no readable dataset was returned.",
                    salinity_query_params=query_params,
                )

            salinity, salinity_variable = _nearest_value(dataset, list(COPERNICUS_SALINITY_VARIABLE_CANDIDATES))
            density, density_variable = _nearest_value(dataset, list(COPERNICUS_DENSITY_VARIABLE_CANDIDATES))
            available = _available_variables(dataset)
            metadata = {
                "available_variables": available,
                "salinity_variable": salinity_variable,
                "density_variable": density_variable,
            }
            if salinity is None and density is None:
                return EnvironmentData(
                    salinity_source="copernicus_error",
                    salinity_error=f"No configured salinity or density variable found. Available variables: {', '.join(available)}",
                    salinity_query_params=query_params,
                    salinity_metadata=metadata,
                )
            return EnvironmentData(
                sea_surface_salinity_psu=salinity,
                sea_water_density_kg_m3=density,
                salinity_source="copernicus_marine",
                salinity_query_params=query_params,
                salinity_metadata=metadata,
            )
    except Exception as exc:
        return EnvironmentData(
            salinity_source="copernicus_error",
            salinity_error=str(exc),
            salinity_query_params=query_params,
        )
