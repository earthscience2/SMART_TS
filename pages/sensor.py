#!/usr/bin/env python3
# pages/sensor.py
"""Dash 페이지: 콘크리트 요소에 부착된 센서를 관리

* 왼쪽에서 콘크리트를 선택 → 해당 콘크리트의 센서 리스트 표시
* 센서 추가/수정/삭제 기능
* 우측 3D 뷰: 콘크리트 구조 + 센서 위치(파란 점) 표시 → 선택된 센서는 빨간 점으로 강조
* [변경] 센서 위치 입력: 세 개 필드 → 한 필드("[x,y,z]")로 통합
* [변경] msg Alert 제거 → add/edit 전용 Alert(`add-sensor-alert`, `edit-sensor-alert`) 사용
* [변경] 카메라 시점을 실시간으로 저장하되, 콘크리트 변경 시 및 센서 선택 시에는 강제로 고정되지 않도록 수정
* [변경] 콘크리트를 바꿀 때마다 해당 모델을 제대로 그리도록 수정
* [변경] 카메라 저장 시 Toast 알림 표시 (디버깅용)
* [추가] 모든 센서마다 수직 보조선(Vertical Line)을 그려서 높이(z) 비교 용이하도록 함
* [추가] 각 센서 위치에서 X축/Y축 투영 보조선을 그리되, 보조선 범위를 폴리곤 내부로 한정
* [추가] 보조선을 켜고 끌 수 있는 토글 스위치를 추가
* [수정] 센서 수정 모달에서 나머지 센서도 함께 표시하고, 빨간 점 크기를 조정
* [수정] 센서 수정 시 이름(ID)도 수정할 수 있도록 변경
* [수정] 센서 수정 후 테이블이 즉시 갱신되도록 개선
* [수정] 수정 모달 및 미리보기에도 보조선 표시/숨김 기능 추가
* [추가] 센서 추가/수정 시 기존 ID 중복 검사 및 중복 시 Alert 띄움
"""

from __future__ import annotations

import ast
import numpy as np
import pandas as pd
import dash  # dash.no_update 사용을 위해 import
import plotly.graph_objects as go
from dash import (
    html, dcc, Input, Output, State,
    dash_table, register_page, callback
)
import dash_bootstrap_components as dbc
from dash.exceptions import PreventUpdate

import api_db

register_page(__name__, path="/sensor")

# ────────────────────────────── 3-D 헬퍼 ─────────────────────────────
def make_concrete_fig(nodes: list[list[float]], h: float) -> go.Figure:
    fig = go.Figure()
    poly = np.array(nodes)
    x0, y0 = poly[:, 0], poly[:, 1]
    z0 = np.zeros(len(nodes))
    x1, y1 = x0, y0
    z1 = np.full(len(nodes), h)

    # Mesh3d (바닥+상단+측면)
    verts_x = np.concatenate([x0, x1])
    verts_y = np.concatenate([y0, y1])
    verts_z = np.concatenate([z0, z1])
    n = len(nodes)
    faces = []
    # 바닥면 삼각형
    for i in range(1, n - 1):
        faces.append((0, i, i + 1))
    # 상단면 삼각형 (정점 순서를 역순으로)
    for i in range(1, n - 1):
        faces.append((n, n + i + 1, n + i))
    # 측면 삼각형
    for i in range(n):
        nxt = (i + 1) % n
        faces.append((i, nxt, n + nxt))
        faces.append((i, n + nxt, n + i))

    i0, i1, i2 = zip(*faces)
    fig.add_trace(go.Mesh3d(
        x=verts_x, y=verts_y, z=verts_z,
        i=i0, j=i1, k=i2,
        color="lightgray", opacity=0.35
    ))

    # 모서리(Edges) 그리기
    edges = []
    for i in range(n):
        edges.append((x0[i], y0[i], 0))
        edges.append((x0[(i + 1) % n], y0[(i + 1) % n], 0))
    for i in range(n):
        edges.append((x1[i], y1[i], h))
        edges.append((x1[(i + 1) % n], y1[(i + 1) % n], h))
    for i in range(n):
        edges.append((x0[i], y0[i], 0))
        edges.append((x1[i], y1[i], h))

    fig.add_trace(go.Scatter3d(
        x=[p[0] for p in edges],
        y=[p[1] for p in edges],
        z=[p[2] for p in edges],
        mode="lines",
        line=dict(width=4, color="dimgray"),
        hoverinfo="skip"
    ))

    fig.update_layout(
        margin=dict(l=0, r=0, b=0, t=0),
        scene_aspectmode="data"
    )
    return fig

def get_polygon_intersections_x(y: float, nodes: list[list[float]]) -> list[float]:
    intersections = []
    n = len(nodes)
    for i in range(n):
        x1, y1 = nodes[i]
        x2, y2 = nodes[(i + 1) % n]
        # y 선이 엣지의 y 범위 안에 있는지 확인
        if (y1 <= y < y2) or (y2 <= y < y1):
            if y2 != y1:
                t = (y - y1) / (y2 - y1)
                xi = x1 + t * (x2 - x1)
                intersections.append(xi)
    return intersections

def get_polygon_intersections_y(x: float, nodes: list[list[float]]) -> list[float]:
    intersections = []
    n = len(nodes)
    for i in range(n):
        x1, y1 = nodes[i]
        x2, y2 = nodes[(i + 1) % n]
        # x 선이 엣지의 x 범위 안에 있는지 확인
        if (x1 <= x < x2) or (x2 <= x < x1):
            if x2 != x1:
                t = (x - x1) / (x2 - x1)
                yi = y1 + t * (y2 - y1)
                intersections.append(yi)
    return intersections


