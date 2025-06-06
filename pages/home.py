# pages/home.py
from dash import html, register_page, dcc, Input, Output, State, callback
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
import pandas as pd
import numpy as np
import os
import ast
from datetime import datetime

import api_concrete
import api_sensor
from dash.exceptions import PreventUpdate

register_page(__name__, path="/")   # 메인 URL

# ──────────────────────────────────────────────────────────────────────────────
# 1. Point‐in‐Polygon (Ray‐Casting) 함수
# ──────────────────────────────────────────────────────────────────────────────
def point_in_poly(x: float, y: float, poly: list[list[float]]) -> bool:
    """
    Ray‐Casting 알고리즘: (x,y)가 다각형 poly 내부인지 여부 반환
    poly: [[x0,y0],[x1,y1],...]
    """
    inside = False
    n = len(poly)
    for i in range(n):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % n]
        if ((y0 <= y < y1) or (y1 <= y < y0)):
            xinters = (y - y0) * (x1 - x0) / (y1 - y0 + 1e-12) + x0
            if xinters > x:
                inside = not inside
    return inside

# ──────────────────────────────────────────────────────────────────────────────
# 2. 레이아웃 정의
# ──────────────────────────────────────────────────────────────────────────────
layout = dbc.Container(
    fluid=True,
    children=[
        dbc.Row(
            [
                # (1) 왼쪽: 콘크리트 목록 (ListGroup)
                dbc.Col(
                    [
                        html.H5("콘크리트 선택", className="mb-2"),
                        dbc.ListGroup(
                            id="list-concrete-main",
                            style={"maxHeight": "75vh", "overflowY": "auto"},
                        ),
                    ],
                    md=3,
                ),

                # (2) 오른쪽: 탭 (3D 히트맵 / 단면도)
                dbc.Col(
                    [
                        dcc.Tabs(
                            id="tabs-main",
                            value="tab-heatmap",
                            children=[
                                dcc.Tab(label="3D 히트맵", value="tab-heatmap"),
                                dcc.Tab(label="단면도", value="tab-crosssection"),
                            ],
                        ),
                        html.Div(id="tab-content-main", className="mt-2"),
                    ],
                    md=9,
                ),
            ],
            className="g-3",
        ),
    ],
)

# ──────────────────────────────────────────────────────────────────────────────
# 3. 콘크리트 목록 초기화 (ListGroup 형태)
# ──────────────────────────────────────────────────────────────────────────────
@callback(
    Output("list-concrete-main", "children"),
    Output("list-concrete-main", "active_item"),
    Input("list-concrete-main", "active_item"),
    prevent_initial_call=False,
)
def init_concrete_list(active_id):
    """
    콘크리트 목록을 ListGroupItem으로 표시하고, 
    첫 로드 시 첫 번째 콘크리트를 기본 active 상태로 설정
    """
    try:
        df_conc = api_concrete.load_all()  # ["concrete_id","name","dims","created"]
    except Exception:
        return [], None

    items = []
    for _, row in df_conc.iterrows():
        cid = row["concrete_id"]
        label = f"{cid} · {row['name']}"
        items.append(
            dbc.ListGroupItem(label, id=cid, action=True)
        )

    if not items:
        return [], None

    if active_id is None:
        active_id = df_conc.iloc[0]["concrete_id"]

    return items, active_id

# ──────────────────────────────────────────────────────────────────────────────
# 4. 센서 데이터 로드 및 시간 묶기
# ──────────────────────────────────────────────────────────────────────────────
def load_and_aggregate_sensor_data(concrete_id: str) -> pd.DataFrame:
    """
    1) api_sensor.load_all_sensors()로 해당 콘크리트의 센서 메타를 가져옴
    2) 각 센서 CSV (sensors/{sensor_id}.csv)를 읽어, time을 .dt.floor("h")로 hour 블록으로 만듦
    3) 필요한 열만 골라서 합쳐서 반환
    결과 columns: ["sensor_id","x","y","hour","temperature","humidity"]
    """
    df_sensor_list = api_sensor.load_all_sensors()
    df_sensor_list = df_sensor_list[df_sensor_list["concrete_id"] == concrete_id].copy()

    all_records = []
    for _, row in df_sensor_list.iterrows():
        sid = row["sensor_id"]
        try:
            dims = ast.literal_eval(row["dims"])
            x_s = float(dims["nodes"][0])
            y_s = float(dims["nodes"][1])
        except Exception:
            x_s, y_s = 0.0, 0.0

        csv_path = os.path.join("sensors", f"{sid}.csv")
        if not os.path.isfile(csv_path):
            continue

        try:
            df_csv = pd.read_csv(csv_path, parse_dates=["time"])
        except Exception:
            continue

        df_csv["hour"] = df_csv["time"].dt.floor("h")
        df_csv["sensor_id"] = sid
        df_csv["x"] = x_s
        df_csv["y"] = y_s

        df_sub = df_csv[["sensor_id", "x", "y", "hour", "temperature", "humidity"]].copy()
        all_records.append(df_sub)

    if not all_records:
        return pd.DataFrame(columns=["sensor_id", "x", "y", "hour", "temperature", "humidity"])

    df_all = pd.concat(all_records, ignore_index=True)
    return df_all

