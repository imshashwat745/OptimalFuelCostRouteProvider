import logging
import os
from concurrent.futures import ThreadPoolExecutor

from django.conf import settings

from ..core.config import FUEL_CSV_FILENAME
from ..core.constants import (
    FUEL_AT_DEPARTURE, MAX_RANGE_MILES, MIN_TRIP_DISTANCE_MILES,
    MPG, TANK_CAPACITY_GALLONS,
)
from ..exceptions import NoViableRouteError, SameDestinationError
from ..utils.geo import haversine
from ..utils.routing import geocode_location, get_routes, load_stations, map_stations_to_route
from ..utils.fuel_optimizer import solve_graph

logger = logging.getLogger(__name__)


def get_optimal_route(
    start_loc: str,
    finish_loc: str,
    *,
    buffer_gallons: float,
    greedy_fill: bool,
) -> dict:
    # ── Same-destination guard ─────────────────────────────────────────────
    if start_loc.strip().lower() == finish_loc.strip().lower():
        raise SameDestinationError(
            f"Start and destination are the same: '{start_loc}'."
        )

    # ── Parallel geocoding ─────────────────────────────────────────────────
    logger.info("Geocoding '%s' → '%s'", start_loc, finish_loc)
    with ThreadPoolExecutor(max_workers=2) as ex:
        f_start = ex.submit(geocode_location, start_loc)
        f_finish = ex.submit(geocode_location, finish_loc)
        start_coords = f_start.result()
        finish_coords = f_finish.result()

    if haversine(*start_coords, *finish_coords) < MIN_TRIP_DISTANCE_MILES:
        raise SameDestinationError(
            f"'{start_loc}' and '{finish_loc}' resolve to the same coordinates."
        )

    # ── Fetch routes ───────────────────────────────────────────────────────
    routes = get_routes(start_coords, finish_coords)
    logger.info("%d route(s) returned by OSRM", len(routes))

    # ── Load station data (once) ───────────────────────────────────────────
    csv_path = os.path.join(settings.BASE_DIR, "spotter", "data", FUEL_CSV_FILENAME)
    all_stations = load_stations(csv_path)

    # ── Evaluate each route, keep cheapest ────────────────────────────────
    best_cost = float("inf")
    best_result = None

    for idx, route in enumerate(routes):
        logger.info("Evaluating route %d (%.1f mi)", idx + 1, route["distance_miles"])
        valid_stations, route_len = map_stations_to_route(
            all_stations, route["geometry"]["coordinates"]
        )
        try:
            stops, cost = solve_graph(
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
            continue

        logger.info("Route %d → $%.2f | %d stops", idx + 1, cost, len(stops))
        if cost < best_cost:
            best_cost = cost
            best_result = {
                "route_option": idx + 1,
                "total_distance_miles": round(route["distance_miles"], 2),
                "total_fuel_cost": cost,
                "fuel_stops": stops,
                "route_geometry": route["geometry"],
            }

    if best_result is None:
        raise NoViableRouteError(
            "No viable route found across all alternatives. "
            "Check station CSV coverage and vehicle range."
        )

    return best_result