# ────────────────────────────── 레이아웃 ────────────────────────────
layout = dbc.Container(
    fluid=True,
    children=[
        # ── (★) 카메라 정보를 저장하기 위한 Store
        dcc.Store(id="camera-store", data=None),

        # ── (★) 보조선 토글 상태를 저장하기 위한 Store(메인 뷰)
        dcc.Store(id="helper-toggle-store", data=True),

        # ── (★) 카메라 저장 시 알림을 띄우기 위한 Toast (디버깅용)
        dbc.Toast(
            id="camera-toast",
            header="카메라 저장됨",
            is_open=False,
            duration=2000,
            icon="info",
            style={"position": "fixed", "top": 10, "right": 10, "width": "300px"},
            children="",
        ),

        # ── (★) 메인 뷰 보조선 토글 스위치 ───────────────────────────
        dbc.Row(
            dbc.Col(
                dbc.Switch(
                    id="toggle-lines",
                    label="보조선 표시",
                    value=True,
                    style={"marginBottom": "10px"},
                ),
                width=3,
            )
        ),

        # 상단: 콘크리트 선택 → 센서 테이블 + 버튼
        dbc.Row(
            [
                dbc.Col(
                    [
                        html.H6("콘크리트 선택"),
                        dcc.Dropdown(
                            id="ddl-concrete",
                            placeholder="콘크리트 선택",
                            clearable=False,
                        ),
                        html.H6("센서 리스트", className="mt-3"),
                        dash_table.DataTable(
                            id="tbl-sensor",
                            page_size=10,
                            row_selectable="single",
                            style_table={"overflowY": "auto", "height": "45vh"},
                            style_cell={"whiteSpace": "nowrap", "textAlign": "center"},
                            style_header={"backgroundColor": "#f1f3f5", "fontWeight": 600},
                        ),
                        dbc.ButtonGroup(
                            [
                                dbc.Button("+ 추가", id="btn-sensor-add", color="success", className="mt-2"),
                                dbc.Button("수정", id="btn-sensor-edit", color="secondary", className="mt-2", disabled=True),
                                dbc.Button("삭제", id="btn-sensor-del",  color="danger", className="mt-2", disabled=True),
                            ],
                            size="sm",
                            vertical=True,
                            className="w-100",
                        ),
                        dcc.ConfirmDialog(
                            id="confirm-del-sensor",
                            message="선택한 센서를 정말 삭제하시겠습니까?"
                        ),
                    ],
                    md=3,
                ),
                dbc.Col(
                    [
                        html.H6(id="sensor-title", className="mb-2"),
                        dcc.Graph(
                            id="viewer-sensor",
                            style={"height": "75vh"},
                            config={"scrollZoom": True},
                        ),
                    ],
                    md=9,
                ),
            ],
            className="g-3",
        ),

        # ── 추가 모달 ──────────────────────────────────────────
        dbc.Modal(
            id="modal-sensor-add",
            is_open=False,
            size="lg",
            children=[
                dbc.ModalHeader("센서 추가"),
                dbc.ModalBody(
                    [
                        dbc.Alert(id="add-sensor-alert", is_open=False, duration=3000, color="danger"),
                        dbc.Row([
                            dbc.Col([
                                html.Label("Device ID", className="form-label"),
                                dbc.Input(id="add-sensor-device-id", placeholder="Device ID (예: DEVICE001)", className="mb-2"),
                            ], width=6),
                            dbc.Col([
                                html.Label("Channel", className="form-label"),
                                dbc.Input(id="add-sensor-channel", type="number", placeholder="채널 번호", className="mb-2"),
                            ], width=6)
                        ], className="mb-3"),
                        dbc.Input(id="add-sensor-coords", placeholder="센서 좌표 [x, y, z] (예: [1, 1, 0])", className="mb-2"),
                        dcc.Graph(id="add-sensor-preview", style={"height": "45vh"}, className="border"),
                    ]
                ),
                dbc.ModalFooter(
                    [
                        dbc.Button("새로고침", id="add-sensor-build", color="info", className="me-auto"),
                        dbc.Button("저장", id="add-sensor-save", color="primary"),
                        dbc.Button("닫기", id="add-sensor-close", color="secondary"),
                    ]
                ),
            ],
        ),

        # ── 수정 모달 ──────────────────────────────────────────
        dbc.Modal(
            id="modal-sensor-edit",
            is_open=False,
            size="lg",
            children=[
                dbc.ModalHeader(f"센서 수정"),
                dbc.ModalBody(
                    [
                        dcc.Store(id="edit-sensor-concrete-id"),
                        dcc.Store(id="edit-sensor-id-store"),
                        dbc.Alert(id="edit-sensor-alert", is_open=False, duration=3000, color="danger"),
                        # 센서 정보 표시
                        dbc.Row([
                            dbc.Col([
                                html.Label("Device ID", className="form-label"),
                                html.Div(id="edit-sensor-device-id", className="form-control bg-light")
                            ], width=6),
                            dbc.Col([
                                html.Label("Channel", className="form-label"),
                                html.Div(id="edit-sensor-channel", className="form-control bg-light")
                            ], width=6)
                        ], className="mb-3"),
                        # 좌표 입력 필드
                        dbc.Input(id="edit-sensor-coords", placeholder="센서 좌표 [x, y, z] (예: [1, 1, 0])", className="mb-2"),
                        # (★) 수정 모달 보조선 토글 스위치
                        dbc.Row(
                            dbc.Col(
                                dbc.Switch(
                                    id="edit-toggle-lines",
                                    label="모달 내 보조선 표시",
                                    value=True,
                                    style={"marginBottom": "10px"},
                                ),
                                width=4,
                            ),
                            className="mb-2",
                        ),
                        # 센서 수정 3D 뷰(미리보기 영역)
                        dcc.Graph(id="edit-sensor-preview", style={"height": "45vh"}, className="border"),
                    ]
                ),
                dbc.ModalFooter(
                    [
                        dbc.Button("새로고침", id="edit-sensor-build", color="info", className="me-auto"),
                        dbc.Button("저장", id="edit-sensor-save", color="primary"),
                        dbc.Button("닫기", id="edit-sensor-close", color="secondary"),
                    ]
                ),
            ],
        ),
    ],
)


# ───────────────────── ① 콘크리트 목록 초기화 ─────────────────────
@callback(
    Output("ddl-concrete", "options"),
    Output("ddl-concrete", "value"),
    Input("ddl-concrete", "value"),
    prevent_initial_call=False,
)
def init_dropdown(selected_value):
    """
    페이지 로드 또는 값이 None일 때 콘크리트 목록을 Dropdown 옵션으로 설정.
    """
    df_conc = api_db.get_concrete_data()
    options = [
        {"label": f"{row['name']}", "value": row["concrete_pk"]}
        for _, row in df_conc.iterrows()
    ]
    if not options:
        return [], None

    # 초기 로드 시(= selected_value가 None일 때)만 첫 번째 옵션을 기본값으로 지정
    if selected_value is None:
        return options, options[0]["value"]
    # 사용자가 이미 선택한 값이 있으면 그대로 유지
    return options, selected_value