# ──────────────────────────────────────────────────────────────────────────────
# 5. 탭 콘텐츠 렌더링
# ──────────────────────────────────────────────────────────────────────────────
@callback(
    Output("tab-content-main", "children"),
    Input("tabs-main", "value"),
    State("list-concrete-main", "active_item"),
)
def render_tab_content(tab, concrete_id):
    """
    1) 콘크리트 미선택 시 메시지
    2) 센서 데이터 가공
    3) 콘크리트 폴리곤 정보 로드
    4) 탭에 따라 히트맵 or 단면도 컴포넌트 생성
    """
    if concrete_id is None:
        return html.Div("콘크리트를 먼저 선택하세요.", className="text-danger")

    df_data = load_and_aggregate_sensor_data(concrete_id)
    if df_data.empty:
        return html.Div(
            "해당 콘크리트에 등록된 센서가 없거나, 센서 데이터 파일이 없습니다.",
            className="text-warning",
        )

    # 콘크리트 폴리곤 정보 가져오기
    try:
        df_conc = api_concrete.load_all()
        conc_row = df_conc.query("concrete_id == @concrete_id").iloc[0]
        conc_dims = ast.literal_eval(conc_row["dims"])
        conc_nodes = conc_dims["nodes"]      # [[x,y],...]
        conc_h = conc_dims["h"]
    except Exception:
        conc_nodes = []
        conc_h = 0.0

    if tab == "tab-heatmap":
        return make_3d_heatmap_component(df_data, conc_nodes, conc_h)
    else:
        return make_cross_section_component(df_data)

# ──────────────────────────────────────────────────────────────────────────────
# 6. 3D 히트맵 컴포넌트 (Surface + 시간 슬라이더)
# ──────────────────────────────────────────────────────────────────────────────
def make_3d_heatmap_component(df: pd.DataFrame, poly_nodes: list[list[float]], poly_h: float):
    """
    1) df columns: ["sensor_id","x","y","hour","temperature","humidity"]
    2) unique_hours 생성 → 슬라이더 + 시간 표시용 Div + Graph + 숨김 Store
    """
    unique_hours = sorted(df["hour"].unique())
    if not unique_hours:
        return html.Div("유효한 시간 데이터가 없습니다.", className="text-warning")

    # Slider 사용을 위한 mark 생성
    hour_marks = {i: unique_hours[i].strftime("%m-%d %H:%M") for i in range(len(unique_hours))}
    slider = dcc.Slider(
        id="heatmap-hour-slider",
        min=0,
        max=len(unique_hours) - 1,
        step=1,
        value=0,
        marks=hour_marks,
        tooltip={"always_visible": False, "placement": "bottom"},
    )
    time_display = html.Div(id="heatmap-time-display", className="text-center mb-2", style={"fontWeight": "bold"})
    graph = dcc.Graph(id="heatmap-3d-graph", style={"height": "70vh"})
    store = dcc.Store(id="heatmap-hour-list", data=[uh.isoformat() for uh in unique_hours])

    return html.Div(
        [
            time_display,
            slider,
            graph,
            store,
        ]
    )

