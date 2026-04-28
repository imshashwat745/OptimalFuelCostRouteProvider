"""
Performance benchmark for the optimal route endpoint.
Runs calculate_cheapest_route twice — first cold, then warm (cached).
"""
import os
import time
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

django.setup()

from spotter.services.optimal_route_orchestrator import calculate_cheapest_route

def bench(label, **kwargs):
    start_address = time.perf_counter()
    try:
        res = calculate_cheapest_route(**kwargs)
        elapsed = time.perf_counter() - start_address
        print(f"[{label}]  {elapsed:.3f}s  | "
              f"dist={res['total_distance_miles']:.1f}mi  "
              f"cost=${res['total_fuel_cost']:.2f}  "
              f"stops={len(res['fuel_stops'])}")
    except Exception as e:
        elapsed = time.perf_counter() - start_address
        print(f"[{label}]  {elapsed:.3f}s  | ERROR: {e}")


print("=== Spotter Performance Benchmark ===\n")

# Cold run (first request — CSV load, geocode, OSRM all fresh)
bench("Cold  run",
      start_address="Chicago, IL", destination_address="Denver, CO",
      buffer_gallons=5.0, greedy_fill=False)

# Warm run (second request — stations cached in lru_cache, OSRM & geocode in Django cache)
bench("Warm  run",
      start_address="Chicago, IL", destination_address="Denver, CO",
      buffer_gallons=5.0, greedy_fill=False)

# Warm run with greedy fill
bench("Greedy   ",
      start_address="Chicago, IL", destination_address="Denver, CO",
      buffer_gallons=5.0, greedy_fill=True)

print("\nDone.")
