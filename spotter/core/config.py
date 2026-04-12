import os

def env(key: str, default=None) -> str:
    """Read an environment variable, with an optional default."""
    return os.environ.get(key, default)

GOOGLE_API_KEY: str = env("GOOGLE_API_KEY", "")
OSRM_BASE_URL: str = env("OSRM_BASE_URL", "http://router.project-osrm.org")
FUEL_CSV_FILENAME: str = env("SPOTTER_FUEL_CSV", "fuel_prices_geocoded.csv")