# ───────────────────── ② 콘크리트 선택 콜백 ─────────────────────
@callback(
    Output("viewer-sensor", "figure"),
    Output("sensor-title", "children"),
    Output("tbl-sensor", "data"),
    Output("tbl-sensor", "columns"),
    Output("tbl-sensor", "selected_rows"),
    Output("btn-sensor-edit", "disabled"),
    Output("btn-sensor-del", "disabled"),
    Input("ddl-concrete", "value"),
    Input("toggle-lines", "value"),            
    Input("tbl-sensor", "data_timestamp"),     
    State("camera-store", "data"),
    prevent_initial_call=True,
)
def on_concrete_change(selected_conc, show_lines, tbl_timestamp, cam_store):
    if not selected_conc:
        return go.Figure(), "", [], [], [], True, True

    # ────────────────────────────────────────────────────────
    # 1) 콘크리트 정보 로드
    try:
        conc_row = api_db.get_concrete_data().query("concrete_pk == @selected_conc").iloc[0]
        activate = conc_row.get("activate", 1)
        dims = ast.literal_eval(conc_row["dims"])
        conc_nodes, conc_h = dims["nodes"], dims["h"]

    except Exception:
        return go.Figure(), "콘크리트 정보를 불러올 수 없음", [], [], [], True, True

    # 2) 기본 메쉬 생성
    fig = make_concrete_fig(conc_nodes, conc_h)

    # 3) 센서 데이터 로드
    df_sensor = api_db.get_sensors_data()
    df_sensor = df_sensor[df_sensor["concrete_pk"] == selected_conc].copy()

    xs, ys, zs = [], [], []
    sensor_ids = []
    colors, sizes = [], []
    table_data = []

    for idx, row in df_sensor.iterrows():
        try:
            dims = ast.literal_eval(row["dims"])
            x, y, z = float(dims["nodes"][0]), float(dims["nodes"][1]), float(dims["nodes"][2])
            pos_str = f"({x:.2f}, {y:.2f}, {z:.2f})"
        except Exception:
            x = y = z = 0.0
            pos_str = "파싱 오류"
        xs.append(x); ys.append(y); zs.append(z)
        sensor_ids.append(row["sensor_pk"])
        colors.append("blue")
        sizes.append(8)
        table_data.append({
            "sensor_pk": row["sensor_pk"],   # → 데이터에는 남김
            "device_id": row["device_id"],
            "channel":   row["channel"],
            "position":  pos_str,
        })

    # 4) 첫 번째 센서 강조
    selected_indices = [0] if sensor_ids else []

    if sensor_ids:
        colors[0] = "red"
        sizes[0] = 12
        selected_indices = [0] if table_data else []

    # 5) Sensors trace 추가 (점)
    fig.add_trace(go.Scatter3d(
        x=xs, y=ys, z=zs,
        mode="markers",
        marker=dict(size=sizes, color=colors, opacity=0.8),
        customdata=sensor_ids,
        hoverinfo="skip",
        name="Sensors",
    ))

    # 6) 보조선(show_lines=True일 때만)
    if show_lines:
        for x, y, z in zip(xs, ys, zs):
            # (a) 수직 보조선
            fig.add_trace(go.Scatter3d(
                x=[x, x],
                y=[y, y],
                z=[0, z],
                mode="lines",
                line=dict(color="gray", width=2, dash="dash"),
                hoverinfo="skip",
                showlegend=False,
            ))
            # (b) XY 평면 내 X축 투영
            x_ints = get_polygon_intersections_x(y, conc_nodes)
            if x_ints:
                left_candidates = [xi for xi in x_ints if xi < x]
                right_candidates = [xi for xi in x_ints if xi > x]
                x_min_bound = max(left_candidates) if left_candidates else x
                x_max_bound = min(right_candidates) if right_candidates else x
                fig.add_trace(go.Scatter3d(
                    x=[x_min_bound, x_max_bound],
                    y=[y, y],
                    z=[0, 0],
                    mode="lines",
                    line=dict(color="gray", width=2, dash="dash"),
                    hoverinfo="skip",
                    showlegend=False,
                ))
            # (c) XY 평면 내 Y축 투영
            y_ints = get_polygon_intersections_y(x, conc_nodes)
            if y_ints:
                down_candidates = [yi for yi in y_ints if yi < y]
                up_candidates = [yi for yi in y_ints if yi > y]
                y_min_bound = max(down_candidates) if down_candidates else y
                y_max_bound = min(up_candidates) if up_candidates else y
                fig.add_trace(go.Scatter3d(
                    x=[x, x],
                    y=[y_min_bound, y_max_bound],
                    z=[0, 0],
                    mode="lines",
                    line=dict(color="gray", width=2, dash="dash"),
                    hoverinfo="skip",
                    showlegend=False,
                ))

    # 7) 카메라 시점 유지
    if isinstance(cam_store, dict) and "eye" in cam_store:
        fig.update_layout(scene_camera=cam_store)

    # 8) 테이블 컬럼 정의
    columns = [
        {"name": "Device ID",     "id": "device_id"},
        {"name": "채널",           "id": "channel"},
        {"name": "위치 (x,y,z)",   "id": "position"},
    ]

    title         = f"{selected_conc} · 센서 전체"
    edit_disabled = True if activate == 0 else not bool(selected_indices)
    del_disabled  = not bool(selected_indices)

    title = f"{selected_conc} · 센서 전체"
    return fig, title, table_data, columns, selected_indices, edit_disabled, del_disabled