# ──────────────────────────────────────────────────────────────────────────────
# 7. 3D 히트맵 업데이트 콜백
# ──────────────────────────────────────────────────────────────────────────────
@callback(
    Output("heatmap-time-display", "children"),
    Output("heatmap-3d-graph", "figure"),
    Input("heatmap-hour-slider", "value"),
    State("list-concrete-main", "active_item"),
    State("heatmap-hour-list", "data"),
)
def update_heatmap(selected_idx, concrete_id, hour_list):
    """
    1) 선택된 인덱스로 시간(hour_ts) 구함
    2) 해당 시간 데이터 필터링 → df_sel
    3) 콘크리트 폴리곤(poly_nodes) + 높이(poly_h) 로딩
    4) Bounding Box 내 0.01m 간격 격자(X,Y) 생성 → 내부 mask
    5) Nearest Neighbour로 격자점마다 온도값 부여 → Z_top (온도에 해당)
    6) Surface (top face) + 측면 Mesh3d 생성
    """
    if concrete_id is None:
        raise PreventUpdate

    # 7-1) 시간 리스트 ISO 문자열 → pandas.Timestamp 변환
    unique_hours = [pd.to_datetime(ts) for ts in hour_list]
    if selected_idx < 0 or selected_idx >= len(unique_hours):
        raise PreventUpdate
    hour_ts = unique_hours[selected_idx]

    # 7-2) 해당 시간 블록의 센서 데이터 필터링
    df_data = load_and_aggregate_sensor_data(concrete_id)
    df_sel = df_data[df_data["hour"] == hour_ts].copy()
    if df_sel.empty:
        msg = f"{hour_ts.strftime('%Y-%m-%d %H:%M')} 시각의 데이터가 없습니다."
        empty_fig = go.Figure().update_layout(title=msg, margin=dict(l=40, r=20, t=40, b=40))
        return msg, empty_fig

    # 7-3) 콘크리트 폴리곤 정보 로드
    df_conc = api_concrete.load_all()
    conc_row = df_conc.query("concrete_id == @concrete_id").iloc[0]
    conc_dims = ast.literal_eval(conc_row["dims"])
    poly_nodes = conc_dims["nodes"]  # [[x,y],...]
    poly_h = conc_dims["h"]

    poly_arr = np.array(poly_nodes)
    min_x, max_x = poly_arr[:,0].min(), poly_arr[:,0].max()
    min_y, max_y = poly_arr[:,1].min(), poly_arr[:,1].max()

    # 7-4) 0.01m 간격 그리드 생성
    xi = np.arange(min_x, max_x + 1e-6, 0.01)
    yi = np.arange(min_y, max_y + 1e-6, 0.01)
    X, Y = np.meshgrid(xi, yi)  # shape: (len(yi), len(xi))

    # 7-5) 폴리곤 내부 mask 생성
    mask = np.zeros_like(X, dtype=bool)
    for i in range(X.shape[0]):
        for j in range(X.shape[1]):
            if point_in_poly(X[i,j], Y[i,j], poly_nodes):
                mask[i,j] = True

    # 7-6) Nearest Neighbour 온도 부여 (각 격자점마다 가장 가까운 센서 온도 채우기)
    sensor_coords = df_sel[["x","y"]].to_numpy()
    sensor_temps = df_sel["temperature"].to_numpy()
    flat_X = X.flatten()
    flat_Y = Y.flatten()
    points = np.vstack((flat_X, flat_Y)).T  # (N,2)
    temp_flat = np.full(flat_X.shape, np.nan)

    # 브루트포스 방식: 각 그리드점마다 센서와 거리 계산
    for idx_pt, (px, py) in enumerate(points):
        if mask.flatten()[idx_pt]:
            d2 = (sensor_coords[:,0] - px)**2 + (sensor_coords[:,1] - py)**2
            nearest = np.argmin(d2)
            temp_flat[idx_pt] = sensor_temps[nearest]

    Z_top = temp_flat.reshape(X.shape)  # (len(yi), len(xi))

    # 7-7) Surface (상단 표면) 그리기
    surface = go.Surface(
        x=X, y=Y, z=np.full_like(X, poly_h),      # z = poly_h (항상 상단 높이)
        surfacecolor=Z_top,
        colorscale="Viridis",
        cmin=df_sel["temperature"].min(),
        cmax=df_sel["temperature"].max(),
        colorbar=dict(title="Temperature (°C)"),
        showscale=True,
        hovertemplate="X: %{x:.2f}m<br>Y: %{y:.2f}m<br>Temp: %{surfacecolor:.2f}°C<extra></extra>"
    )

    # 7-8) 측면 Mesh3d (단색 회색) 그리기
    #    - 사각형 단순화: bounding box 상자 모양으로 처리
    x0, x1 = min_x, max_x
    y0, y1 = min_y, max_y
    h = poly_h

    # 꼭짓점 8개
    verts = np.array([
        [x0, y0, 0],  # 0
        [x1, y0, 0],  # 1
        [x1, y1, 0],  # 2
        [x0, y1, 0],  # 3
        [x0, y0, h],  # 4
        [x1, y0, h],  # 5
        [x1, y1, h],  # 6
        [x0, y1, h],  # 7
    ])
    # 측면 faces 인덱스
    I = [0, 0, 0, 1, 3, 4, 4, 4, 5, 7, 7, 7]
    J = [1, 3, 4, 2, 0, 5, 7, 3, 6, 4, 6, 2]
    K = [3, 4, 5, 6, 7, 6, 3, 7, 2, 7, 2, 6]
    mesh_side = go.Mesh3d(
        x=verts[:,0], y=verts[:,1], z=verts[:,2],
        i=I, j=J, k=K,
        color="lightgray", opacity=0.5,
        name="Concrete Side"
    )

    layout_3d = go.Layout(
        title=f"{hour_ts.strftime('%Y-%m-%d %H:%M')} 3D 히트맵",
        scene=dict(
            xaxis=dict(title="X (m)"),
            yaxis=dict(title="Y (m)"),
            zaxis=dict(title="Temperature (°C)"),
            aspectmode="auto",
        ),
        margin=dict(l=0, r=0, b=0, t=40),
    )

    fig = go.Figure(data=[mesh_side, surface], layout=layout_3d)
    time_str = hour_ts.strftime("%Y-%m-%d %H:%M")
    return f"선택된 시간: {time_str}", fig

