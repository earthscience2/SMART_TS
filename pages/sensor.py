#!/usr/bin/env python3
# pages/sensor.py
"""Dash page for managing sensors attached to selected concrete elements.

* 왼쪽에서 콘크리트를 선택 → 해당 콘크리트의 센서 리스트 표시
* 센서 추가/수정/삭제 기능
* 우측 3D 뷰: 콘크리트 구조 + 센서 위치(붉은 점) 표시, 기본적으로 모든 센서 표시
  → 선택된 센서는 강조 표시(크기 및 색상)
* [변경] 센서 위치 입력: 세 개 필드 → 한 필드("[x,y,z]")로 통합
* [변경] `msg` Alert 제거 → add/edit 전용 Alert(`add-sensor-alert`, `edit-sensor-alert`) 사용
* [변경] 센서를 클릭할 때마다 이전에 그 센서에서 보던 시점을 저장하고, 
           해당 센서를 다시 선택할 때 저장된 시점을 복원하도록 수정
"""

from __future__ import annotations

import ast
import numpy as np
import pandas as pd
import dash  # dash.no_update 사용을 위해 import
import plotly.graph_objects as go
from dash import (
    html, dcc, Input, Output, State, ctx,
    dash_table, register_page, callback
)
import dash_bootstrap_components as dbc
import api_sensor
import api_concrete
from dash.exceptions import PreventUpdate

register_page(__name__, path="/sensor")


# ────────────────────────────── 3-D 헬퍼 ─────────────────────────────
def make_concrete_fig(nodes: list[list[float]], h: float) -> go.Figure:
    """
    기존 concrete의 3D 뷰를 그리는 함수.
    nodes: [[x, y], ...], h: 높이
    """
    fig = go.Figure()
    poly = np.array(nodes)
    x0, y0 = poly[:, 0], poly[:, 1]
    z0 = np.zeros(len(nodes))
    x1, y1 = x0, y0
    z1 = np.full(len(nodes), h)

    # 꼭짓점 벡터
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


def overlay_sensor(fig: go.Figure, sensor_xyz: list[float], selected: bool = False) -> go.Figure:
    """
    이미 만들어진 콘크리트 3D(fig)에 센서 위치를 추가.
    selected=True일 때는 강조(빨간, 크게) 표시, 아니면 파란색 반투명.
    sensor_xyz: [x, y, z]
    """
    x, y, z = sensor_xyz
    if selected:
        fig.add_trace(go.Scatter3d(
            x=[x], y=[y], z=[z],
            mode="markers",
            marker=dict(size=8, color="red"),
            name="Selected Sensor",
            hoverinfo="skip"
        ))
    else:
        fig.add_trace(go.Scatter3d(
            x=[x], y=[y], z=[z],
            mode="markers",
            marker=dict(size=4, color="blue", opacity=0.6),
            name="Sensor",
            hoverinfo="skip"
        ))
    return fig