# ───────────────────── ③ 센서 선택 콜백 ─────────────────────
@callback(
    Output("viewer-sensor", "figure", allow_duplicate=True),
    Output("sensor-title", "children", allow_duplicate=True),
    Output("btn-sensor-edit", "disabled", allow_duplicate=True),
    Output("btn-sensor-del", "disabled", allow_duplicate=True),

    Input("tbl-sensor", "selected_rows"),
    State("tbl-sensor", "data"),
    State("viewer-sensor", "figure"),
    State("camera-store", "data"),
    State("ddl-concrete", "value"),
    prevent_initial_call=True,
)
def on_sensor_select(selected_rows, tbl_data, current_fig, cam_store, selected_conc):
    """
    DataTable에서 센서를 선택할 때:
    - 이전 Figure(current_fig)에서 camera를 유지
    - 'Sensors' trace의 marker.color/size만 업데이트하여 선택된 인덱스만 빨간색/크기 12로 변경
    """
    if not current_fig or not tbl_data:
        raise PreventUpdate

    fig = go.Figure(current_fig)

    # 1) camera-store가 있으면 덮어쓰기 (항상 카메라 최신 유지)
    if isinstance(cam_store, dict) and "eye" in cam_store:
        fig.update_layout(scene_camera=cam_store)

    # 2) 'Sensors' trace 찾기
    sensor_trace = None
    for tr in fig.data:
        if tr.name == "Sensors" and isinstance(tr.marker.color, (list, tuple)):
            sensor_trace = tr
            break

    if sensor_trace is None:
        raise PreventUpdate

    # 3) 색상/크기 모두 파란/8로 초기화
    n_points = len(sensor_trace.x)
    new_colors = ["blue"] * n_points
    new_sizes = [8] * n_points

    # 4) 선택된 인덱스만 빨간/12로 설정
    if selected_rows:
        sel_idx = selected_rows[0]
        if 0 <= sel_idx < n_points:
            new_colors[sel_idx] = "red"
            new_sizes[sel_idx] = 12   # ← 선택된 센서를 크기 12로 강조
            del_disabled = False
            activate = api_db.get_concrete_data().query("concrete_pk==@selected_conc").iloc[0].get("activate",1)
            edit_disabled = True if activate == 0 else False
            sel_id = sensor_trace.customdata[sel_idx]
            base_title = fig.layout.title.text if (fig.layout and fig.layout.title) else ""
            base_conc = base_title.split("·")[0].strip() if base_title else ""
            # 센서 정보 가져오기
            sensor_info = api_db.get_sensors_data(sensor_pk=sel_id).iloc[0]
            title = f"{base_conc} · {sensor_info['device_id']} (채널: {sensor_info['channel']})"
        else:
            edit_disabled = True
            del_disabled = True
            base_title = fig.layout.title.text if (fig.layout and fig.layout.title) else ""
            title = base_title
    else:
        edit_disabled = True
        del_disabled = True
        base_title = fig.layout.title.text if (fig.layout and fig.layout.title) else ""
        title = base_title

    # 5) trace 업데이트
    sensor_trace.marker.color = new_colors
    sensor_trace.marker.size = new_sizes

    return fig, title, edit_disabled, del_disabled


# ───────────────────── ④ 카메라 정보 저장 콜백 ────────────────────
# ───────────────────── ④ 카메라 정보 저장 콜백 (알림 비활성화 버전) ────────────────────
@callback(
    Output("camera-store", "data"),
    Input("viewer-sensor", "relayoutData"),
    State("camera-store", "data"),
    prevent_initial_call=True,
)
def capture_camera(relayout, cam_store):
    """
    사용자가 3D 뷰를 회전/줌/패닝할 때 relayoutData에
      1) 'scene.camera.eye.x', 'scene.camera.eye.y', 'scene.camera.eye.z', 
         'scene.camera.center.x', ... 등의 키가 개별적으로 올 때
      2) 또는 'scene.camera': { 'eye': {...}, 'center': {...}, 'up': {...} } 형태로 올 때
    두 경우를 모두 감지하여 camera-store에 저장.
    """

    # 0) relayout이 없다면 업데이트할 필요 없음
    if not relayout:
        raise PreventUpdate

    # 1) relayoutData에 'scene.camera' 전체 오브젝트가 있는지 먼저 확인
    try:
        if "scene.camera" in relayout and isinstance(relayout["scene.camera"], dict):
            cam_obj = relayout["scene.camera"]
            eye = cam_obj.get("eye", {})
            center = cam_obj.get("center", {})
            up = cam_obj.get("up", {})
            new_camera = {"eye": eye, "center": center, "up": up}
            return new_camera
    except Exception:
        # 파싱 에러가 나면 기존 cam_store 유지
        return cam_store

    # 2) 개별 키 형태인지 확인
    camera_keys = [k for k in relayout.keys() if k.startswith("scene.camera.")]
    if not camera_keys:
        raise PreventUpdate

    try:
        camera = cam_store.copy() if isinstance(cam_store, dict) else {}
        eye = camera.get("eye", {}).copy()
        center = camera.get("center", {}).copy()
        up = camera.get("up", {}).copy()
        updated = False

        for k, v in relayout.items():
            if k.startswith("scene.camera.eye."):
                comp = k.split(".")[-1]
                eye[comp] = v
                updated = True
            elif k.startswith("scene.camera.center."):
                comp = k.split(".")[-1]
                center[comp] = v
                updated = True
            elif k.startswith("scene.camera.up."):
                comp = k.split(".")[-1]
                up[comp] = v
                updated = True

        if not updated:
            raise PreventUpdate

        new_camera = {"eye": eye, "center": center, "up": up}
        return new_camera

    except PreventUpdate:
        raise
    except Exception:
        # 어떤 오류가 나더라도 기존 cam_store 유지
        return cam_store



# ───────────────────── ⑤ 추가 모달 토글 콜백 ─────────────────────
@callback(
    Output("modal-sensor-add", "is_open"),
    Input("btn-sensor-add",   "n_clicks"),
    Input("add-sensor-close", "n_clicks"),
    Input("add-sensor-save",  "n_clicks"),
    State("modal-sensor-add", "is_open"),
    prevent_initial_call=True,
)
def toggle_add_modal(b_add, b_close, b_save, is_open):
    trig = dash.callback_context.triggered_id
    if trig == "btn-sensor-add":
        return True
    if trig in ("add-sensor-close", "add-sensor-save"):
        return False
    return is_open


