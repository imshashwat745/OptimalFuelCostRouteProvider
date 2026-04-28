import functools
import hashlib
import logging
import re

import numpy as np
import pandas as pd
import requests
from shapely.geometry import Point, LineString
from shapely.strtree import STRtree

from django.core.cache import cache

from ..core.config import OSRM_BASE_URL, ORS_API_KEY, FUEL_CSV_FILENAME
from ..core.constants import MAX_OFF_ROUTE_MILES
from ..exceptions import GeocodingError, RoutingError
from .geo import calculate_haversine_distance, project_point_to_line_segment, cumulative_distances_np

logger = logging.getLogger(__name__)


# ── Geocoding ────────────────────────────────────────────────────────────────


def fetch_coordinates_for_address(location_name: str) -> tuple[float, float]:
    if not ORS_API_KEY:
        raise GeocodingError("ORS_API_KEY is not set in config.")

    cache_key = "geocode:" + re.sub(r"[^a-z0-9]", "_", location_name.strip().lower())
    cached = cache.get(cache_key)

    if cached:
        return cached

    url = "https://api.openrouteservice.org/geocode/search"
    headers = {
        "Authorization": ORS_API_KEY
    }
    params = {
        "text": location_name
    }
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=10).json()
    except requests.RequestException as exc:
        raise GeocodingError(f"Network error geocoding '{location_name}': {exc}") from exc

    if resp.get("features"):
        coords_raw = resp["features"][0]["geometry"]["coordinates"]
        coords = (coords_raw[1], coords_raw[0])
        cache.set(cache_key, coords, timeout=60 * 60 * 24 * 30)  # 30 days — coords don't change
        return coords

    raise GeocodingError(
        f"Could not geocode '{location_name}'. API response invalid."
    )

# ── OSRM Routes ───────────────────────────────────────────────────────────────

def fetch_osrm_route_alternatives(
    start_coords: tuple[float, float],
    end_coords: tuple[float, float],
) -> list[dict]:
    # Cache key based on rounded coordinates (5 decimal places ≈ 1m precision)
    key_raw = (
        f"osrm:{start_coords[0]:.5f},{start_coords[1]:.5f}"
        f":{end_coords[0]:.5f},{end_coords[1]:.5f}"
    )
    cache_key = "osrm:" + hashlib.md5(key_raw.encode()).hexdigest()
    cached = cache.get(cache_key)
    if cached:
        logger.debug("OSRM cache hit for %s", key_raw)
        return cached

    coord_str = (
        f"{start_coords[1]},{start_coords[0]};"
        f"{end_coords[1]},{end_coords[0]}"
    )
    url = (
        f"{OSRM_BASE_URL}/route/v1/driving/{coord_str}"
        "?alternatives=true&overview=full&geometries=geojson"
    )
    try:
        resp = requests.get(url, timeout=30)
    except requests.RequestException as exc:
        raise RoutingError(f"Network error contacting OSRM: {exc}") from exc

    if resp.status_code != 200:
        raise RoutingError(f"OSRM returned HTTP {resp.status_code}.")

    data = resp.json()
    if data.get("code") != "Ok":
        raise RoutingError(f"OSRM error: {data.get('message', data.get('code'))}")

    result = [
        {
            "distance_miles": r["distance"] * 0.000621371,
            "geometry": r["geometry"],
        }
        for r in data["routes"]
    ]

    cache.set(cache_key, result, timeout=60 * 60 * 24)  # 24 hours
    return result


# ── Station loading + spatial index (cached per process) ──────────────────────