# ──────────────────────────────────────────────────────────────────────────────
# 8. 단면도 컴포넌트 (Cross‐section)
# ──────────────────────────────────────────────────────────────────────────────
def make_cross_section_component(df: pd.DataFrame):
    unique_hours = sorted(df["hour"].unique())
    if not unique_hours:
        return html.Div("유효한 시간 데이터가 없습니다.", className="text-warning")

    hour_marks = {i: unique_hours[i].strftime("%m-%d %H:%M") for i in range(len(unique_hours))}
    slider = dcc.Slider(
        id="slider-hour",
        min=0,
        max=len(unique_hours) - 1,
        step=1,
        value=0,
        marks=hour_marks,
        tooltip={"always_visible": False, "placement": "bottom"},
    )
    time_display = html.Div(id="cross-time-display", className="text-center mb-2", style={"fontWeight": "bold"})
    graph_x = dcc.Graph(id="cross-x-plot", style={"height": "40vh"})
    graph_y = dcc.Graph(id="cross-y-plot", style={"height": "40vh"})
    store = dcc.Store(id="selected-hour-ts", data=[uh.isoformat() for uh in unique_hours])

    return html.Div(
        [
            time_display,
            slider,
            graph_x,
            graph_y,
            store,
        ]
    )

# ──────────────────────────────────────────────────────────────────────────────
# 9. 단면도 업데이트 콜백
# ──────────────────────────────────────────────────────────────────────────────
@callback(
    Output("cross-time-display", "children"),
    Output("cross-x-plot", "figure"),
    Output("cross-y-plot", "figure"),
    Input("slider-hour", "value"),
    State("list-concrete-main", "active_item"),
    State("selected-hour-ts", "data"),
)
def update_cross_section(selected_idx, concrete_id, hour_ts_list):
    if concrete_id is None:
        raise PreventUpdate

    unique_hours = [pd.to_datetime(ts) for ts in hour_ts_list]
    if selected_idx < 0 or selected_idx >= len(unique_hours):
        raise PreventUpdate
    hour_ts = unique_hours[selected_idx]
    time_str = hour_ts.strftime("%Y-%m-%d %H:%M")

    df_data = load_and_aggregate_sensor_data(concrete_id)
    df_sel = df_data[df_data["hour"] == hour_ts].copy()
    if df_sel.empty:
        empty_fig = go.Figure().update_layout(
            title="해당 시간의 데이터가 없습니다.", margin=dict(l=40, r=20, t=40, b=40)
        )
        return f"선택된 시간: {time_str}", empty_fig, empty_fig

    # X축 단면: Y vs 온도
    fig_x = go.Figure()
    fig_x.add_trace(
        go.Scatter(
            x=df_sel["y"],
            y=df_sel["temperature"],
            mode="markers+lines",
            marker=dict(color="red", size=8),
            text=df_sel["sensor_id"],
            hovertemplate="Sensor: %{text}<br>Y: %{x:.2f}<br>Temp: %{y:.2f}°C<extra></extra>",
            name="온도 (Y 단면)",
        )
    )
    fig_x.update_layout(
        title=f"{time_str} – X축 단면 (Y vs Temperature)",
        xaxis_title="Y 위치 (m)",
        yaxis_title="온도 (°C)",
        margin=dict(l=40, r=20, t=40, b=40),
    )

    # Y축 단면: X vs 습도
    fig_y = go.Figure()
    fig_y.add_trace(
        go.Scatter(
            x=df_sel["x"],
            y=df_sel["humidity"],
            mode="markers+lines",
            marker=dict(color="blue", size=8),
            text=df_sel["sensor_id"],
            hovertemplate="Sensor: %{text}<br>X: %{x:.2f}<br>Humidity: %{y:.1f}%<extra></extra>",
            name="습도 (X 단면)",
        )
    )
    fig_y.update_layout(
        title=f"{time_str} – Y축 단면 (X vs Humidity)",
        xaxis_title="X 위치 (m)",
        yaxis_title="습도 (%)",
        margin=dict(l=40, r=20, t=40, b=40),
    )

    return f"선택된 시간: {time_str}", fig_x, fig_y
