import networkx as nx
from ..exceptions import NoViableRouteError


def solve_graph(
    valid_stations: list[dict],
    total_route_dist: float,
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
    G = nx.DiGraph()
    G.add_node("Start", mile_marker=0.0, price=0.0, off_route_miles=0.0, data=None)
    for s in valid_stations:
        G.add_node(s["id"], mile_marker=s["mile_marker"], price=s["price"],
                   off_route_miles=s["off_route_miles"], data=s)
    G.add_node("End", mile_marker=total_route_dist, price=0.0, off_route_miles=0.0, data=None)

    nodes = list(G.nodes(data=True))
    for i, (u_id, u_attr) in enumerate(nodes):
        for v_id, v_attr in nodes[i + 1:]:
            route_dist = v_attr["mile_marker"] - u_attr["mile_marker"]
            if route_dist > max_range_miles:
                break
            actual_dist = u_attr["off_route_miles"] + route_dist + v_attr["off_route_miles"]
            if 0 < actual_dist <= max_range_miles:
                G.add_edge(
                    u_id, v_id,
                    weight=actual_dist / mpg * u_attr["price"],
                    actual_dist=actual_dist,
                )

    try:
        path = nx.shortest_path(G, source="Start", target="End", weight="weight")
    except nx.NetworkXNoPath:
        markers = [0.0] + [s["mile_marker"] for s in valid_stations] + [total_route_dist]
        gaps = [(markers[k + 1] - markers[k], markers[k], markers[k + 1])
                for k in range(len(markers) - 1)]
        worst_gap, gap_start, gap_end = max(gaps, key=lambda x: x[0])
        raise NoViableRouteError(
            f"No viable route. Largest gap: {worst_gap:.1f} miles "
            f"(mile {gap_start:.1f} → {gap_end:.1f}). "
            f"Stations: {len(valid_stations)}. Range: {max_range_miles:.0f} mi."
        )

    stop_nodes = [nid for nid in path if nid not in ("Start", "End")]

    # Build ordered path_stops with per-leg distances
    path_stops = []
    prev_id = "Start"
    for nid in stop_nodes:
        node_attr = G.nodes[nid]
        path_stops.append({
            "data":      node_attr["data"],
            "price":     node_attr["price"],
            "dist_here": G.edges[prev_id, nid]["actual_dist"],
            "off_route": node_attr["off_route_miles"],
        })
        prev_id = nid

    last_to_end = (
        G.edges[stop_nodes[-1], "End"]["actual_dist"] if stop_nodes
        else G.edges["Start", "End"]["actual_dist"]
    )

    # ── Greedy fill pass ──────────────────────────────────────────────────────
    current_fuel = fuel_at_departure
    fuel_stops: list[dict] = []
    total_cost = 0.0

    for i, stop in enumerate(path_stops):
        current_fuel -= stop["dist_here"] / mpg
        current_fuel = max(current_fuel, 0.0)

        is_last = i == len(path_stops) - 1

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
            for k in range(i + 1, len(path_stops)):
                dist_acc += path_stops[k]["dist_here"]
                if dist_acc > max_range_miles:
                    break
                if path_stops[k]["price"] < stop["price"]:
                    next_cheaper_idx = k
                    break

            if next_cheaper_idx is not None:
                fuel_to_cheaper = (
                    sum(path_stops[k]["dist_here"] for k in range(i + 1, next_cheaper_idx + 1))
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