# ───────────────────── ⑥ 추가 미리보기 콜백 ─────────────────────
@callback(
    Output("add-sensor-preview", "figure"),
    Output("add-sensor-alert",   "children"),
    Output("add-sensor-alert",   "is_open"),
    Input("add-sensor-build", "n_clicks"),
    State("ddl-concrete",     "value"),
    State("add-sensor-device-id", "value"),
    State("add-sensor-channel", "value"),
    State("add-sensor-coords","value"),
    State("toggle-lines",     "value"),   # ← 메인 뷰 보조선 토글 상태
    prevent_initial_call=True,
)
def add_sensor_preview(_, conc_pk, device_id, channel, coords_txt, show_lines):
    """
    센서 추가 모달에서:
    1) 콘크리트 + 기존 센서(파란 점) + 보조선(show_lines=True인 경우)
    2) 새로 추가할 센서를 파란 점(크기 6)으로 미리보기
    3) 이미 존재하는 디바이스 ID와 채널 조합이 입력되면 Alert 반환
    """
    # 콘크리트, 디바이스 ID, 채널, 좌표 입력 검사
    if not conc_pk:
        return dash.no_update, "콘크리트를 먼저 선택하세요", True
    if not device_id:
        return dash.no_update, "Device ID를 입력하세요", True
    if not channel:
        return dash.no_update, "채널 번호를 입력하세요", True

    # (추가) 동일 콘크리트 내 기존 센서 디바이스 ID와 채널 조합 확인
    df_sensor_full = api_db.get_sensors_data()
    df_same = df_sensor_full[df_sensor_full["concrete_pk"] == conc_pk]
    existing_sensors = df_same[(df_same["device_id"] == device_id) & (df_same["channel"] == channel)]
    if not existing_sensors.empty:
        return dash.no_update, f"이미 존재하는 디바이스 ID와 채널 조합: {device_id} (채널: {channel})", True

    if not coords_txt:
        return dash.no_update, "좌표를 입력하세요 (예: [1,1,0])", True

    # 1) 콘크리트 정보 로드 & 기본 Mesh 그리기
    try:
        conc_row = api_db.get_concrete_data().query("concrete_pk == @conc_pk").iloc[0]
        conc_dims = ast.literal_eval(conc_row["dims"])
        conc_nodes, conc_h = conc_dims["nodes"], conc_dims["h"]
        fig_conc = make_concrete_fig(conc_nodes, conc_h)
    except Exception:
        return go.Figure(), "콘크리트 정보를 불러올 수 없음", True

    # 2) 현재 콘크리트에 속한 기존 센서 정보를 모두 가져와서 그리기 (파란 점, 크기 4)
    all_xs, all_ys, all_zs = [], [], []
    for idx, row in df_same.iterrows():
        try:
            dims = ast.literal_eval(row["dims"])
            x_s, y_s, z_s = float(dims["nodes"][0]), float(dims["nodes"][1]), float(dims["nodes"][2])
        except Exception:
            x_s, y_s, z_s = 0.0, 0.0, 0.0
        all_xs.append(x_s); all_ys.append(y_s); all_zs.append(z_s)

    # (1) 파란 점으로 기존 센서 모두 그리기 (크기 4)
    fig_conc.add_trace(go.Scatter3d(
        x=all_xs, y=all_ys, z=all_zs,
        mode="markers",
        marker=dict(size=4, color="blue", opacity=0.8),
        hoverinfo="skip",
        name="Existing Sensors",
    ))

    # (2) show_lines=True일 때만 보조선을 그리기
    if show_lines:
        for x_s, y_s, z_s in zip(all_xs, all_ys, all_zs):
            # ── (a) 수직 보조선: (x_s, y_s, 0) → (x_s, y_s, z_s)
            fig_conc.add_trace(go.Scatter3d(
                x=[x_s, x_s],
                y=[y_s, y_s],
                z=[0, z_s],
                mode="lines",
                line=dict(color="gray", width=2, dash="dash"),
                hoverinfo="skip",
                showlegend=False,
            ))

            # ── (b) XY 평면 X축 투영 (y=y_s, z=0)
            x_ints = get_polygon_intersections_x(y_s, conc_nodes)
            if x_ints:
                left_candidates = [xi for xi in x_ints if xi < x_s]
                right_candidates = [xi for xi in x_ints if xi > x_s]
                x_min_bound = max(left_candidates) if left_candidates else x_s
                x_max_bound = min(right_candidates) if right_candidates else x_s
                fig_conc.add_trace(go.Scatter3d(
                    x=[x_min_bound, x_max_bound],
                    y=[y_s, y_s],
                    z=[0, 0],
                    mode="lines",
                    line=dict(color="gray", width=2, dash="dash"),
                    hoverinfo="skip",
                    showlegend=False,
                ))

            # ── (c) XY 평면 Y축 투영 (x=x_s, z=0)
            y_ints = get_polygon_intersections_y(x_s, conc_nodes)
            if y_ints:
                down_candidates = [yi for yi in y_ints if yi < y_s]
                up_candidates = [yi for yi in y_ints if yi > y_s]
                y_min_bound = max(down_candidates) if down_candidates else y_s
                y_max_bound = min(up_candidates) if up_candidates else y_s
                fig_conc.add_trace(go.Scatter3d(
                    x=[x_s, x_s],
                    y=[y_min_bound, y_max_bound],
                    z=[0, 0],
                    mode="lines",
                    line=dict(color="gray", width=2, dash="dash"),
                    hoverinfo="skip",
                    showlegend=False,
                ))

    # 3) coords_txt 파싱 → 새로 추가할 센서 좌표
    try:
        xyz = ast.literal_eval(coords_txt)
        if not (isinstance(xyz, (list, tuple)) and len(xyz) == 3):
            raise ValueError
        xyz = [float(x) for x in xyz]
    except Exception:
        return dash.no_update, "좌표 형식이 잘못되었습니다 (예: [1,1,0])", True

    # 4) 새로 추가할 센서를 파란 점(크기 6)으로 표시
    fig_conc.add_trace(go.Scatter3d(
        x=[xyz[0]], y=[xyz[1]], z=[xyz[2]],
        mode="markers",
        marker=dict(size=6, color="yellow", opacity=0.6),
        name="Preview New Sensor",
        hoverinfo="skip",
    ))

    return fig_conc, "", False


