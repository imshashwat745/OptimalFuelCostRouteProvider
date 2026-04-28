"""
Tests for spotter.utils.fuel_optimization_engine.calculate_optimal_fuel_stops.

All tests use synthetic station data — no network calls, no CSV loading.
"""
from django.test import TestCase
from spotter.utils.fuel_optimization_engine import calculate_optimal_fuel_stops
from spotter.exceptions import NoViableRouteError


def make_station(sid, mile_marker, price, off_route_miles=0.0):
    """Helper to create a station dict."""
    return {
        "id": sid,
        "name": f"Station {sid}",
        "address": f"Address {sid}",
        "price": price,
        "lat": 40.0,
        "lon": -90.0,
        "mile_marker": mile_marker,
        "off_route_miles": off_route_miles,
    }


# Vehicle constants for all tests
VEHICLE = dict(
    max_range_miles=500.0,
    mpg=10.0,
    tank_capacity_gallons=50.0,
    buffer_gallons=5.0,
)


class BasicPathfindingTests(TestCase):
    """Verify that Dijkstra picks the cheapest path."""

    def test_picks_cheaper_station(self):
        """Given two reachable stations, optimizer picks the cheaper one."""
        # Route is 600mi — beyond direct range (450mi with buffer),
        # so the truck MUST stop.
        stations = [
            make_station("A", 300, 4.00),
            make_station("B", 300, 3.00),  # Same mile marker, cheaper
        ]
        stops, cost = calculate_optimal_fuel_stops(
            stations, 600,
            fuel_at_departure=50.0,
            greedy_fill=False,
            **VEHICLE,
        )
        # Should pick station B (price 3.00)
        self.assertTrue(
            any(s["id"] == "B" for s in stops),
            "Optimizer should pick the cheaper station B",
        )

    def test_single_station_route(self):
        """Route beyond direct range — must stop at the station."""
        stations = [make_station("A", 250, 3.50)]
        stops, cost = calculate_optimal_fuel_stops(
            stations, 600,
            fuel_at_departure=50.0,
            greedy_fill=False,
            **VEHICLE,
        )
        self.assertEqual(len(stops), 1)
        self.assertEqual(stops[0]["id"], "A")
        self.assertGreater(cost, 0)

    def test_direct_route_skips_stations(self):
        """If route is within direct range (with buffer), stations are skipped."""
        stations = [make_station("A", 200, 3.00)]
        stops, cost = calculate_optimal_fuel_stops(
            stations, 400,
            fuel_at_departure=50.0,
            greedy_fill=False,
            **VEHICLE,
        )
        self.assertEqual(len(stops), 0, "Optimizer should skip station on short route")
        self.assertEqual(cost, 0.0)

    def test_no_stations_short_route(self):
        """Direct route with no stations — should work if within range."""
        stops, cost = calculate_optimal_fuel_stops(
            [], 300,
            fuel_at_departure=50.0,
            greedy_fill=False,
            **VEHICLE,
        )
        self.assertEqual(len(stops), 0)
        self.assertEqual(cost, 0.0)


class DepartureFuelTests(TestCase):
    """Bug fix validation: departure fuel must be enforced."""

    def test_low_departure_fuel_raises(self):
        """
        With 5 gallons (50 mi range) and first station at mile 200,
        the truck cannot reach it. Must raise NoViableRouteError.
        """
        stations = [make_station("A", 200, 3.00)]
        with self.assertRaises(NoViableRouteError):
            calculate_optimal_fuel_stops(
                stations, 400,
                fuel_at_departure=5.0,  # Only 50 miles of range
                greedy_fill=False,
                **VEHICLE,
            )

    def test_exact_departure_fuel_reachable(self):
        """Departure fuel is exactly enough to reach the first station."""
        stations = [make_station("A", 100, 3.00)]
        stops, cost = calculate_optimal_fuel_stops(
            stations, 200,
            fuel_at_departure=10.0,  # Exactly 100 mi range
            greedy_fill=False,
            **VEHICLE,
        )
        self.assertEqual(len(stops), 1)

    def test_full_tank_departure(self):
        """Full tank should reach any station within max range."""
        stations = [make_station("A", 450, 3.00)]
        stops, cost = calculate_optimal_fuel_stops(
            stations, 490,
            fuel_at_departure=50.0,  # Full tank = 500 mi
            greedy_fill=False,
            **VEHICLE,
        )
        self.assertEqual(len(stops), 1)


