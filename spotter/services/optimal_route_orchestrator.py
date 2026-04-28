import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

from django.conf import settings

from ..core.config import FUEL_CSV_FILENAME
from ..core.constants import (
    FUEL_AT_DEPARTURE, MAX_RANGE_MILES, MIN_TRIP_DISTANCE_MILES,
    MPG, TANK_CAPACITY_GALLONS,
)
from ..exceptions import NoViableRouteError, SameDestinationError
from ..utils.geo import calculate_haversine_distance
from ..utils.spatial_routing_client import fetch_coordinates_for_address, fetch_osrm_route_alternatives, load_stations_in_memory, find_stations_along_route_corridor
from ..utils.fuel_optimization_engine import calculate_optimal_fuel_stops

logger = logging.getLogger(__name__)


def _evaluate_route_alternative(
    idx: int,
    route: dict,
    all_stations: list[dict],
    csv_path: str,
    buffer_gallons: float,
    greedy_fill: bool,
) -> tuple[int, dict | None, float]:
    """Evaluate a single route alternative. Returns (index, result_dict, cost)."""
    logger.info("Evaluating route %d (%.1f mi)", idx + 1, route["distance_miles"])
    valid_stations, route_len = find_stations_along_route_corridor(
        all_stations, route["geometry"]["coordinates"],
        _csv_path=csv_path,
    )
    try:
        stops, cost = calculate_optimal_fuel_stops(
            valid_stations, route_len,
            max_range_miles=MAX_RANGE_MILES,
            mpg=MPG,
            tank_capacity_gallons=TANK_CAPACITY_GALLONS,
            fuel_at_departure=FUEL_AT_DEPARTURE,
            buffer_gallons=buffer_gallons,
            greedy_fill=greedy_fill,
        )
    except NoViableRouteError as exc:
        logger.warning("Route %d skipped: %s", idx + 1, exc)
        return idx, None, float("inf")

    logger.info("Route %d → $%.2f | %d stops", idx + 1, cost, len(stops))
    result = {
        "route_option": idx + 1,
        "total_distance_miles": round(route["distance_miles"], 2),
        "total_fuel_cost": cost,
        "fuel_stops": stops,
        "route_geometry": route["geometry"],
    }
    return idx, result, cost


def calculate_cheapest_route(
    start_address: str,
    destination_address: str,
    *,
    buffer_gallons: float,
    greedy_fill: bool,
) -> dict:
    # ── Same-destination guard ─────────────────────────────────────────────
    if start_address.strip().lower() == destination_address.strip().lower():
        raise SameDestinationError(
            f"Start and destination are the same: '{start_address}'."
        )

    csv_path = os.path.join(settings.BASE_DIR, "spotter", "data", FUEL_CSV_FILENAME)

    # ── Parallel: geocode both locations + pre-warm station cache ──────────
    logger.info("Geocoding '%s' → '%s'", start_address, destination_address)
    with ThreadPoolExecutor(max_workers=3) as ex:
        future_start_coords = ex.submit(fetch_coordinates_for_address, start_address)
        future_dest_coords = ex.submit(fetch_coordinates_for_address, destination_address)
        future_stations = ex.submit(load_stations_in_memory, csv_path)
        start_coords = future_start_coords.result()
        finish_coords = future_dest_coords.result()
        all_stations = future_stations.result()

    if calculate_haversine_distance(*start_coords, *finish_coords) < MIN_TRIP_DISTANCE_MILES:
        raise SameDestinationError(
            f"'{start_address}' and '{destination_address}' resolve to the same coordinates."
        )

    # ── Fetch routes ───────────────────────────────────────────────────────
    routes = fetch_osrm_route_alternatives(start_coords, finish_coords)
    logger.info("%d route(s) returned by OSRM", len(routes))

    # ── Evaluate each route in parallel, keep cheapest ────────────────────
    best_cost = float("inf")
    best_result = None

    if len(routes) > 1:
        with ThreadPoolExecutor(max_workers=len(routes)) as ex:
            futures = [
                ex.submit(
                    _evaluate_route_alternative, idx, route,
                    all_stations, csv_path, buffer_gallons, greedy_fill,
                )
                for idx, route in enumerate(routes)
            ]
            for future in as_completed(futures):
                idx, result, cost = future.result()
                if result and cost < best_cost:
                    best_cost = cost
                    best_result = result
    else:
        for idx, route in enumerate(routes):
            _, result, cost = _evaluate_route_alternative(
                idx, route, all_stations, csv_path, buffer_gallons, greedy_fill,
            )
            if result and cost < best_cost:
                best_cost = cost
                best_result = result

    if best_result is None:
        raise NoViableRouteError(
            "No viable route found across all alternatives. "
            "Check station CSV coverage and vehicle range."
        )

    return best_result

