# -*- coding: utf-8 -*-
"""
Created on Tue Jun  3 16:54:24 2025

@author: 스마트제어계측
"""

import numpy as np
from shapely.geometry import Polygon, Point
from scipy.interpolate import RBFInterpolator
import matplotlib.pyplot as plt

def compute_epsilon(sensor_coords, sensor_temps, alpha=1.0):
    N = sensor_coords.shape[0]
    d_prime = np.zeros((N, N))
    for i in range(N):
        for j in range(i + 1, N):
            spatial = np.linalg.norm(sensor_coords[i] - sensor_coords[j])
            temp_diff = abs(sensor_temps[i] - sensor_temps[j])
            d = np.sqrt(spatial**2 + alpha * temp_diff**2)
            d_prime[i, j] = d_prime[j, i] = d

    # 자기 자신 제외
    np.fill_diagonal(d_prime, np.inf)
    nn_distances = np.min(d_prime, axis=1)

    mean_nn = np.mean(nn_distances)
    return 1.0 / mean_nn


# 1. Define geometry input
plan_points = [[1, 1], [2, 1], [2, 2], [1, 2]]
thickness = 0.5
element_size = 0.1

# 2. Sensor data: sensor_id, x, y, z, temperature
sensors = [(1, 1.0, 1.0, 0.0, 29.8696), 
           (2, 1.0, 2.0, 0.0, 29.9542), 
           (3, 1.2, 1.2, 0.4, 29.8438), 
           (4, 1.2, 1.4, 0.4, 29.8633), 
           (5, 1.2, 1.6, 0.4, 29.6178)]

sensor_coords_e = np.array([[x, y, z] for _, x, y, z, _ in sensors])
sensor_temps_e  = np.array([temp for _, x, y, z, temp in sensors])
epsilon = compute_epsilon(sensor_coords_e, sensor_temps_e)
print("epsilon : ",epsilon)

# 3. Create 3D mesh inside polygon volume
polygon = Polygon(plan_points)
nodes = {}
node_id = 1
z_levels = np.arange(0, thickness + 1e-3, element_size)
x_range = np.arange(0, 11, element_size)
y_range = np.arange(0, 11, element_size)

for z in z_levels:
    for x in x_range:
        for y in y_range:
            if polygon.contains(Point(x, y)):
                nodes[node_id] = (x, y, z)
                node_id += 1

# 4. Interpolate sensor temperatures to all nodes
sensor_coords = np.array([[x, y, z] for _, x, y, z, _ in sensors])
sensor_temps = np.array([t for *_, t in sensors])
node_ids = list(nodes.keys())
node_coords = np.array([nodes[nid] for nid in node_ids])

interpolator = RBFInterpolator(sensor_coords, sensor_temps, kernel='gaussian', epsilon=epsilon)
interp_temps = interpolator(node_coords)
node_temp_map = dict(zip(node_ids, interp_temps))

# 5. Create ordered C3D8 elements using node coordinates
coord_to_node = {v: k for k, v in nodes.items()}
elements = {}
eid = 1
x_vals = sorted(set(x for x, y, z in coord_to_node))
y_vals = sorted(set(y for x, y, z in coord_to_node))
z_vals = sorted(set(z for x, y, z in coord_to_node))

for x in x_vals[:-1]:
    for y in y_vals[:-1]:
        for z in z_vals[:-1]:
            try:
                n000 = coord_to_node[(x, y, z)]
                n100 = coord_to_node[(x + 1, y, z)]
                n110 = coord_to_node[(x + 1, y + 1, z)]
                n010 = coord_to_node[(x, y + 1, z)]
                n001 = coord_to_node[(x, y, z + 1)]
                n101 = coord_to_node[(x + 1, y, z + 1)]
                n111 = coord_to_node[(x + 1, y + 1, z + 1)]
                n011 = coord_to_node[(x, y + 1, z + 1)]
                elements[eid] = [n000, n100, n110, n010, n001, n101, n111, n011]
                eid += 1
            except KeyError:
                continue

# 6. Write CalculiX .inp file
def generate_calculix_inp(nodes, elements, node_temperatures, output_path):
    with open(output_path, "w") as f:
        f.write("*HEADING\nConcrete Curing Thermal Stress Analysis\n\n")
        f.write("*NODE\n")
        for nid, (x, y, z) in nodes.items():
            f.write(f"{nid}, {x:.2f}, {y:.2f}, {z:.2f}\n")
        max_nid = max(nodes.keys())
        f.write("*NSET, NSET=ALLNODES, GENERATE\n")
        f.write(f"1, {max_nid}, 1\n")
        f.write("*ELEMENT, TYPE=C3D8, ELSET=SolidSet\n")
        for eid, node_list in elements.items():
            f.write(f"{eid}, {', '.join(map(str, node_list))}\n")
        f.write("*MATERIAL, NAME=Conc\n")
        f.write("*ELASTIC\n30000, 0.2\n")
        f.write("*DENSITY\n2400\n")
        f.write("*EXPANSION\n1.0e-5\n")
        f.write("*SOLID SECTION, ELSET=SolidSet, MATERIAL=Conc\n\n")
        f.write("*INITIAL CONDITIONS, TYPE=TEMPERATURE\n")
        f.write("ALLNODES, 20.0\n")
        f.write("*STEP\n*STATIC\n")
        f.write("*BOUNDARY\n")
        for nid, (x, y, z) in nodes.items():
            if z == 0.0:
                f.write(f"{nid}, 1, 3, 0.0\n")
        f.write("*TEMPERATURE\n")
        for nid, temp in node_temperatures.items():
            f.write(f"{nid}, {temp:.2f}\n")
        f.write("*NODE PRINT, NSET=ALLNODES\nU\n")
        f.write("*EL PRINT, ELSET=SolidSet\nS\n")
        f.write("*NODE FILE, NSET=ALLNODES\nU\n")
        f.write("*EL FILE, ELSET=SolidSet\nS\n")
        f.write("*END STEP\n")

# Generate the file
final_path = "concrete_model_ordered_elements.inp"
generate_calculix_inp(nodes, elements, node_temp_map, final_path)