# ────────────────────────────── 레이아웃 ────────────────────────────
layout = dbc.Container(
    fluid=True,
    children=[
        # ── (★) 각 센서별 카메라 정보를 저장하기 위한 Store
        dcc.Store(id="camera-store", data={}),  # 초기값: 빈 dict

        # 상단: 콘크리트 선택 → 센서 테이블 + 버튼
        dbc.Row(
            [
                # ── 콘크리트 선택 + 센서 리스트 영역 ─────────────────────────
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
                            page_size=20,
                            row_selectable="single",
                            style_table={"overflowY": "auto", "height": "50vh"},
                            style_cell={"whiteSpace": "nowrap", "textAlign": "center"},
                            style_header={"backgroundColor": "#f1f3f5", "fontWeight": 600},
                        ),
                        dbc.ButtonGroup(
                            [
                                dbc.Button("+ 추가", id="btn-sensor-add", color="success", className="mt-2"),
                                dbc.Button("수정", id="btn-sensor-edit", color="secondary", className="mt-2", disabled=True),
                                dbc.Button("삭제", id="btn-sensor-del", color="danger", className="mt-2", disabled=True),
                            ],
                            size="sm",
                            vertical=True,
                            className="w-100",
                        ),
                        dcc.ConfirmDialog(id="confirm-del-sensor", message="선택한 센서를 정말 삭제하시겠습니까?"),
                    ],
                    md=3,
                ),
                # ── 3D 뷰 영역 ─────────────────────────────────────────────────
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
                        dbc.Input(id="add-sensor-id", placeholder="Sensor ID (예: S001)", className="mb-2"),
                        dbc.Input(id="add-sensor-coords", placeholder="센서 좌표 [x, y, z] (예: [1, 1, 0])", className="mb-2"),
                        dcc.Graph(id="add-sensor-preview", style={"height": "45vh"}, className="border"),
                    ]
                ),
                dbc.ModalFooter(
                    [
                        dbc.Button("미리보기", id="add-sensor-build", color="info", className="me-auto"),
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
                dbc.ModalHeader("센서 수정"),
                dbc.ModalBody(
                    [
                        dcc.Store(id="edit-sensor-concrete-id"),
                        dcc.Store(id="edit-sensor-id-store"),
                        dbc.Alert(id="edit-sensor-alert", is_open=False, duration=3000, color="danger"),
                        dbc.Input(id="edit-sensor-id", disabled=True, className="mb-2"),
                        dbc.Input(id="edit-sensor-coords", placeholder="센서 좌표 [x, y, z] (예: [1, 1, 0])", className="mb-2"),
                        dcc.Graph(id="edit-sensor-preview", style={"height": "45vh"}, className="border"),
                    ]
                ),
                dbc.ModalFooter(
                    [
                        dbc.Button("미리보기", id="edit-sensor-build", color="info", className="me-auto"),
                        dbc.Button("저장", id="edit-sensor-save", color="primary"),
                        dbc.Button("닫기", id="edit-sensor-close", color="secondary"),
                    ]
                ),
            ],
        ),
    ],
)


# ───────────────────── ① 페이지 초기화 ──────────────────────
@callback(
    Output("ddl-concrete", "options"),
    Output("ddl-concrete", "value"),
    Input("ddl-concrete", "id"),  # 페이지 로드 시 한 번 트리거
    prevent_initial_call=False,
)
def init_dropdown(_):
    """
    페이지 로드 시 concrete 목록을 Dropdown 옵션으로 설정.
    """
    df_conc = api_concrete.load_all()
    options = [
        {"label": f"{row['concrete_id']} · {row['name']}", "value": row["concrete_id"]}
        for _, row in df_conc.iterrows()
    ]
    if not options:
        return [], None
    return options, options[0]["value"]


# ───────────────────── ② 센서 테이블 로드 ────────────────────
@callback(
    Output("tbl-sensor", "data"),
    Output("tbl-sensor", "columns"),
    Output("tbl-sensor", "selected_rows"),
    Input("ddl-concrete", "value"),
    Input("tbl-sensor", "data_timestamp"),
    prevent_initial_call=False,
)
def refresh_sensor_table(selected_conc, _):
    """
    선택된 concrete_id에 속한 센서들만 테이블에 표시.
    """
    if not selected_conc:
        return [], [], []
    df_sensor = api_sensor.load_all_sensors()
    df_sensor = df_sensor[df_sensor["concrete_id"] == selected_conc].copy()

    data = []
    for _, row in df_sensor.iterrows():
        try:
            dims = ast.literal_eval(row["dims"])
            xyz = dims.get("nodes", [])
            pos_str = f"({xyz[0]:.2f}, {xyz[1]:.2f}, {xyz[2]:.2f})"
        except Exception:
            pos_str = "파싱 오류"
        data.append({"sensor_id": row["sensor_id"], "position": pos_str})

    columns = [
        {"name": "Sensor ID", "id": "sensor_id"},
        {"name": "위치 (x,y,z)", "id": "position"},
    ]
    sel = [0] if data else []
    return data, columns, sel


