import math
import numpy as np


def calculate_haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 3958.8
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(d_lon / 2) ** 2
    )
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def project_point_to_line_segment(
    lat: float, lon: float,
    lat1: float, lon1: float,
    lat2: float, lon2: float,
) -> tuple[float, float]:
    """
    Returns (perpendicular_distance_miles, mile_offset_along_segment).
    Uses cos(lat)-scaled Cartesian frame so dot-product projection is
    geometrically correct at any latitude.
    """
    seg_len = calculate_haversine_distance(lat1, lon1, lat2, lon2)
    if seg_len < 1e-9:
        return calculate_haversine_distance(lat, lon, lat1, lon1), 0.0

    cos_lat = math.cos(math.radians((lat1 + lat2) / 2.0))
    dx, dy = lat2 - lat1, (lon2 - lon1) * cos_lat
    px, py = lat - lat1, (lon - lon1) * cos_lat

    t = max(0.0, min(1.0, (px * dx + py * dy) / (dx * dx + dy * dy)))
    closest_lat = lat1 + t * (lat2 - lat1)
    closest_lon = lon1 + t * (lon2 - lon1)

    return calculate_haversine_distance(lat, lon, closest_lat, closest_lon), t * seg_len


def cumulative_distances_np(
    coords: list[tuple[float, float]],
) -> tuple[np.ndarray, float]:
    """
    Vectorised cumulative route distances (miles).
    coords: list of (lon, lat) pairs (GeoJSON order).
    Returns (cumulative array of length N, total_route_length).
    """
    arr = np.asarray(coords, dtype=np.float64)         # shape (N, 2)
    lons, lats = arr[:, 0], arr[:, 1]

    lat1, lat2 = np.radians(lats[:-1]), np.radians(lats[1:])
    dlat = lat2 - lat1
    dlon = np.radians(lons[1:] - lons[:-1])

    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    seg_miles = 3958.8 * 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))

    cumulative = np.empty(len(coords), dtype=np.float64)
    cumulative[0] = 0.0
    np.cumsum(seg_miles, out=cumulative[1:])

    return cumulative, float(cumulative[-1])