class BufferFuelTests(TestCase):
    """Bug fix validation: buffer_gallons must be enforced at the End node."""

    def test_direct_route_needs_buffer(self):
        """
        Route is 480 miles. Full tank = 500 mi. But buffer = 5 gal (50 mi).
        Effective range to End = (50 - 5) * 10 = 450 mi.
        480 > 450, so direct route is impossible. Must stop or raise error.
        """
        # With no stations, this should raise since we can't make it with buffer
        with self.assertRaises(NoViableRouteError):
            calculate_optimal_fuel_stops(
                [], 480,
                fuel_at_departure=50.0,
                greedy_fill=False,
                **VEHICLE,
            )

    def test_buffer_forces_stop(self):
        """
        Same 480mi route, but with a station at mile 200.
        Truck should stop there to refuel and arrive with buffer intact.
        """
        stations = [make_station("A", 200, 3.00)]
        stops, cost = calculate_optimal_fuel_stops(
            stations, 480,
            fuel_at_departure=50.0,
            greedy_fill=False,
            **VEHICLE,
        )
        self.assertEqual(len(stops), 1)
        self.assertGreater(cost, 0)

    def test_zero_buffer_allows_longer_direct(self):
        """With buffer=0, 480mi direct route on 500mi tank is fine."""
        stops, cost = calculate_optimal_fuel_stops(
            [], 480,
            fuel_at_departure=50.0,
            max_range_miles=500.0,
            mpg=10.0,
            tank_capacity_gallons=50.0,
            buffer_gallons=0.0,
            greedy_fill=False,
        )
        self.assertEqual(len(stops), 0)
        self.assertEqual(cost, 0.0)


class GreedyFillTests(TestCase):
    """Verify greedy fill buys minimum fuel to reach a cheaper station."""

    def test_greedy_fill_buys_less_at_expensive_station(self):
        """
        Station A at mile 200 costs $4. Station B at mile 350 costs $3.
        With greedy_fill=True, we should buy only enough at A to reach B
        (not fill to full).
        """
        stations = [
            make_station("A", 200, 4.00),
            make_station("B", 350, 3.00),
        ]
        stops_greedy, cost_greedy = calculate_optimal_fuel_stops(
            stations, 490,
            fuel_at_departure=50.0,
            greedy_fill=True,
            **VEHICLE,
        )
        stops_full, cost_full = calculate_optimal_fuel_stops(
            stations, 490,
            fuel_at_departure=50.0,
            greedy_fill=False,
            **VEHICLE,
        )
        # Greedy fill should be cheaper (or equal) since it defers buying to cheaper station
        self.assertLessEqual(cost_greedy, cost_full)

    def test_greedy_fill_fills_full_when_cheapest(self):
        """
        If current station is cheapest on path, greedy fill should fill to full.
        Route 700mi forces stopping at both A and B.
        """
        stations = [
            make_station("A", 200, 2.00),  # Cheapest
            make_station("B", 500, 4.00),  # More expensive
        ]
        stops, cost = calculate_optimal_fuel_stops(
            stations, 700,
            fuel_at_departure=50.0,
            greedy_fill=True,
            **VEHICLE,
        )
        # Station A should fill to full since B is more expensive
        stop_a = next((s for s in stops if s["id"] == "A"), None)
        self.assertIsNotNone(stop_a, "Station A should be in the stops")
        if stop_a:
            # Arriving at A with 50 - 200/10 = 30 gal
            # Greedy: no cheaper station ahead → fill to full = 50 - 30 = 20
            self.assertAlmostEqual(stop_a["fuel_filled"], 20.0, delta=1.0)


class NoViableRouteTests(TestCase):
    """Verify proper error reporting when no route is possible."""

    def test_gap_too_large(self):
        """Stations are too far apart for the vehicle range."""
        stations = [
            make_station("A", 100, 3.00),
            make_station("B", 700, 3.00),  # 600 mi gap > 500 mi range
        ]
        with self.assertRaises(NoViableRouteError):
            calculate_optimal_fuel_stops(
                stations, 800,
                fuel_at_departure=50.0,
                greedy_fill=False,
                **VEHICLE,
            )

    def test_error_message_includes_gap_info(self):
        """Error message should include the largest gap information."""
        stations = [make_station("A", 100, 3.00)]
        try:
            calculate_optimal_fuel_stops(
                stations, 800,
                fuel_at_departure=50.0,
                greedy_fill=False,
                **VEHICLE,
            )
            self.fail("Should have raised NoViableRouteError")
        except NoViableRouteError as e:
            self.assertIn("gap", str(e).lower())