# ───────────────────── ③ 카메라 정보 저장 콜백 ────────────────────
@callback(
    Output("camera-store", "data"),
    Input("viewer-sensor", "relayoutData"),
    State("camera-store", "data"),
    State("tbl-sensor", "selected_rows"),
    State("tbl-sensor", "data"),
    prevent_initial_call=True,
)
def capture_camera(relayout, cam_store, selected_rows, tbl_data):
    """
    사용자가 3D 뷰를 마우스로 돌리거나 확대/축소할 때,
    relayoutData에 'scene.camera.eye.x' 등의 키가 들어온다.
    이 정보를 현재 선택된 센서 ID를 키로 해서 camera-store에 저장.
    """
    if not relayout:
        raise PreventUpdate

    # 현재 선택된 센서 ID가 있어야 저장할 수 있음
    if not (selected_rows and tbl_data):
        return cam_store

    sel_sensor_id = pd.DataFrame(tbl_data).iloc[selected_rows[0]]["sensor_id"]

    # 이전에 저장된 카메라 정보를 가져오고, 없으면 빈 구조 생성
    prev_camera = cam_store.get(sel_sensor_id, {})
    eye = prev_camera.get("eye", {}).copy()
    center = prev_camera.get("center", {}).copy()
    up = prev_camera.get("up", {}).copy()

    updated = False
    for k, v in relayout.items():
        if k.startswith("scene.camera.eye."):
            comp = k.split(".")[-1]  # 'x' or 'y' or 'z'
            eye[comp] = v
            updated = True
        if k.startswith("scene.camera.center."):
            comp = k.split(".")[-1]
            center[comp] = v
            updated = True
        if k.startswith("scene.camera.up."):
            comp = k.split(".")[-1]
            up[comp] = v
            updated = True

    if updated:
        cam_store[sel_sensor_id] = {"eye": eye, "center": center, "up": up}
        return cam_store

    return cam_store


# ───────────────────── ④ 콘크리트/센서 선택 시 3D 뷰 갱신 ─────────
@callback(
    Output("viewer-sensor", "figure"),
    Output("sensor-title", "children"),
    Output("btn-sensor-edit", "disabled"),
    Output("btn-sensor-del",  "disabled"),
    Input("tbl-sensor", "selected_rows"),
    State("tbl-sensor", "data"),
    State("ddl-concrete", "value"),
    State("viewer-sensor", "figure"),  # 이전에 렌더링된 figure
    State("camera-store", "data"),     # 센서별로 저장된 카메라 정보 딕셔너리
)
def show_sensor_3d(selected_rows, tbl_data, selected_conc, prev_fig, cam_store):
    """
    1) 선택된 콘크리트 3D 뷰
    2) 해당 콘크리트 전체 센서 위치 표시 (파란 점)
    3) 선택된 센서는 빨간 점(크게) 강조

    → 현재 선택된 센서 ID를 보고, cam_store에서 저장된 카메라 정보를
       가져와서 뷰를 그릴 때 항상 적용
    → 콘크리트 메쉬는 prev_fig에서 가져오지 않고, 매번 make_concrete_fig으로 새로 생성
       (카메라는 cam_store에만 의존)
    """
    # 콘크리트를 선택하지 않았거나 불러올 수 없으면 빈 Figure 반환
    if not selected_conc:
        return go.Figure(), "", True, True

    try:
        conc_row = api_concrete.load_all().query("concrete_id == @selected_conc").iloc[0]
        conc_dims = ast.literal_eval(conc_row["dims"])
        conc_nodes, conc_h = conc_dims["nodes"], conc_dims["h"]
    except Exception:
        return go.Figure(), "콘크리트 정보를 불러올 수 없음", True, True

    # ① 새 콘크리트 메쉬 생성
    fig_conc = make_concrete_fig(conc_nodes, conc_h)

    # ② 현재 선택된 센서 ID
    sel_sensor_id = None
    if selected_rows and tbl_data:
        sel_sensor_id = pd.DataFrame(tbl_data).iloc[selected_rows[0]]["sensor_id"]

    # ③ cam_store에 해당 센서 ID로 저장된 카메라 정보가 있으면 적용
    if sel_sensor_id and isinstance(cam_store, dict):
        cam = cam_store.get(sel_sensor_id)
        if isinstance(cam, dict) and "eye" in cam:
            fig_conc.update_layout(scene_camera=cam)

    # ④ 모든 센서 좌표 불러와서 파란 점으로 표시
    df_all = api_sensor.load_all_sensors()
    df_this = df_all[df_all["concrete_id"] == selected_conc]
    all_xyz = []
    for _, row in df_this.iterrows():
        try:
            dims = ast.literal_eval(row["dims"])
            coord = dims.get("nodes", [])
            all_xyz.append((row["sensor_id"], [float(coord[0]), float(coord[1]), float(coord[2])]))
        except Exception:
            continue

    for s_id, xyz in all_xyz:
        fig_conc = overlay_sensor(fig_conc, xyz, selected=False)

    # 기본 타이틀
    title = f"{selected_conc} · 센서 전체"

    # ⑤ 선택된 센서가 있으면 빨간 점 강조
    if sel_sensor_id:
        matched = [xyz for sid, xyz in all_xyz if sid == sel_sensor_id]
        if matched:
            fig_conc = overlay_sensor(fig_conc, matched[0], selected=True)
            title = f"{selected_conc} · 센서 {sel_sensor_id} 선택됨"
            return fig_conc, title, False, False

    # 선택된 센서가 없으면 “편집/삭제” 버튼 비활성화
    return fig_conc, title, True, True


