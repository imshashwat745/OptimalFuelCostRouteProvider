# Spotter

A Django REST API that computes the optimal fuel stop strategy for long-haul truck routes. Given a start and end location, it finds the cheapest combination of fuel stops along the route using Dijkstra's algorithm across real station price data.

---

## Project Structure

```
proj/
├── config/
│   ├── settings.py
│   └── urls.py
│
├── spotter/
│   ├── api/
│   │   ├── views.py          # HTTP boundary — request/response only
│   │   └── serializers.py    # Input validation and defaults
│   │
│   ├── services/
│   │   └── route_service.py  # Orchestration layer
│   │
│   ├── core/
│   │   ├── constants.py      # Static values (MPG, range, defaults)
│   │   └── config.py         # Environment variable reads
│   │
│   ├── utils/
│   │   ├── geo.py            # Haversine distance, segment projection
│   │   ├── routing.py        # Google Geocoding, OSRM, station mapping
│   │   └── fuel_optimizer.py # Graph construction, Dijkstra, greedy fill
│   │
│   ├── data/
│   │   └── fuel_prices_geocoded.csv
│   │
│   ├── exceptions.py
│   ├── tests.py
│   └── urls.py
│
└── scripts/
    ├── geocode.py            # One-time data pipeline (already run)
    └── normalize.py          # One-time whitespace cleanup (already run)
```

---

## How It Works

### Request Flow

```
GET /api/route/?start=Chicago,IL&finish=Denver,CO
        |
        v
  RouteOptimizerView          api/views.py
  Validates query params
        |
        v
  get_optimal_route()         services/route_service.py
  Orchestrates everything
        |
        |--- geocode_location() x 2    (parallel)     utils/routing.py
        |    Converts city names to (lat, lng)
        |    Cached 30 days in Django cache
        |
        |--- get_routes()                              utils/routing.py
        |    Fetches up to 3 alternative routes
        |    from OSRM (open-source routing engine)
        |
        |--- load_stations()                           utils/routing.py
        |    Reads fuel_prices_geocoded.csv into
        |    a list of station dicts
        |
        +--- For each route:
             |
             |--- map_stations_to_route()              utils/routing.py
             |    Spatially indexes route segments
             |    with an STRtree. Filters stations
             |    within MAX_OFF_ROUTE_MILES. Annotates
             |    each with mile_marker + off_route_miles.
             |
             +--- solve_graph()                        utils/fuel_optimizer.py
                  Builds a directed graph:
                  Start -> stations -> End
                  Edge weight = fuel cost to drive that leg
                  at the price of the departure station.
                  Dijkstra finds cheapest path.
                  Greedy pass decides exact fill amounts.

        Returns cheapest result across all route alternatives.
```

### Optimizer Detail

The optimizer runs in two phases.

**Phase 1 — Dijkstra path selection.** Builds a directed graph where each edge weight is the fuel cost of driving that leg at the originating station's price. `nx.shortest_path` finds the globally cheapest sequence of stops.

**Phase 2 — Greedy fill-amount pass.** Walks the Dijkstra-selected path and decides how many gallons to buy at each stop:

- Default (`greedy_fill=false`): fill to full at every intermediate stop.
- Greedy (`greedy_fill=true`): if a cheaper station exists ahead on the path and is reachable on the current tank, buy only enough to get there. Otherwise fill to full.
- Last stop: buy only what is needed to reach the destination plus the buffer reserve.

---

## API Reference

### `GET /api/route/`

Find the optimal fuel stop plan between two locations.

**Query Parameters**

| Parameter | Required | Type | Default | Description |
|---|---|---|---|---|
| `start` | Yes | string | — | Starting location, e.g. `Chicago, IL` |
| `finish` | Yes | string | — | Destination, e.g. `Denver, CO` |
| `buffer_gallons` | No | float >= 0 | `5.0` | Safety reserve kept in tank at final stop |
| `greedy_fill` | No | boolean | `false` | Buy minimum fuel needed vs. fill to full |

**Example Request**

```
GET /api/route/?start=Chicago,IL&finish=Denver,CO&buffer_gallons=5&greedy_fill=false
```

**Success Response — `200 OK`**