# ───────────────────── ⑦ 추가 저장 콜백 ─────────────────────
@callback(
    Output("tbl-sensor", "data_timestamp", allow_duplicate=True),
    Output("add-sensor-alert", "children", allow_duplicate=True),
    Output("add-sensor-alert", "color",    allow_duplicate=True),
    Output("add-sensor-alert", "is_open",  allow_duplicate=True),
    Input("add-sensor-save", "n_clicks"),
    State("ddl-concrete",     "value"),
    State("add-sensor-device-id", "value"),
    State("add-sensor-channel", "value"),
    State("add-sensor-coords","value"),
    prevent_initial_call=True,
)
def add_sensor_save(_, conc_pk, device_id, channel, coords_txt):
    """
    센서 추가 시:
    1) 콘크리트를 선택했는지, 디바이스 ID와 채널, 좌표를 입력했는지 확인
    2) 동일 콘크리트 내에 이미 같은 디바이스 ID와 채널 조합이 있으면 Alert 반환 후 저장 중단
    3) 좌표 형식이 정상일 경우 api_sensor.add_sensor 호출
    4) 성공하면 data_timestamp를 갱신 → 메인 뷰 테이블 재로딩
    """
    if not (conc_pk and device_id and channel):
        return dash.no_update, "콘크리트, 디바이스 ID, 채널을 모두 입력하세요", "danger", True

    # (추가) 동일 콘크리트 내 기존 센서 디바이스 ID와 채널 조합 확인
    df_sensor_full = api_db.get_sensors_data()
    df_same = df_sensor_full[df_sensor_full["concrete_pk"] == conc_pk]
    existing_sensors = df_same[(df_same["device_id"] == device_id) & (df_same["channel"] == channel)]
    if not existing_sensors.empty:
        return dash.no_update, f"이미 존재하는 디바이스 ID와 채널 조합: {device_id} (채널: {channel})", "danger", True

    if not coords_txt:
        return dash.no_update, "좌표를 입력하세요 (예: [1,1,0])", "danger", True

    # 좌표 파싱
    try:
        xyz = ast.literal_eval(coords_txt)
        if not (isinstance(xyz, (list, tuple)) and len(xyz) == 3):
            raise ValueError
        xyz = [float(x) for x in xyz]
    except Exception:
        return dash.no_update, "좌표 형식이 잘못되었습니다 (예: [1,1,0])", "danger", True

    # 실제 추가
    try:
        api_db.add_sensors_data(concrete_pk=conc_pk, device_id=device_id, channel=channel, d_type=1, dims={"nodes": xyz})
    except Exception as e:
        return dash.no_update, f"추가 실패: {e}", "danger", True

    # data_timestamp를 업데이트해서 테이블 갱신 트리거
    return pd.Timestamp.utcnow().value, "추가 완료", "success", True


# ───────────────────── ⑧ 삭제 컨펌 토글 콜백 ───────────────────
@callback(
    Output("confirm-del-sensor", "displayed"),
    Input("btn-sensor-del", "n_clicks"),
    State("tbl-sensor", "selected_rows"),
    prevent_initial_call=True
)
def ask_delete_sensor(n, sel):
    return bool(n and sel)


@callback(
    Output("tbl-sensor", "data_timestamp", allow_duplicate=True),
    Output("add-sensor-alert",    "children",      allow_duplicate=True),
    Output("add-sensor-alert",    "color",         allow_duplicate=True),
    Output("add-sensor-alert",    "is_open",       allow_duplicate=True),
    Input("confirm-del-sensor",   "submit_n_clicks"),
    State("tbl-sensor",           "selected_rows"),
    State("tbl-sensor",           "data"),
    State("ddl-concrete",         "value"),
    prevent_initial_call=True,
)
def delete_sensor_confirm(_click, sel, tbl_data, conc_pk):
    if not (sel and conc_pk):
        raise PreventUpdate

    row = pd.DataFrame(tbl_data).iloc[sel[0]]
    sensor_pk = row["sensor_pk"]       # ← 이제 에러 없이 조회됨

    try:
        api_db.delete_sensors_data(sensor_pk)
    except Exception as e:
        return dash.no_update, f"삭제 실패: {e}", "danger", True

    return pd.Timestamp.utcnow().value, f"{sensor_pk} 삭제 완료", "warning", True


# ───────────────────── ⑨ 수정 모달 토글 콜백 ───────────────────
@callback(
    Output("modal-sensor-edit", "is_open"),
    Output("edit-sensor-concrete-id", "data"),
    Output("edit-sensor-id-store", "data"),
    Input("btn-sensor-edit", "n_clicks"),
    Input("edit-sensor-close", "n_clicks"),
    Input("edit-sensor-save", "n_clicks"),
    State("tbl-sensor", "selected_rows"), State("tbl-sensor", "data"),
    State("ddl-concrete", "value"),
    prevent_initial_call=True,
)
def toggle_edit_modal(b_open, b_close, b_save, sel, tbl_data, conc_pk):
    trig = dash.callback_context.triggered_id
    # "수정" 버튼을 누르면, 선택된 센서 정보(콘크리트ID + 센서ID)를 저장 후 모달 열기
    if trig == "btn-sensor-edit" and sel and conc_pk:
        row = pd.DataFrame(tbl_data).iloc[sel[0]]
        return True, conc_pk, row["sensor_pk"]
    return False, dash.no_update, dash.no_update