# ───────────────────── ⑥ 추가/삭제/수정 콜백 등 나머지는 기존 로직 유지 ─────────────────────

# ───────────────────── ⑦ 추가 모달 토글 ─────────────────────
@callback(
    Output("modal-sensor-add", "is_open"),
    Input("btn-sensor-add",   "n_clicks"),
    Input("add-sensor-close", "n_clicks"),
    Input("add-sensor-save",  "n_clicks"),
    State("modal-sensor-add","is_open"),
    prevent_initial_call=True,
)
def toggle_add_modal(b_add, b_close, b_save, is_open):
    trig = ctx.triggered_id
    if trig == "btn-sensor-add":
        return True
    if trig in ("add-sensor-close", "add-sensor-save"):
        return False
    return is_open


# ───────────────────── ⑧ 추가 미리보기 ─────────────────────
@callback(
    Output("add-sensor-preview", "figure"),
    Output("add-sensor-alert",   "children"),
    Output("add-sensor-alert",   "is_open"),
    Input("add-sensor-build", "n_clicks"),
    State("ddl-concrete",     "value"),
    State("add-sensor-id",    "value"),
    State("add-sensor-coords","value"),
    prevent_initial_call=True,
)
def add_sensor_preview(_, conc_id, sensor_id, coords_txt):
    if not conc_id:
        return dash.no_update, "콘크리트를 먼저 선택하세요", True
    if not sensor_id:
        return dash.no_update, "센서 ID를 입력하세요", True
    if not coords_txt:
        return dash.no_update, "좌표를 입력하세요 (예: [1,1,0])", True

    # 콘크리트 뷰 생성
    try:
        conc_row = api_concrete.load_all().query("concrete_id == @conc_id").iloc[0]
        conc_dims = ast.literal_eval(conc_row["dims"])
        conc_nodes, conc_h = conc_dims["nodes"], conc_dims["h"]
        fig_conc = make_concrete_fig(conc_nodes, conc_h)
    except Exception:
        return go.Figure(), "콘크리트 정보를 불러올 수 없음", True

    # 좌표 파싱
    try:
        xyz = ast.literal_eval(coords_txt)
        if not (isinstance(xyz, (list, tuple)) and len(xyz) == 3):
            raise ValueError
        xyz = [float(x) for x in xyz]
    except Exception:
        return dash.no_update, "좌표 형식이 잘못되었습니다 (예: [1,1,0])", True

    # 센서 파란 점으로 미리보기
    fig_conc = overlay_sensor(fig_conc, xyz, selected=False)
    return fig_conc, "", False