class OffRouteMilesTests(TestCase):
    """Verify off-route miles are correctly factored into distances."""

    def test_off_route_miles_counted(self):
        """Station 2 miles off route should require extra fuel."""
        # Route 600mi — forces a stop so we can compare costs
        station_on = make_station("A", 300, 3.00, off_route_miles=0.0)
        station_off = make_station("B", 300, 3.00, off_route_miles=2.0)

        stops_on, cost_on = calculate_optimal_fuel_stops(
            [station_on], 600,
            fuel_at_departure=50.0,
            greedy_fill=False,
            **VEHICLE,
        )
        stops_off, cost_off = calculate_optimal_fuel_stops(
            [station_off], 600,
            fuel_at_departure=50.0,
            greedy_fill=False,
            **VEHICLE,
        )

        # Off-route station requires more fuel → higher cost
        # (same price but more distance)
        self.assertGreater(cost_off, cost_on)


class CostVerificationTests(TestCase):
    """Manually verify total cost matches expected calculation."""

    def test_manual_cost_check(self):
        """
        Single station at mile 300, price $3.00, route = 600 mi.
        Start with full tank (50 gal). Use 300/10=30 gal to reach station.
        Arrive with 20 gal. Last stop: need (300/10) + 5 buffer = 35 gal.
        Fill = max(35 - 20, 0) = 15 gal (capped at tank capacity).
        Cost = 15 * 3.00 = $45.00.
        """
        stations = [make_station("A", 300, 3.00)]
        stops, cost = calculate_optimal_fuel_stops(
            stations, 600,
            fuel_at_departure=50.0,
            greedy_fill=False,
            **VEHICLE,
        )
        self.assertEqual(len(stops), 1)
        self.assertAlmostEqual(stops[0]["fuel_filled"], 15.0, delta=0.5)
        self.assertAlmostEqual(cost, 45.0, delta=2.0)


