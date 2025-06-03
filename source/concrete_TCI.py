import re
import pandas as pd

# 경로 설정
inp_path = "concrete_model_ordered_elements.inp"
dat_path = "concrete_model_ordered_elements.dat"

# ---------------- STEP 1: .inp 파일에서 요소와 절점 추출 ----------------
nodes = {}
elements = []

with open(inp_path, "r") as f:
    lines = f.readlines()

reading_nodes = reading_elements = False
for line in lines:
    line = line.strip()
    if line.startswith("*NODE"):
        reading_nodes = True
        continue
    elif line.startswith("*ELEMENT"):
        reading_nodes = False
        reading_elements = True
        continue
    elif line.startswith("*"):
        reading_nodes = reading_elements = False
        continue

    if reading_nodes:
        parts = line.split(",")
        if len(parts) >= 4:
            try:
                nid = int(parts[0])
                nodes[nid] = tuple(map(float, parts[1:4]))
            except:
                continue
    elif reading_elements:
        parts = line.split(",")
        if len(parts) == 9:
            try:
                eid = int(parts[0])
                elements.append((eid, list(map(int, parts[1:]))))
            except:
                continue

# ---------------- STEP 2: .dat 파일에서 요소별 응력 및 TCI 추출 ----------------
stress_data = []
pattern = re.compile(
    r"^\s*(\d+)\s+(\d+)\s+"
    r"([-+]?\d*\.\d+E[+-]?\d+)\s+([-+]?\d*\.\d+E[+-]?\d+)\s+([-+]?\d*\.\d+E[+-]?\d+)\s+"
    r"([-+]?\d*\.\d+E[+-]?\d+)\s+([-+]?\d*\.\d+E[+-]?\d+)\s+([-+]?\d*\.\d+E[+-]?\d+)"
)

with open(dat_path, "r") as f:
    for line in f:
        m = pattern.match(line)
        if m:
            elem, ip = int(m[1]), int(m[2])
            sxx, syy, szz = float(m[3]), float(m[4]), float(m[5])
            sxy, sxz, syz = float(m[6]), float(m[7]), float(m[8])
            principal = max(abs(sxx), abs(syy), abs(szz))
            f_ct = 18.5
            tci = principal / f_ct
            stress_data.append({
                "element": elem, "integration_point": ip,
                "sxx": sxx, "syy": syy, "szz": szz,
                "sxy": sxy, "sxz": sxz, "syz": syz,
                "principal_stress": principal,
                "TCI": tci
            })

# ---------------- STEP 3: 절점별 응력 평균 및 TCI 집계 ----------------
node_stresses = {}

for record in stress_data:
    elem_id = record["element"]
    stress_vals = {k: record[k] for k in ["sxx", "syy", "szz", "sxy", "sxz", "syz", "principal_stress", "TCI"]}

    matched_nodes = [n for e, nlist in elements if e == elem_id for n in nlist]

    for nid in matched_nodes:
        if nid not in node_stresses:
            node_stresses[nid] = {"count": 0}
            for k in stress_vals:
                node_stresses[nid][k] = 0.0
        node_stresses[nid]["count"] += 1
        for key in stress_vals:
            node_stresses[nid][key] += stress_vals[key]

# ---------------- STEP 4: 평균 계산 및 crack_risk 평가 ----------------
node_summary = []
for nid, data in node_stresses.items():
    count = data.pop("count")
    averaged = {k: v / count for k, v in data.items()}
    crack_risk = averaged["TCI"] > 1.0
    node_summary.append({
        "node": nid,
        **averaged,
        "crack_risk": crack_risk
    })

# ---------------- STEP 5: CSV 저장 ----------------
df_node_summary = pd.DataFrame(node_summary)
csv_path = "tci_node_summary_fixed.csv"
df_node_summary.to_csv(csv_path, index=False)



import plotly.graph_objs as go

# node 좌표와 TCI/risk를 결합
node_coords = {nid: coord for nid, coord in nodes.items()}
# 위험한 노드(TCI > 1)만 필터링
df_risk_nodes = df_node_summary[df_node_summary["crack_risk"] == True].copy()

# 좌표 추출
df_risk_nodes["x"] = df_risk_nodes["node"].map(lambda nid: node_coords.get(nid, (None, None, None))[0])
df_risk_nodes["y"] = df_risk_nodes["node"].map(lambda nid: node_coords.get(nid, (None, None, None))[1])
df_risk_nodes["z"] = df_risk_nodes["node"].map(lambda nid: node_coords.get(nid, (None, None, None))[2])

# Plotly 시각화
scatter_risk = go.Scatter3d(
    x=df_risk_nodes["x"],
    y=df_risk_nodes["y"],
    z=df_risk_nodes["z"],
    mode="markers+text",
    marker=dict(
        size=6,
        color=df_risk_nodes["TCI"],
        colorscale="Jet",
        colorbar=dict(title="TCI"),
        cmin=1.0,
        cmax=df_node_summary["TCI"].max(),
    ),
    text=df_risk_nodes.apply(lambda row: f"Node {row['node']}<br>TCI={row['TCI']:.2f} ⚠️", axis=1),
    hoverinfo="text"
)

layout_risk = go.Layout(
    title="⚠️ 위험 절점만 표시 (TCI > 1)",
    scene=dict(
        xaxis_title="X",
        yaxis_title="Y",
        zaxis_title="Z",
    ),
    margin=dict(l=0, r=0, b=0, t=40)
)

fig_risk = go.Figure(data=[scatter_risk], layout=layout_risk)
fig_risk.write_html("tci_heatmap_risk_only.html")