# ───────────────────── ⑨ 추가 저장 ────────────────────────
@callback(
    Output("tbl-sensor", "data_timestamp", allow_duplicate=True),
    Output("add-sensor-alert", "children", allow_duplicate=True),
    Output("add-sensor-alert", "color",    allow_duplicate=True),
    Output("add-sensor-alert", "is_open",  allow_duplicate=True),
    Input("add-sensor-save", "n_clicks"),
    State("ddl-concrete",     "value"),
    State("add-sensor-id",    "value"),
    State("add-sensor-coords","value"),
    prevent_initial_call=True,
)
def add_sensor_save(_, conc_id, sensor_id, coords_txt):
    if not (conc_id and sensor_id):
        return dash.no_update, "콘크리트 및 센서 ID를 입력하세요", "danger", True
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

    # 센서 추가
    try:
        api_sensor.add_sensor(conc_id, sensor_id, {"nodes": xyz})
    except Exception as e:
        return dash.no_update, f"추가 실패: {e}", "danger", True

    return pd.Timestamp.utcnow().value, "추가 완료", "success", True


# ───────────────────── ⑩ 삭제 컨펌 토글 ───────────────────
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
    Output("add-sensor-alert", "children", allow_duplicate=True),
    Output("add-sensor-alert", "color", allow_duplicate=True),
    Output("add-sensor-alert", "is_open", allow_duplicate=True),
    Input("confirm-del-sensor", "submit_n_clicks"),
    State("tbl-sensor", "selected_rows"), State("tbl-sensor", "data"),
    State("ddl-concrete", "value"),
    prevent_initial_call=True,
)
def delete_sensor_confirm(_click, sel, tbl_data, conc_id):
    if not (sel and conc_id):
        raise PreventUpdate

    row = pd.DataFrame(tbl_data).iloc[sel[0]]
    sensor_id = row["sensor_id"]
    try:
        api_sensor.delete_sensor(conc_id, sensor_id)
    except Exception as e:
        return dash.no_update, f"삭제 실패: {e}", "danger", True

    return pd.Timestamp.utcnow().value, f"{sensor_id} 삭제 완료", "warning", True


# ───────────────────── ⑪ 수정 모달 토글 ───────────────────
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
def toggle_edit_modal(b_open, b_close, b_save, sel, tbl_data, conc_id):
    trig = ctx.triggered_id
    if trig == "btn-sensor-edit" and sel and conc_id:
        row = pd.DataFrame(tbl_data).iloc[sel[0]]
        return True, conc_id, row["sensor_id"]
    return False, dash.no_update, dash.no_update


# ───────────────────── ⑫ 수정 모달 필드 채우기 ───────────────
@callback(
    Output("edit-sensor-id", "value"),
    Output("edit-sensor-coords", "value"),
    Output("edit-sensor-preview","figure"),
    Output("edit-sensor-alert","children"),
    Output("edit-sensor-alert","is_open"),
    Input("modal-sensor-edit","is_open"),
    State("edit-sensor-concrete-id","data"), State("edit-sensor-id-store","data"),
)
def fill_edit_sensor(opened, conc_id, sensor_id):
    if not opened or not (conc_id and sensor_id):
        raise PreventUpdate

    # 1) 콘크리트 정보 로드
    try:
        conc_row = api_concrete.load_all().query("concrete_id == @conc_id").iloc[0]
        conc_dims = ast.literal_eval(conc_row["dims"])
        conc_nodes, conc_h = conc_dims["nodes"], conc_dims["h"]
        fig_conc = make_concrete_fig(conc_nodes, conc_h)
    except Exception:
        fig_conc = go.Figure()

    # 2) 센서 정보 로드
    df_sensor_full = api_sensor.load_all_sensors()
    df_row = df_sensor_full[
        (df_sensor_full["concrete_id"] == conc_id) &
        (df_sensor_full["sensor_id"]    == sensor_id)
    ]
    if df_row.empty:
        return sensor_id, "", fig_conc, "", False

    try:
        dims_sensor = ast.literal_eval(df_row.iloc[0]["dims"])
        x, y, z = dims_sensor["nodes"]
        coords_txt = f"[{x}, {y}, {z}]"
        fig_all = overlay_sensor(fig_conc, [x, y, z], selected=True)
    except Exception:
        coords_txt = ""
        fig_all = fig_conc

    return sensor_id, coords_txt, fig_all, "", False