class BruteForceOptimalityTests(TestCase):
    """
    Prove Dijkstra gives the global minimum cost by brute-force
    enumerating all valid station subsets for small problem instances.
    """

    def _brute_force_min_cost(self, stations, total_dist, **kwargs):
        """
        Try every possible subset of stations, simulate the fill-to-full
        strategy, return the minimum achievable cost.
        """
        from itertools import combinations

        mpg = kwargs["mpg"]
        tank_cap = kwargs["tank_capacity_gallons"]
        fuel_dep = kwargs["fuel_at_departure"]
        buffer = kwargs["buffer_gallons"]
        max_range = kwargs["max_range_miles"]

        best = float("inf")

        # Try all subsets (including empty — direct route)
        for r in range(len(stations) + 1):
            for combo in combinations(stations, r):
                path = sorted(combo, key=lambda s: s["mile_marker"])

                # Check feasibility: can we reach each stop and End?
                prev_mile = 0.0
                prev_off = 0.0
                fuel = fuel_dep
                cost = 0.0
                feasible = True

                for s in path:
                    dist = (s["mile_marker"] - prev_mile) + prev_off + s["off_route_miles"]
                    fuel_needed = dist / mpg
                    if fuel_needed > fuel:
                        feasible = False
                        break
                    fuel -= fuel_needed
                    # Fill to full at each intermediate stop
                    filled = tank_cap - fuel
                    cost += filled * s["price"]
                    fuel = tank_cap
                    prev_mile = s["mile_marker"]
                    prev_off = s["off_route_miles"]

                if not feasible:
                    continue

                # Check we can reach End with buffer
                dist_to_end = (total_dist - prev_mile) + prev_off
                fuel_needed_end = dist_to_end / mpg + buffer
                if fuel_needed_end > fuel:
                    continue

                # Adjust last stop: only fill what's needed (not to full)
                if path:
                    last = path[-1]
                    # Undo the fill-to-full at last stop
                    last_filled = tank_cap - (fuel - (tank_cap - fuel))
                    # Recalculate: arrive at last stop, fill only enough for End + buffer
                    prev_mile_before_last = 0.0 if len(path) == 1 else path[-2]["mile_marker"]
                    prev_off_before_last = 0.0 if len(path) == 1 else path[-2]["off_route_miles"]
                    if len(path) == 1:
                        dist_to_last = last["mile_marker"] + last["off_route_miles"]
                        fuel_at_last = fuel_dep - dist_to_last / mpg
                    else:
                        dist_to_last = (last["mile_marker"] - prev_mile_before_last) + prev_off_before_last + last["off_route_miles"]
                        fuel_at_last = tank_cap - dist_to_last / mpg

                    dist_last_to_end = (total_dist - last["mile_marker"]) + last["off_route_miles"]
                    needed_at_last = dist_last_to_end / mpg + buffer
                    actual_fill = max(needed_at_last - fuel_at_last, 0.0)
                    actual_fill = min(actual_fill, tank_cap - fuel_at_last)

                    # Recalculate cost: all stops except last fill to full
                    cost = 0.0
                    fuel_sim = fuel_dep
                    prev_m = 0.0
                    prev_o = 0.0
                    for j, s in enumerate(path):
                        dist = (s["mile_marker"] - prev_m) + prev_o + s["off_route_miles"]
                        fuel_sim -= dist / mpg
                        if j < len(path) - 1:
                            filled = tank_cap - fuel_sim
                            cost += filled * s["price"]
                            fuel_sim = tank_cap
                        else:
                            cost += actual_fill * s["price"]
                            fuel_sim += actual_fill
                        prev_m = s["mile_marker"]
                        prev_o = s["off_route_miles"]

                if cost < best:
                    best = cost

        return best

    def test_dijkstra_matches_brute_force_3_stations(self):
        """
        3 stations with different prices and positions.
        Brute force checks all 2^3 = 8 subsets.
        """
        stations = [
            make_station("A", 200, 4.00),
            make_station("B", 350, 2.50),
            make_station("C", 450, 3.50),
        ]
        kwargs = dict(
            max_range_miles=500.0, mpg=10.0,
            tank_capacity_gallons=50.0, buffer_gallons=5.0,
        )
        stops, dijkstra_cost = calculate_optimal_fuel_stops(
            stations, 700,
            fuel_at_departure=50.0,
            greedy_fill=False, **kwargs,
        )
        brute_cost = self._brute_force_min_cost(
            stations, 700, fuel_at_departure=50.0, **kwargs,
        )
        self.assertAlmostEqual(
            dijkstra_cost, brute_cost, delta=0.5,
            msg=f"Dijkstra ${dijkstra_cost} != brute-force ${brute_cost}",
        )

    def test_dijkstra_matches_brute_force_4_stations(self):
        """
        4 stations — brute force checks all 2^4 = 16 subsets.
        """
        stations = [
            make_station("A", 150, 3.80),
            make_station("B", 300, 2.90),
            make_station("C", 450, 3.20),
            make_station("D", 600, 2.50),
        ]
        kwargs = dict(
            max_range_miles=500.0, mpg=10.0,
            tank_capacity_gallons=50.0, buffer_gallons=5.0,
        )
        stops, dijkstra_cost = calculate_optimal_fuel_stops(
            stations, 800,
            fuel_at_departure=50.0,
            greedy_fill=False, **kwargs,
        )
        brute_cost = self._brute_force_min_cost(
            stations, 800, fuel_at_departure=50.0, **kwargs,
        )
        self.assertAlmostEqual(
            dijkstra_cost, brute_cost, delta=0.5,
            msg=f"Dijkstra ${dijkstra_cost} != brute-force ${brute_cost}",
        )

    def test_dijkstra_matches_brute_force_5_stations_varied_prices(self):
        """
        5 stations with deliberately adversarial pricing to stress-test.
        Brute force checks all 2^5 = 32 subsets.
        """
        stations = [
            make_station("A", 100, 5.00),   # Very expensive
            make_station("B", 200, 2.00),   # Very cheap
            make_station("C", 350, 4.50),   # Expensive
            make_station("D", 480, 2.20),   # Cheap
            make_station("E", 600, 3.00),   # Mid
        ]
        kwargs = dict(
            max_range_miles=500.0, mpg=10.0,
            tank_capacity_gallons=50.0, buffer_gallons=5.0,
        )
        stops, dijkstra_cost = calculate_optimal_fuel_stops(
            stations, 850,
            fuel_at_departure=50.0,
            greedy_fill=False, **kwargs,
        )
        brute_cost = self._brute_force_min_cost(
            stations, 850, fuel_at_departure=50.0, **kwargs,
        )
        self.assertAlmostEqual(
            dijkstra_cost, brute_cost, delta=0.5,
            msg=f"Dijkstra ${dijkstra_cost} != brute-force ${brute_cost}",
        )

