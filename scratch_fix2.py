import os
import glob
import re

def replace_in_file(filepath, replacements):
    with open(filepath, 'r') as f:
        content = f.read()
    
    for old, new in replacements:
        content = content.replace(old, new)
        
    with open(filepath, 'w') as f:
        f.write(content)

replace_in_file("spotter/utils/fuel_optimization_engine.py", [
    ("(G,", "(route_graph,"),
    (" G.nodes", " route_graph.nodes"),
    (" G.edges", " route_graph.edges"),
    ("G = nx", "route_graph = nx"),
])

replace_in_file("spotter/tests/test_views.py", [
    ('"start":', '"start_address":'),
    ('"finish":', '"destination_address":'),
])

