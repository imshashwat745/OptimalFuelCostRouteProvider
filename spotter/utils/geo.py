import math


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
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


def point_on_segment(
    lat: float, lon: float,
    lat1: float, lon1: float,
    lat2: float, lon2: float,
) -> tuple[float, float]:
    """
    Returns (perpendicular_distance_miles, mile_offset_along_segment).
    Uses cos(lat)-scaled Cartesian frame so dot-product projection is
    geometrically correct at any latitude.
    """
    seg_len = haversine(lat1, lon1, lat2, lon2)
    if seg_len < 1e-9:
        return haversine(lat, lon, lat1, lon1), 0.0

    cos_lat = math.cos(math.radians((lat1 + lat2) / 2.0))
    dx, dy = lat2 - lat1, (lon2 - lon1) * cos_lat
    px, py = lat - lat1, (lon - lon1) * cos_lat

    t = max(0.0, min(1.0, (px * dx + py * dy) / (dx * dx + dy * dy)))
    closest_lat = lat1 + t * (lat2 - lat1)
    closest_lon = lon1 + t * (lon2 - lon1)

    return haversine(lat, lon, closest_lat, closest_lon), t * seg_len
