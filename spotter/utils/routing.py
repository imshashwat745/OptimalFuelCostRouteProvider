import requests
import pandas as pd
from shapely.geometry import Point, LineString
from shapely.strtree import STRtree

from ..core.config import GOOGLE_API_KEY, OSRM_BASE_URL
from ..core.constants import MAX_OFF_ROUTE_MILES
from ..exceptions import GeocodingError, RoutingError
from .geo import haversine, point_on_segment
from django.core.cache import cache
import re


# ── Geocoding ────────────────────────────────────────────────────────────────


def geocode_location(location_name: str) -> tuple[float, float]:
    if not GOOGLE_API_KEY:
        raise GeocodingError("GOOGLE_API_KEY is not set in environment.")

    cache_key = f"geocode:{location_name.strip().lower()}"
    cache_key = "geocode:" + re.sub(r"[^a-z0-9]", "_", location_name.strip().lower())
    cached = cache.get(cache_key)

    if cached:
        return cached

    url = (
        "https://maps.googleapis.com/maps/api/geocode/json"
        f"?address={requests.utils.quote(location_name)}&key={GOOGLE_API_KEY}"
    )
    try:
        resp = requests.get(url, timeout=10).json()
    except requests.RequestException as exc:
        raise GeocodingError(f"Network error geocoding '{location_name}': {exc}") from exc

    if resp.get("status") == "OK" and resp.get("results"):
        loc = resp["results"][0]["geometry"]["location"]
        coords = (loc["lat"], loc["lng"])
        cache.set(cache_key, coords, timeout=60 * 60 * 24 * 30)  # 30 days — coords don't change
        return coords

    raise GeocodingError(
        f"Could not geocode '{location_name}'. API status: {resp.get('status')}."
    )


# ── OSRM Routes ───────────────────────────────────────────────────────────────

def get_routes(
    start_coords: tuple[float, float],
    end_coords: tuple[float, float],
) -> list[dict]:
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

    return [
        {
            "distance_miles": r["distance"] * 0.000621371,
            "geometry": r["geometry"],
        }
        for r in data["routes"]
    ]


# ── Station loading + mapping ─────────────────────────────────────────────────

def load_stations(filepath: str) -> list[dict]:
    df = pd.read_csv(filepath)
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
    return (
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


def map_stations_to_route(
    stations: list[dict],
    route_coords: list[tuple[float, float]],
) -> tuple[list[dict], float]:
    n = len(route_coords)
    cumulative = [0.0] * n
    seg_index: list[int] = []
    segments: list[LineString] = []

    for i in range(1, n):
        lon1, lat1 = route_coords[i - 1]
        lon2, lat2 = route_coords[i]
        cumulative[i] = cumulative[i - 1] + haversine(lat1, lon1, lat2, lon2)
        segments.append(LineString([(lon1, lat1), (lon2, lat2)]))
        seg_index.append(i - 1)

    total_route_len = cumulative[-1]
    tree = STRtree(segments)
    search_radius_deg = MAX_OFF_ROUTE_MILES / 69.0 + 0.02

    lons, lats = zip(*route_coords)
    pad = search_radius_deg * 1.3
    min_lat, max_lat = min(lats) - pad, max(lats) + pad
    min_lon, max_lon = min(lons) - pad, max(lons) + pad

    valid: list[dict] = []
    for station in stations:
        slat, slon = station["lat"], station["lon"]
        if not (min_lat <= slat <= max_lat and min_lon <= slon <= max_lon):
            continue

        pt = Point(slon, slat)
        candidate_idxs = tree.query(pt.buffer(search_radius_deg))

        best_dist, best_mile = float("inf"), 0.0
        for ci in candidate_idxs:
            ri = seg_index[ci]
            lon1, lat1 = route_coords[ri]
            lon2, lat2 = route_coords[ri + 1]
            dist, offset = point_on_segment(slat, slon, lat1, lon1, lat2, lon2)
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
