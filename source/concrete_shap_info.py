import plotly.graph_objects as go
import numpy as np

# Step 1: Parse the .inp file again
inp_file_path = "concrete_model_ordered_elements.inp"
nodes = {}
temperatures = {}
elements = []

with open(inp_file_path, 'r') as f:
    lines = f.readlines()

reading_nodes = reading_elements = reading_temperature = False

for line in lines:
    line = line.strip()
    if line.startswith("*NODE"):
        reading_nodes = True
        reading_elements = reading_temperature = False
        continue
    elif line.startswith("*ELEMENT"):
        reading_elements = True
        reading_nodes = reading_temperature = False
        continue
    elif line.startswith("*TEMPERATURE"):
        reading_temperature = True
        reading_nodes = reading_elements = False
        continue
    elif line.startswith("*"):
        reading_nodes = reading_elements = reading_temperature = False
        continue

    if reading_nodes:
        parts = line.split(",")
        if len(parts) < 4:
            continue
        try:
            nid = int(parts[0])
            x, y, z = map(float, parts[1:4])
            nodes[nid] = (x, y, z)
        except:
            continue
    elif reading_elements:
        parts = line.split(",")
        if len(parts) == 9:
            try:
                elements.append([int(p) for p in parts[1:]])
            except:
                continue
    elif reading_temperature:
        parts = line.split(",")
        if len(parts) < 2:
            continue
        try:
            nid = int(parts[0])
            temp = float(parts[1])
            temperatures[nid] = temp
        except:
            continue

# Step 2: Extract node coordinates and temperatures
node_coords = np.array([nodes[nid] for nid in sorted(nodes)])
node_temps = np.array([temperatures.get(nid, 20.0) for nid in sorted(nodes)])
node_ids_sorted = sorted(nodes)

x, y, z = node_coords[:, 0], node_coords[:, 1], node_coords[:, 2]

# Step 3: Plot mesh outlines
mesh_lines = []
for element in elements:
    n = element
    # Define edges for a C3D8 brick element
    edges = [
        [n[0], n[1]], [n[1], n[2]], [n[2], n[3]], [n[3], n[0]],
        [n[4], n[5]], [n[5], n[6]], [n[6], n[7]], [n[7], n[4]],
        [n[0], n[4]], [n[1], n[5]], [n[2], n[6]], [n[3], n[7]]
    ]
    for edge in edges:
        xline = [nodes[edge[0]][0], nodes[edge[1]][0], None]
        yline = [nodes[edge[0]][1], nodes[edge[1]][1], None]
        zline = [nodes[edge[0]][2], nodes[edge[1]][2], None]
        mesh_lines.append((xline, yline, zline))

# Step 4: Sensor data (from earlier input)
sensors = [
    (1, 3, 2, 1.0, 50.5),
    (2, 6, 2, 1.5, 40.6),
    (3, 9, 2, 1.0, 70.0),
    (4, 9, 7, 1.5, 65.0),
    (5, 7, 7, 0.5, 80.0)
]

# Step 5: Build plot
fig = go.Figure()

# Add mesh outline lines
for xline, yline, zline in mesh_lines:
    fig.add_trace(go.Scatter3d(
        x=xline, y=yline, z=zline,
        mode='lines',
        line=dict(color='gray', width=1),
        showlegend=False
    ))

# Add temperature contour points
fig.add_trace(go.Scatter3d(
    x=x, y=y, z=z,
    mode='markers',
    marker=dict(
        size=3,
        color=node_temps,
        colorscale='Jet',
        colorbar=dict(title='Temp (°C)'),
        opacity=0.7
    ),
    name="Temperature"
))

# Add sensor markers
for sid, sx, sy, sz, temp in sensors:
    fig.add_trace(go.Scatter3d(
        x=[sx], y=[sy], z=[sz],
        mode='markers+text',
        marker=dict(size=5, color='black'),
        text=[f"S{sid}"],
        textposition="top center",
        name=f"Sensor {sid}"
    ))

# Layout
fig.update_layout(
    scene=dict(
        xaxis_title='X',
        yaxis_title='Y',
        zaxis_title='Z',
        aspectmode='data'
    ),
    title="Concrete Mesh with Temperature Contours and Sensor Locations",
    margin=dict(l=0, r=0, b=0, t=30)
)

fig.show()