# ───────────────────── ⑩ 수정 모달 필드 채우기 콜백 ─────────────────────
@callback(
    Output("edit-sensor-coords", "value"),
    Output("edit-sensor-preview", "figure"),
    Output("edit-sensor-alert", "children"),
    Output("edit-sensor-alert", "is_open"),
    Output("edit-sensor-device-id", "children"),
    Output("edit-sensor-channel", "children"),
    Input("modal-sensor-edit", "is_open"),
    State("edit-sensor-concrete-id", "data"),
    State("edit-sensor-id-store", "data"),
    State("edit-toggle-lines", "value"),      # ← 모달 내 보조선 토글 스위치 상태
)
def fill_edit_sensor(opened, conc_pk, sensor_pk, show_lines):
    if not opened or not (conc_pk and sensor_pk):
        raise PreventUpdate

    # 1) 센서 정보 로드
    try:
        sensor_row = api_db.get_sensors_data(sensor_pk=sensor_pk).iloc[0]
        device_id = sensor_row["device_id"]
        channel = sensor_row["channel"]
        dims = ast.literal_eval(sensor_row["dims"])
        coords_txt = f"[{dims['nodes'][0]}, {dims['nodes'][1]}, {dims['nodes'][2]}]"
    except Exception:
        return dash.no_update, go.Figure(), "센서 정보를 불러올 수 없음", True, "", ""

    # 2) 콘크리트 정보 로드
    try:
        conc_row = api_db.get_concrete_data().query("concrete_pk == @conc_pk").iloc[0]
        conc_dims = ast.literal_eval(conc_row["dims"])
        conc_nodes, conc_h = conc_dims["nodes"], conc_dims["h"]
        fig_conc = make_concrete_fig(conc_nodes, conc_h)
    except Exception:
        return dash.no_update, go.Figure(), "콘크리트 정보를 불러올 수 없음", True, device_id, channel

    # 3) 현재 콘크리트에 속한 모든 센서 정보를 가져와서 그리기 (파란 점, 크기 4)
    df_sensor_full = api_db.get_sensors_data()
    df_same = df_sensor_full[df_sensor_full["concrete_pk"] == conc_pk].copy()

    all_xs, all_ys, all_zs = [], [], []
    all_ids = []
    for idx, row in df_same.iterrows():
        try:
            dims = ast.literal_eval(row["dims"])
            x_s, y_s, z_s = float(dims["nodes"][0]), float(dims["nodes"][1]), float(dims["nodes"][2])
        except Exception:
            x_s, y_s, z_s = 0.0, 0.0, 0.0
        all_xs.append(x_s); all_ys.append(y_s); all_zs.append(z_s)
        all_ids.append(row["sensor_pk"])

    # 모든 센서를 파란 점(크기 4)으로 추가
    fig_conc.add_trace(go.Scatter3d(
        x=all_xs, y=all_ys, z=all_zs,
        mode="markers",
        marker=dict(size=4, color="blue", opacity=0.8),
        customdata=all_ids,
        hoverinfo="skip",
        name="All Sensors (for edit)",
    ))

    # 4) 보조선(show_lines=True 일 때만)
    if show_lines:
        for x_s, y_s, z_s in zip(all_xs, all_ys, all_zs):
            # ① 수직 보조선
            fig_conc.add_trace(go.Scatter3d(
                x=[x_s, x_s],
                y=[y_s, y_s],
                z=[0, z_s],
                mode="lines",
                line=dict(color="gray", width=2, dash="dash"),
                hoverinfo="skip",
                showlegend=False,
            ))
            # ② XY 평면 X축 투영
            x_ints = get_polygon_intersections_x(y_s, conc_nodes)
            if x_ints:
                left_candidates = [xi for xi in x_ints if xi < x_s]
                right_candidates = [xi for xi in x_ints if xi > x_s]
                if left_candidates:
                    x_min_bound = max(left_candidates)
                else:
                    x_min_bound = x_s
                if right_candidates:
                    x_max_bound = min(right_candidates)
                else:
                    x_max_bound = x_s
                fig_conc.add_trace(go.Scatter3d(
                    x=[x_min_bound, x_max_bound],
                    y=[y_s, y_s],
                    z=[0, 0],
                    mode="lines",
                    line=dict(color="gray", width=2, dash="dash"),
                    hoverinfo="skip",
                    showlegend=False,
                ))
            # ③ XY 평면 Y축 투영
            y_ints = get_polygon_intersections_y(x_s, conc_nodes)
            if y_ints:
                down_candidates = [yi for yi in y_ints if yi < y_s]
                up_candidates = [yi for yi in y_ints if yi > y_s]
                if down_candidates:
                    y_min_bound = max(down_candidates)
                else:
                    y_min_bound = y_s
                if up_candidates:
                    y_max_bound = min(up_candidates)
                else:
                    y_max_bound = y_s
                fig_conc.add_trace(go.Scatter3d(
                    x=[x_s, x_s],
                    y=[y_min_bound, y_max_bound],
                    z=[0, 0],
                    mode="lines",
                    line=dict(color="gray", width=2, dash="dash"),
                    hoverinfo="skip",
                    showlegend=False,
                ))

    # 5) 수정 대상 센서만 빨간 점(크기 6)으로 강조
    matching = df_same[df_same["sensor_pk"] == sensor_pk]
    if not matching.empty:
        dims_sensor = ast.literal_eval(matching.iloc[0]["dims"])
        x, y, z = float(dims_sensor["nodes"][0]), float(dims_sensor["nodes"][1]), float(dims_sensor["nodes"][2])
        fig_conc.add_trace(go.Scatter3d(
            x=[x], y=[y], z=[z],
            mode="markers",
            marker=dict(size=6, color="red"),  # ← 빨간 점의 크기 6
            name="Selected Sensor (for edit)",
            hoverinfo="skip",
        ))

    return coords_txt, fig_conc, "", False, device_id, channel