@functools.lru_cache(maxsize=1)
def _load_and_index_stations_in_memory(csv_path: str) -> tuple[list[dict], STRtree, list[int]]:
    """
    Load station data from CSV once per process.
    Returns (stations_list, station_strtree, strtree_to_station_index).
    """
    logger.info("Loading station data from %s", csv_path)
    df = pd.read_csv(csv_path)
    df["Lat"] = pd.to_numeric(df["Lat"], errors="coerce")
    df["Lng"] = pd.to_numeric(df["Lng"], errors="coerce")
    df["Retail Price"] = pd.to_numeric(df["Retail Price"], errors="coerce")
    df = df.dropna(subset=["Lat", "Lng", "Retail Price"])

    df["_id"] = df["OPIS Truckstop ID"].astype(str) + "_" + df.index.astype(str)
    df["_address"] = (
        df["Address"].astype(str).str.strip()
        + ", " + df["City"].astype(str)
        + ", " + df["State"].astype(str)
    )
    stations = (
        df.rename(columns={
            "_id": "id",
            "Truckstop Name": "name",
            "_address": "address",
            "Retail Price": "price",
            "Lat": "lat",
            "Lng": "lon",
        })[["id", "name", "address", "price", "lat", "lon"]]
        .to_dict("records")
    )

    # Build spatial index on station points
    points = [Point(s["lon"], s["lat"]) for s in stations]
    national_station_spatial_index = STRtree(points)

    logger.info("Loaded %d stations, spatial index built", len(stations))
    return stations, national_station_spatial_index, list(range(len(stations)))


def load_stations_in_memory(filepath: str) -> list[dict]:
    """Public API — returns just the station list (backward compatible)."""
    stations, _, _ = _load_and_index_stations_in_memory(filepath)
    return stations


def find_stations_along_route_corridor(
    stations: list[dict],
    route_coords: list[tuple[float, float]],
    *,
    _csv_path: str | None = None,
) -> tuple[list[dict], float]:
    """
    Find stations within MAX_OFF_ROUTE_MILES of the route and annotate them
    with mile_marker and off_route_miles.
    """
    n = len(route_coords)

    # ── Vectorized cumulative distances along route ───────────────────────
    cumulative, total_route_len = cumulative_distances_np(route_coords)

    # ── Build segment spatial index (for per-station projection) ──────────
    segments: list[LineString] = []
    seg_index: list[int] = []
    for i in range(1, n):
        lon1, lat1 = route_coords[i - 1]
        lon2, lat2 = route_coords[i]
        segments.append(LineString([(lon1, lat1), (lon2, lat2)]))
        seg_index.append(i - 1)

    route_segments_spatial_index = STRtree(segments)
    search_radius_deg = MAX_OFF_ROUTE_MILES / 69.0 + 0.02

    # ── Query station spatial index for candidates near the route ─────────
    # Build a buffered envelope of the route
    route_line = LineString(route_coords)
    route_corridor_polygon = route_line.buffer(search_radius_deg)

    # Get the global station tree
    if _csv_path:
        _, station_tree, _ = _load_and_index_stations_in_memory(_csv_path)
    else:
        # Fallback: use bounding box filter on the passed-in station list
        station_tree = None

    if station_tree is not None:
        candidate_station_idxs = station_tree.query(route_corridor_polygon)
        stations_near_corridor = [stations[i] for i in candidate_station_idxs]
    else:
        # Fallback bounding-box filter (when called without cached tree)
        lons, lats = zip(*route_coords)
        pad = search_radius_deg * 1.3
        min_lat, max_lat = min(lats) - pad, max(lats) + pad
        min_lon, max_lon = min(lons) - pad, max(lons) + pad
        stations_near_corridor = [
            s for s in stations
            if min_lat <= s["lat"] <= max_lat and min_lon <= s["lon"] <= max_lon
        ]

    # ── Project each candidate onto nearest route segment ─────────────────
    valid: list[dict] = []
    for station in stations_near_corridor:
        slat, slon = station["lat"], station["lon"]
        pt = Point(slon, slat)
        candidate_seg_idxs = route_segments_spatial_index.query(pt.buffer(search_radius_deg))

        best_dist, best_mile = float("inf"), 0.0
        for ci in candidate_seg_idxs:
            ri = seg_index[ci]
            lon1, lat1 = route_coords[ri]
            lon2, lat2 = route_coords[ri + 1]
            dist, offset = project_point_to_line_segment(slat, slon, lat1, lon1, lat2, lon2)
            if dist < best_dist:
                best_dist = dist
                best_mile = cumulative[ri] + offset

        if best_dist <= MAX_OFF_ROUTE_MILES:
            s = station.copy()
            s["mile_marker"] = best_mile
            s["off_route_miles"] = round(best_dist, 4)
            valid.append(s)

    valid.sort(key=lambda x: x["mile_marker"])
    return valid, total_route_len
