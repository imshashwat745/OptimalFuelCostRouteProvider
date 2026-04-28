import networkx as nx
from ..exceptions import NoViableRouteError


def calculate_optimal_fuel_stops(
    candidate_stations: list[dict],
    total_route_distance_miles: float,
    *,
    max_range_miles: float,
    mpg: float,
    tank_capacity_gallons: float,
    fuel_at_departure: float,
    buffer_gallons: float,
    greedy_fill: bool,
) -> tuple[list[dict], float]:
    """
    Dijkstra finds the cheapest path, then a greedy pass decides
    exactly how many gallons to buy at each stop.
    """
    route_graph = nx.DiGraph()
    route_graph.add_node("Start", mile_marker=0.0, price=0.0, off_route_miles=0.0, data=None)
    for s in candidate_stations:
        route_graph.add_node(s["id"], mile_marker=s["mile_marker"], price=s["price"],
                   off_route_miles=s["off_route_miles"], data=s)
    route_graph.add_node("End", mile_marker=total_route_distance_miles, price=0.0, off_route_miles=0.0, data=None)

    nodes = list(route_graph.nodes(data=True))
    for i, (source_node_id, source_station_data) in enumerate(nodes):
        is_start = source_node_id == "Start"
        for dest_node_id, dest_station_data in nodes[i + 1:]:
            is_end = dest_node_id == "End"
            route_dist = dest_station_data["mile_marker"] - source_station_data["mile_marker"]
            if route_dist > max_range_miles:
                break
            total_driving_distance = source_station_data["off_route_miles"] + route_dist + dest_station_data["off_route_miles"]

            # Enforce physical fuel constraints on each edge
            capacity = fuel_at_departure if is_start else tank_capacity_gallons
            if is_end:
                capacity -= buffer_gallons
            max_reachable_distance = capacity * mpg

            if 0 < total_driving_distance <= max_reachable_distance:
                # Edge weight = cost of fuel for this leg.
                # Fill-to-full: arriving at v, you buy dist/mpg gallons at v's price.
                # Exception: End node (no purchase) — fuel was bought at u.
                if is_end:
                    edge_price = source_station_data["price"]
                else:
                    edge_price = dest_station_data["price"]
                route_graph.add_edge(
                    source_node_id, dest_node_id,
                    weight=total_driving_distance / mpg * edge_price,
                    total_driving_distance=total_driving_distance,
                )

    try:
        path = nx.shortest_path(route_graph, source="Start", target="End", weight="weight")
    except nx.NetworkXNoPath:
        markers = [0.0] + [s["mile_marker"] for s in candidate_stations] + [total_route_distance_miles]
        gaps = [(markers[k + 1] - markers[k], markers[k], markers[k + 1])
                for k in range(len(markers) - 1)]
        worst_gap, gap_start, gap_end = max(gaps, key=lambda x: x[0])
        raise NoViableRouteError(
            f"No viable route. Largest gap: {worst_gap:.1f} miles "
            f"(mile {gap_start:.1f} → {gap_end:.1f}). "
            f"Stations: {len(candidate_stations)}. Range: {max_range_miles:.0f} mi."
        )

    stop_nodes = [nid for nid in path if nid not in ("Start", "End")]

    # Build ordered ordered_route_stops with per-leg distances
    ordered_route_stops = []
    predest_node_id = "Start"
    for nid in stop_nodes:
        node_attr = route_graph.nodes[nid]
        ordered_route_stops.append({
            "data":      node_attr["data"],
            "price":     node_attr["price"],
            "dist_here": route_graph.edges[predest_node_id, nid]["total_driving_distance"],
            "off_route": node_attr["off_route_miles"],
        })
        predest_node_id = nid

    last_to_end = (
        route_graph.edges[stop_nodes[-1], "End"]["total_driving_distance"] if stop_nodes
        else route_graph.edges["Start", "End"]["total_driving_distance"]
    )

    # ── Greedy fill pass ──────────────────────────────────────────────────────
    current_fuel = fuel_at_departure
    fuel_stops: list[dict] = []
    total_cost = 0.0

    for i, stop in enumerate(ordered_route_stops):
        current_fuel -= stop["dist_here"] / mpg
        current_fuel = max(current_fuel, 0.0)

        is_last = i == len(ordered_route_stops) - 1

        if is_last:
            needed = last_to_end / mpg + buffer_gallons
            fuel_filled = min(max(needed - current_fuel, 0.0),
                              tank_capacity_gallons - current_fuel)

        elif not greedy_fill:
            fuel_filled = tank_capacity_gallons - current_fuel

        else:
            # Buy just enough to reach the next cheaper station on the path
            dist_acc = 0.0
            next_cheaper_idx = None
            for k in range(i + 1, len(ordered_route_stops)):
                dist_acc += ordered_route_stops[k]["dist_here"]
                if dist_acc > max_range_miles:
                    break
                if ordered_route_stops[k]["price"] < stop["price"]:
                    next_cheaper_idx = k
                    break

            if next_cheaper_idx is not None:
                fuel_to_cheaper = (
                    sum(ordered_route_stops[k]["dist_here"] for k in range(i + 1, next_cheaper_idx + 1))
                    / mpg + buffer_gallons
                )
                fuel_filled = max(fuel_to_cheaper - current_fuel, 0.0)
            else:
                fuel_filled = tank_capacity_gallons - current_fuel

            fuel_filled = min(max(fuel_filled, 0.0), tank_capacity_gallons - current_fuel)

        current_fuel += fuel_filled
        total_cost += fuel_filled * stop["price"]

        if fuel_filled > 1e-6:
            sd = stop["data"].copy()
            sd["fuel_remaining_on_arrival"] = round(current_fuel - fuel_filled, 4)
            sd["fuel_filled"] = round(fuel_filled, 4)
            sd["off_route_miles"] = round(stop["off_route"], 4)
            fuel_stops.append(sd)

    return fuel_stops, round(total_cost, 2)
