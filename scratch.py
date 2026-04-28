import os

def replace_in_file(filepath, replacements):
    with open(filepath, 'r') as f:
        content = f.read()
    
    for old, new in replacements:
        content = content.replace(old, new)
        
    with open(filepath, 'w') as f:
        f.write(content)

# 1. Update optimal_route_orchestrator.py
replace_in_file("spotter/services/optimal_route_orchestrator.py", [
    ("spotter.utils.routing", "spotter.utils.spatial_routing_client"),
    ("..utils.routing", "..utils.spatial_routing_client"),
    ("geocode_location", "fetch_coordinates_for_address"),
    ("get_routes", "fetch_osrm_route_alternatives"),
    ("load_stations", "load_stations_in_memory"),
    ("map_stations_to_route", "find_stations_along_route_corridor"),
    ("spotter.utils.fuel_optimizer", "spotter.utils.fuel_optimization_engine"),
    ("..utils.fuel_optimizer", "..utils.fuel_optimization_engine"),
    ("solve_graph", "calculate_optimal_fuel_stops"),
    ("get_optimal_route", "calculate_cheapest_route"),
    ("_evaluate_route", "_evaluate_route_alternative"),
    ("start_loc", "start_address"),
    ("finish_loc", "destination_address"),
    ("f_start", "future_start_coords"),
    ("f_finish", "future_dest_coords"),
    ("f_stations", "future_stations"),
])

# 2. Update fuel_optimization_engine.py
replace_in_file("spotter/utils/fuel_optimization_engine.py", [
    ("solve_graph", "calculate_optimal_fuel_stops"),
    ("valid_stations", "candidate_stations"),
    ("total_route_dist", "total_route_distance_miles"),
    (" G ", " route_graph "),
    ("G.add_node", "route_graph.add_node"),
    ("G.nodes", "route_graph.nodes"),
    ("G.add_edge", "route_graph.add_edge"),
    ("G.edges", "route_graph.edges"),
    ("u_id", "source_node_id"),
    ("v_id", "dest_node_id"),
    ("u_attr", "source_station_data"),
    ("v_attr", "dest_station_data"),
    ("actual_dist", "total_driving_distance"),
    ("max_dist", "max_reachable_distance"),
    ("path_stops", "ordered_route_stops"),
])

# 3. Update spatial_routing_client.py
replace_in_file("spotter/utils/spatial_routing_client.py", [
    ("geocode_location", "fetch_coordinates_for_address"),
    ("get_routes", "fetch_osrm_route_alternatives"),
    ("_load_stations_cached", "_load_and_index_stations_in_memory"),
    ("load_stations", "load_stations_in_memory"),
    ("map_stations_to_route", "find_stations_along_route_corridor"),
    ("tree =", "national_station_spatial_index ="),
    ("station_tree =", "national_station_spatial_index ="),
    ("station_tree.query", "national_station_spatial_index.query"),
    ("route_buffer", "route_corridor_polygon"),
    ("candidate_stations", "stations_near_corridor"),
    ("seg_tree", "route_segments_spatial_index"),
    ("haversine", "calculate_haversine_distance"),
    ("point_on_segment", "project_point_to_line_segment"),
])

# 4. Update geo.py
replace_in_file("spotter/utils/geo.py", [
    ("haversine", "calculate_haversine_distance"),
    ("point_on_segment", "project_point_to_line_segment"),
])

# 5. Update views.py
replace_in_file("spotter/api/views.py", [
    ("..services.route_service", "..services.optimal_route_orchestrator"),
    ("get_optimal_route", "calculate_cheapest_route"),
    ("start", "start_address"),
    ("finish", "destination_address"),
    ("exc", "routing_exception"),
])

# 6. Update serializers.py
replace_in_file("spotter/api/serializers.py", [
    ("start", "start_address"),
    ("finish", "destination_address"),
])

# 7. Update test_perf.py
replace_in_file("test_perf.py", [
    ("spotter.services.route_service", "spotter.services.optimal_route_orchestrator"),
    ("get_optimal_route", "calculate_cheapest_route"),
    ("start_loc", "start_address"),
    ("finish_loc", "destination_address"),
    ("start", "start_address"),
    ("finish", "destination_address"),
])

