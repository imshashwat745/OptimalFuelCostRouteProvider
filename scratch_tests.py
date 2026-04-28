import os
import glob

def replace_in_file(filepath, replacements):
    with open(filepath, 'r') as f:
        content = f.read()
    
    for old, new in replacements:
        content = content.replace(old, new)
        
    with open(filepath, 'w') as f:
        f.write(content)

test_files = glob.glob("spotter/tests/*.py")
for filepath in test_files:
    replace_in_file(filepath, [
        ("spotter.utils.routing", "spotter.utils.spatial_routing_client"),
        ("spotter.utils.fuel_optimizer", "spotter.utils.fuel_optimization_engine"),
        ("spotter.services.route_service", "spotter.services.optimal_route_orchestrator"),
        ("solve_graph", "calculate_optimal_fuel_stops"),
        ("get_optimal_route", "calculate_cheapest_route"),
        ("haversine", "calculate_haversine_distance"),
        ("point_on_segment", "project_point_to_line_segment"),
        ("cumulative_distances_np", "cumulative_distances_np"),
    ])

