import os
import glob

def replace_in_file(filepath, replacements):
    with open(filepath, 'r') as f:
        content = f.read()
    
    for old, new in replacements:
        content = content.replace(old, new)
        
    with open(filepath, 'w') as f:
        f.write(content)

replace_in_file("spotter/services/optimal_route_orchestrator.py", [
    ("haversine", "calculate_haversine_distance"),
])

replace_in_file("spotter/tests/test_geo.py", [
    ("haversine", "calculate_haversine_distance"),
    ("point_on_segment", "project_point_to_line_segment"),
])