```json
{
  "request": {
    "start": "Chicago, IL",
    "finish": "Denver, CO",
    "buffer_gallons": 5.0,
    "greedy_fill": false
  },
  "optimal_trip": {
    "route_option": 1,
    "total_distance_miles": 920.5,
    "total_fuel_cost": 342.18,
    "fuel_stops": [
      {
        "id": "1042_301",
        "name": "PILOT TRAVEL CENTER #42",
        "address": "I-80, Exit 145, Lincoln, NE",
        "price": 3.429,
        "lat": 40.8136,
        "lon": -96.7026,
        "mile_marker": 463.2,
        "off_route_miles": 0.3,
        "fuel_remaining_on_arrival": 18.4,
        "fuel_filled": 31.6
      }
    ],
    "route_geometry": {
      "type": "LineString",
      "coordinates": [[-87.6298, 41.8781], ["..."], [-104.9903, 39.7392]]
    }
  }
}
```

**`fuel_stops` fields**

| Field | Description |
|---|---|
| `id` | Internal station identifier |
| `name` | Truckstop name |
| `address` | Street address |
| `price` | Retail diesel price at time of data export ($/gal) |
| `lat` / `lon` | Station coordinates |
| `mile_marker` | Distance along route where this station sits |
| `off_route_miles` | How far off the main route to reach this station |
| `fuel_remaining_on_arrival` | Gallons in tank when arriving at this stop |
| `fuel_filled` | Gallons purchased here |

**Error Responses**

| Status | `error` key | Cause |
|---|---|---|
| `400` | `invalid_params` | Missing or invalid query parameters |
| `400` | `same_destination` | Start and finish resolve to the same location |
| `502` | `upstream_error` | Google Geocoding API or OSRM unreachable or failed |
| `422` | `no_viable_route` | No combination of stations can bridge the route within vehicle range |
| `500` | `internal_error` | Unexpected server error |

---

## Configuration

All tuneable values are read from environment variables. Copy `.env.example` to `.env` and fill in your values.

```bash
cp .env.example .env
```

| Variable | Default | Description |
|---|---|---|
| `GOOGLE_API_KEY` | — | **Required.** Google Maps Geocoding API key |
| `OSRM_BASE_URL` | `http://router.project-osrm.org` | OSRM routing server base URL |
| `SPOTTER_MPG` | `10.0` | Vehicle fuel efficiency |
| `SPOTTER_MAX_RANGE_MILES` | `500.0` | Maximum range on a full tank |
| `SPOTTER_MAX_OFF_ROUTE_MILES` | `5.0` | Maximum detour distance to consider a station |
| `SPOTTER_FUEL_CSV` | `fuel_prices_geocoded.csv` | Filename of the station data inside `spotter/data/` |
| `SECRET_KEY` | — | Django secret key |
| `DEBUG` | `False` | Django debug mode |
| `ALLOWED_HOSTS` | — | Comma-separated allowed hosts |

---

## Setup

```bash
# 1. Create and activate virtual environment
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env
# Edit .env — set GOOGLE_API_KEY and SECRET_KEY at minimum

# 4. Run migrations
python manage.py migrate

# 5. Start development server
python manage.py runserver
```

---

## Caching

Geocoding results are cached to avoid redundant API calls for frequently queried cities. The cache key is derived from the normalized location string (lowercased, special characters replaced with underscores).

```
"Salt Lake City, UT"  ->  geocode:salt_lake_city__ut   TTL: 30 days
```

**Current backend:** Django `LocMemCache` (in-process, per-worker). Fine for development and single-instance deployments.

**Upgrading to Redis for GCP Cloud Memorystore:** swap one block in `settings.py`:

```python
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": env("REDIS_URL"),
    }
}
```

No other code changes are needed — the cache calls in `routing.py` are backend-agnostic.

---

## Running Tests

```bash
python manage.py test spotter
```

Tests cover geo math, the optimizer (including a manual cost verification), and all API error code paths. External services (Google, OSRM) are mocked — no network calls are made during the test run.

---

## Dependency Architecture

Each layer only imports from layers below it — never sideways or upward.

```
api/        ->   services/   ->   utils/   ->   core/
(HTTP)           (orchestrate)    (math/IO)      (config/constants)
```

`utils/` never imports from `services/`. `api/` never imports from `utils/` directly.
