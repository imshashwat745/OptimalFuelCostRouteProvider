from .config import env

MPG: float = float(env("SPOTTER_MPG", 10.0))
MAX_RANGE_MILES: float = float(env("SPOTTER_MAX_RANGE_MILES", 500.0))
MAX_OFF_ROUTE_MILES: float = float(env("SPOTTER_MAX_OFF_ROUTE_MILES", 5.0))

TANK_CAPACITY_GALLONS: float = MAX_RANGE_MILES / MPG   # derived
FUEL_AT_DEPARTURE: float = TANK_CAPACITY_GALLONS        # always start full

MIN_TRIP_DISTANCE_MILES: float = 1.0

DEFAULT_BUFFER_GALLONS: float = 2.0
DEFAULT_GREEDY_FILL: bool = False