# ───────────────────── ⑬ 수정 미리보기 ─────────────────────
@callback(
    Output("edit-sensor-preview","figure",    allow_duplicate=True),
    Output("edit-sensor-alert",   "children",  allow_duplicate=True),
    Output("edit-sensor-alert",   "is_open",   allow_duplicate=True),
    Input("edit-sensor-build","n_clicks"),
    State("edit-sensor-coords","value"),
    State("edit-sensor-concrete-id","data"),
    State("edit-sensor-id-store","data"),
    prevent_initial_call=True,
)
def edit_sensor_preview(_, coords_txt, conc_id, sensor_id):
    # 1) 콘크리트 피겨 로드
    try:
        conc_row = api_concrete.load_all().query("concrete_id == @conc_id").iloc[0]
        conc_dims = ast.literal_eval(conc_row["dims"])
        conc_nodes, conc_h = conc_dims["nodes"], conc_dims["h"]
        fig_conc = make_concrete_fig(conc_nodes, conc_h)
    except Exception:
        return dash.no_update, "콘크리트 정보를 불러올 수 없음", True

    # 2) 좌표 파싱
    if not coords_txt:
        return dash.no_update, "좌표를 입력하세요 (예: [1,1,0])", True

    try:
        xyz = ast.literal_eval(coords_txt)
        if not (isinstance(xyz, (list, tuple)) and len(xyz) == 3):
            raise ValueError
        xyz = [float(x) for x in xyz]
    except Exception:
        return dash.no_update, "좌표 형식이 잘못되었습니다 (예: [1,1,0])", True

    # 3) 파란 점으로 모든 센서 표시 후, 빨간 점으로 해당 센서 강조
    fig_conc = make_concrete_fig(conc_nodes, conc_h)
    df_all = api_sensor.load_all_sensors()
    df_this = df_all[df_all["concrete_id"] == conc_id]
    for _, row in df_this.iterrows():
        try:
            dims = ast.literal_eval(row["dims"])
            coord = dims.get("nodes", [])
            fig_conc = overlay_sensor(fig_conc, coord, selected=False)
        except Exception:
            continue

    fig_conc = overlay_sensor(fig_conc, xyz, selected=True)
    return fig_conc, "", False


# ───────────────────── ⑭ 수정 저장 ────────────────────────
@callback(
    Output("tbl-sensor","data_timestamp", allow_duplicate=True),
    Output("edit-sensor-alert","children",    allow_duplicate=True),
    Output("edit-sensor-alert","color",       allow_duplicate=True),
    Output("edit-sensor-alert","is_open",     allow_duplicate=True),
    Input("edit-sensor-save","n_clicks"),
    State("edit-sensor-concrete-id","data"), State("edit-sensor-id-store","data"),
    State("edit-sensor-coords","value"),
    prevent_initial_call=True,
)
def edit_sensor_save(_, conc_id, sensor_id, coords_txt):
    if not (conc_id and sensor_id):
        return dash.no_update, "데이터 로드 실패", "danger", True
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

    try:
        api_sensor.update_sensor(conc_id, sensor_id, {"nodes": xyz})
    except Exception as e:
        return dash.no_update, f"수정 실패: {e}", "danger", True

    return pd.Timestamp.utcnow().value, f"{sensor_id} 수정 완료", "success", True