# ───────────────────── ⑪ 수정 미리보기 콜백 ────────────────────
@callback(
    Output("edit-sensor-preview", "figure", allow_duplicate=True),
    Output("edit-sensor-alert", "children", allow_duplicate=True),
    Output("edit-sensor-alert", "is_open", allow_duplicate=True),
    Input("edit-sensor-build", "n_clicks"),           # "새로고침" 버튼 클릭
    Input("edit-toggle-lines", "value"),              # 모달 내 보조선 스위치 값
    State("edit-sensor-coords", "value"),             # 수정할 좌표
    State("edit-sensor-concrete-id", "data"),         # 현재 콘크리트 ID
    State("edit-sensor-id-store", "data"),            # 수정 중인 센서 ID
    prevent_initial_call=True,
)
def edit_sensor_preview(n_clicks, show_lines, coords_txt, conc_pk, sensor_pk):
    """
    수정 모달에서:
    - '새로고침' 버튼(n_clicks) OR
    - '모달 내 보조선 표시' 스위치(show_lines)
    둘 중 하나가 변경되면 실행됩니다.

    1) 콘크리트 + (수정 대상 제외) 나머지 센서를 파란 점으로 그림
    2) show_lines=True 면 보조선을 그림
    3) 입력된 coords_txt로 수정된 센서를 빨간 점으로 그림
    """
    # 1) 콘크리트 정보 로드 & 기본 Mesh 그리기
    try:
        conc_row = api_db.get_concrete_data().query("concrete_pk == @conc_pk").iloc[0]
        conc_dims = ast.literal_eval(conc_row["dims"])
        conc_nodes, conc_h = conc_dims["nodes"], conc_dims["h"]
        fig_conc = make_concrete_fig(conc_nodes, conc_h)
    except Exception:
        # 콘크리트 정보 로드 실패 시 빈 Figure와 에러 토스트 반환
        return dash.no_update, "콘크리트 정보를 불러올 수 없음", True

    # 2) 수정 중인 센서를 제외한 "나머지 센서들"을 파란 점으로 먼저 그리기
    df_sensor_full = api_db.get_sensors_data()
    df_same = df_sensor_full[df_sensor_full["concrete_pk"] == conc_pk].copy()

    for idx, row in df_same.iterrows():
        sid = row["sensor_pk"]
        # (★) 수정 대상 sensor_id는 제외하고 그린다
        if sid == sensor_pk:
            continue

        try:
            dims = ast.literal_eval(row["dims"])
            x_s, y_s, z_s = float(dims["nodes"][0]), float(dims["nodes"][1]), float(dims["nodes"][2])
        except Exception:
            x_s, y_s, z_s = 0.0, 0.0, 0.0

        fig_conc.add_trace(go.Scatter3d(
            x=[x_s], y=[y_s], z=[z_s],
            mode="markers",
            marker=dict(size=4, color="blue"),  # 비수정 센서: 파란 점 (크기 4)
            hoverinfo="skip",
            showlegend=False,
        ))

    # 3) show_lines=True일 때만 보조선을 그린다
    if show_lines:
        for idx, row in df_same.iterrows():
            try:
                dims = ast.literal_eval(row["dims"])
                x_s, y_s, z_s = float(dims["nodes"][0]), float(dims["nodes"][1]), float(dims["nodes"][2])
            except Exception:
                x_s, y_s, z_s = 0.0, 0.0, 0.0

            # (a) 수직 보조선: (x_s, y_s, 0) → (x_s, y_s, z_s)
            fig_conc.add_trace(go.Scatter3d(
                x=[x_s, x_s],
                y=[y_s, y_s],
                z=[0, z_s],
                mode="lines",
                line=dict(color="gray", width=2, dash="dash"),
                hoverinfo="skip",
                showlegend=False,
            ))

            # (b) XY 평면 내 X축 투영 (y=y_s, z=0)
            x_ints = get_polygon_intersections_x(y_s, conc_nodes)
            if x_ints:
                left_candidates = [xi for xi in x_ints if xi < x_s]
                right_candidates = [xi for xi in x_ints if xi > x_s]
                x_min_bound = max(left_candidates) if left_candidates else x_s
                x_max_bound = min(right_candidates) if right_candidates else x_s
                fig_conc.add_trace(go.Scatter3d(
                    x=[x_min_bound, x_max_bound],
                    y=[y_s, y_s],
                    z=[0, 0],
                    mode="lines",
                    line=dict(color="gray", width=2, dash="dash"),
                    hoverinfo="skip",
                    showlegend=False,
                ))

            # (c) XY 평면 Y축 투영 (x=x_s, z=0)
            y_ints = get_polygon_intersections_y(x_s, conc_nodes)
            if y_ints:
                down_candidates = [yi for yi in y_ints if yi < y_s]
                up_candidates = [yi for yi in y_ints if yi > y_s]
                y_min_bound = max(down_candidates) if down_candidates else y_s
                y_max_bound = min(up_candidates) if up_candidates else y_s
                fig_conc.add_trace(go.Scatter3d(
                    x=[x_s, x_s],
                    y=[y_min_bound, y_max_bound],
                    z=[0, 0],
                    mode="lines",
                    line=dict(color="gray", width=2, dash="dash"),
                    hoverinfo="skip",
                    showlegend=False,
                ))

    # 4) coords_txt(수정할 좌표) 파싱
    if not coords_txt:
        return dash.no_update, "좌표를 입력하세요 (예: [1,1,0])", True
    try:
        xyz = ast.literal_eval(coords_txt)
        if not (isinstance(xyz, (list, tuple)) and len(xyz) == 3):
            raise ValueError
        x_new, y_new, z_new = [float(v) for v in xyz]
    except Exception:
        return dash.no_update, "좌표 형식이 잘못되었습니다 (예: [1,1,0])", True

    # 5) 수정된 센서를 빨간 점(크기 6)으로 표시
    fig_conc.add_trace(go.Scatter3d(
        x=[x_new], y=[y_new], z=[z_new],
        mode="markers",
        marker=dict(size=6, color="red"),  # 수정된 센서: 빨간 점 (크기 6)
        name="Preview Edited Sensor",
        hoverinfo="skip",
    ))

    return fig_conc, "", False


# ───────────────────── ⑫ 수정 저장 콜백 ────────────────────────
@callback(
    Output("tbl-sensor", "data_timestamp", allow_duplicate=True),
    Output("edit-sensor-alert", "children", allow_duplicate=True),
    Output("edit-sensor-alert", "color", allow_duplicate=True),
    Output("edit-sensor-alert", "is_open", allow_duplicate=True),
    Input("edit-sensor-save", "n_clicks"),
    State("edit-sensor-concrete-id", "data"),
    State("edit-sensor-id-store", "data"),       # old_sensor_pk
    State("edit-sensor-coords", "value"),        # 수정된 좌표
    prevent_initial_call=True,
)
def edit_sensor_save(n_clicks, conc_pk, old_sensor_pk, coords_txt):
    if not (conc_pk and old_sensor_pk):
        return dash.no_update, "데이터 로드 실패", "danger", True
    if not coords_txt:
        return dash.no_update, "좌표를 입력하세요 (예: [1,1,0])", "danger", True

    try:
        xyz = ast.literal_eval(coords_txt)
        if not (isinstance(xyz, (list, tuple)) and len(xyz) == 3):
            raise ValueError
        xyz = [float(x) for x in xyz]
    except Exception:
        return dash.no_update, "좌표 형식이 잘못되었습니다 (예: [1,1,0])", "danger", True

    try:
        api_db.update_sensors_data(sensor_pk=old_sensor_pk, dims={"nodes": xyz})
    except Exception as e:
        return dash.no_update, f"위치 업데이트 실패: {e}", "danger", True

    # 성공: 테이블 갱신
    return pd.Timestamp.utcnow().value, f"{old_sensor_pk} 위치 수정 완료", "success", True
