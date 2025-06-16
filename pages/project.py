#!/usr/bin/env python3
# pages/project.py
"""Dash 페이지: 프로젝트 및 콘크리트 관리

* 왼쪽에서 프로젝트를 선택 → 해당 프로젝트의 콘크리트 리스트 표시
* 콘크리트 분석 시작/삭제 기능
* 3D 히트맵 뷰어로 시간별 온도 분포 확인
"""

from __future__ import annotations

import os
import glob
import shutil
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime, timedelta
import dash
from dash import (
    html, dcc, Input, Output, State,
    dash_table, register_page, callback
)
import dash_bootstrap_components as dbc
from dash.exceptions import PreventUpdate
from scipy.interpolate import griddata
import ast

import api_db

register_page(__name__, path="/project")

# ────────────────────────────── 레이아웃 ────────────────────────────
layout = dbc.Container(
    fluid=True,
    children=[
        # ── (★) 삭제 컨펌 다이얼로그
        dcc.ConfirmDialog(
            id="confirm-del-concrete",
            message="선택한 콘크리트를 정말 삭제하시겠습니까?"
        ),

        # ── (★) Alert 메시지
        dbc.Alert(
            id="project-alert",
            is_open=False,
            duration=3000,
            color="danger",
        ),

        # ── (★) 현재 시간 정보를 저장할 Store
        dcc.Store(id="current-time-store", data=None),

        # ── (★) 클릭 좌표 저장
        dcc.Store(id="section-coord-store", data=None),

        # 상단: 프로젝트 선택 → 콘크리트 테이블 + 버튼
        dbc.Row(
            [
                dbc.Col(
                    [
                        html.H6("프로젝트 선택"),
                        dcc.Dropdown(
                            id="ddl-project",
                            placeholder="프로젝트 선택",
                            clearable=False,
                        ),
                        html.H6("콘크리트 리스트", className="mt-3"),
                        dash_table.DataTable(
                            id="tbl-concrete",
                            page_size=10,
                            row_selectable="single",
                            style_table={"overflowY": "auto", "height": "45vh"},
                            style_cell={"whiteSpace": "nowrap", "textAlign": "center"},
                            style_header={"backgroundColor": "#f1f3f5", "fontWeight": 600},
                        ),
                        dbc.ButtonGroup(
                            [
                                dbc.Button("분석 시작", id="btn-concrete-analyze", color="success", className="mt-2", disabled=True),
                                dbc.Button("삭제", id="btn-concrete-del", color="danger", className="mt-2", disabled=True),
                            ],
                            size="sm",
                            vertical=True,
                            className="w-100",
                        ),
                    ],
                    md=3,
                ),
                dbc.Col(
                    [
                        html.H6(id="concrete-title", className="mb-2"),
                        # 3D 뷰와 단면도를 나란히 배치
                        dbc.Row([
                            # 3D 뷰
                            dbc.Col([
                                dcc.Graph(
                                    id="viewer-3d",
                                    style={"height": "60vh"},
                                    config={"scrollZoom": True},
                                ),
                            ], md=7),
                            # 단면도
                            dbc.Col([
                                html.Div([
                                    dcc.Graph(id="viewer-section-x", style={"height": "19vh"}),
                                    dcc.Graph(id="viewer-section-y", style={"height": "19vh"}),
                                    dcc.Graph(id="viewer-section-z", style={"height": "19vh"}),
                                ]),
                            ], md=5),
                        ]),
                        # 시간 슬라이더
                        html.Div([
                            html.Label("시간", className="form-label"),
                            dcc.Slider(
                                id="time-slider",
                                min=0,
                                step=1,
                                value=0,
                                marks={},
                                tooltip={"placement": "bottom", "always_visible": True},
                            ),
                        ], className="mt-3"),
                    ],
                    md=9,
                ),
            ],
            className="g-3",
        ),
    ],
)

# ───────────────────── ① 프로젝트 목록 초기화 ─────────────────────
@callback(
    Output("ddl-project", "options"),
    Output("ddl-project", "value"),
    Input("ddl-project", "value"),
    prevent_initial_call=False,
)
def init_dropdown(selected_value):
    """
    페이지 로드 또는 값이 None일 때 프로젝트 목록을 Dropdown 옵션으로 설정.
    """
    df_proj = api_db.get_project_data()
    options = [
        {"label": f"{row['name']}", "value": row["project_pk"]}
        for _, row in df_proj.iterrows()
    ]
    if not options:
        return [], None

    # 초기 로드 시(= selected_value가 None일 때)만 첫 번째 옵션을 기본값으로 지정
    if selected_value is None:
        return options, options[0]["value"]
    # 사용자가 이미 선택한 값이 있으면 그대로 유지
    return options, selected_value

# ───────────────────── ② 프로젝트 선택 콜백 ─────────────────────
@callback(
    Output("tbl-concrete", "data"),
    Output("tbl-concrete", "columns"),
    Output("tbl-concrete", "selected_rows"),
    Output("btn-concrete-del", "disabled"),
    Output("btn-concrete-analyze", "disabled"),
    Output("concrete-title", "children"),
    Output("time-slider", "min", allow_duplicate=True),
    Output("time-slider", "max", allow_duplicate=True),
    Output("time-slider", "value", allow_duplicate=True),
    Output("time-slider", "marks", allow_duplicate=True),
    Output("current-time-store", "data"),
    Input("ddl-project", "value"),
    prevent_initial_call=True,
)
def on_project_change(selected_proj):
    if not selected_proj:
        return [], [], [], True, True, "", 0, 5, 0, {}, None

    # 1) 프로젝트 정보 로드
    try:
        proj_row = api_db.get_project_data(project_pk=selected_proj).iloc[0]
        proj_name = proj_row["name"]
    except Exception:
        return [], [], [], True, True, "프로젝트 정보를 불러올 수 없음", 0, 5, 0, {}, None

    # 2) 콘크리트 데이터 로드
    df_conc = api_db.get_concrete_data(project_pk=selected_proj)
    table_data = []
    for _, row in df_conc.iterrows():
        try:
            dims = eval(row["dims"])
            nodes = dims["nodes"]
            h = dims["h"]
            shape_info = f"{len(nodes)}각형 (높이: {h:.2f}m)"
        except Exception:
            shape_info = "파싱 오류"
        
        table_data.append({
            "concrete_pk": row["concrete_pk"],
            "name": row["name"],
            "shape": shape_info,
            "activate": "활성" if row["activate"] == 1 else "비활성",
        })

    # 3) 테이블 컬럼 정의
    columns = [
        {"name": "콘크리트 ID", "id": "concrete_pk"},
        {"name": "이름", "id": "name"},
        {"name": "형상", "id": "shape"},
        {"name": "상태", "id": "activate"},
    ]

    title = f"{proj_name} · 콘크리트 전체"
    return table_data, columns, [], True, True, title, 0, 5, 0, {}, None

# ───────────────────── ③ 콘크리트 선택 콜백 ─────────────────────
@callback(
    Output("btn-concrete-del", "disabled", allow_duplicate=True),
    Output("btn-concrete-analyze", "disabled", allow_duplicate=True),
    Input("tbl-concrete", "selected_rows"),
    State("tbl-concrete", "data"),
    prevent_initial_call=True,
)
def on_concrete_select(selected_rows, tbl_data):
    if not selected_rows:
        return True, True
    row = pd.DataFrame(tbl_data).iloc[selected_rows[0]]
    is_active = row["activate"] == "활성"
    return False, not is_active

# ───────────────────── 3D 뷰 클릭 → 단면 위치 저장 ─────────────────────
@callback(
    Output("section-coord-store", "data"),
    Input("viewer-3d", "clickData"),
    prevent_initial_call=True,
)
def store_section_coord(clickData):
    if not clickData or "points" not in clickData:
        raise PreventUpdate
    pt = clickData["points"][0]
    return {"x": pt["x"], "y": pt["y"], "z": pt["z"]}

# ───────────────────── 3D/단면도 업데이트 콜백 ─────────────────────
@callback(
    Output("viewer-3d", "figure"),
    Output("viewer-section-x", "figure"),
    Output("viewer-section-y", "figure"),
    Output("viewer-section-z", "figure"),
    Output("current-time-store", "data", allow_duplicate=True),
    Input("time-slider", "value"),
    Input("section-coord-store", "data"),
    State("tbl-concrete", "selected_rows"),
    State("tbl-concrete", "data"),
    State("current-time-store", "data"),
    prevent_initial_call=True,
)
def update_heatmap(time_idx, section_coord, selected_rows, tbl_data, current_time):
    if not selected_rows:
        raise PreventUpdate
    row = pd.DataFrame(tbl_data).iloc[selected_rows[0]]
    concrete_pk = row["concrete_pk"]
    inp_dir = f"inp/{concrete_pk}"
    inp_files = sorted(glob.glob(f"{inp_dir}/*.inp"))
    if not inp_files:
        raise PreventUpdate

    # 시간 슬라이더: 처음/중간/끝만 표시
    N = len(inp_files)
    if time_idx == 0:
        file_idx = 0
    elif time_idx == 1:
        file_idx = N // 2
    else:
        file_idx = N - 1
    current_file = inp_files[file_idx]
    current_time = os.path.basename(current_file).split(".")[0]

    # inp 파일 파싱 (노드, 온도)
    with open(current_file, 'r') as f:
        lines = f.readlines()
    nodes = {}
    node_section = False
    for line in lines:
        if line.startswith('*NODE'):
            node_section = True
            continue
        elif line.startswith('*'):
            node_section = False
            continue
        if node_section and ',' in line:
            parts = line.strip().split(',')
            if len(parts) >= 4:
                node_id = int(parts[0])
                x = float(parts[1])
                y = float(parts[2])
                z = float(parts[3])
                nodes[node_id] = {'x': x, 'y': y, 'z': z}
    temperatures = {}
    temp_section = False
    for line in lines:
        if line.startswith('*TEMPERATURE'):
            temp_section = True
            continue
        elif line.startswith('*'):
            temp_section = False
            continue
        if temp_section and ',' in line:
            parts = line.strip().split(',')
            if len(parts) >= 2:
                node_id = int(parts[0])
                temp = float(parts[1])
                temperatures[node_id] = temp
    x_coords = np.array([n['x'] for n in nodes.values() if n and temperatures.get(list(nodes.keys())[list(nodes.values()).index(n)], None) is not None])
    y_coords = np.array([n['y'] for n in nodes.values() if n and temperatures.get(list(nodes.keys())[list(nodes.values()).index(n)], None) is not None])
    z_coords = np.array([n['z'] for n in nodes.values() if n and temperatures.get(list(nodes.keys())[list(nodes.values()).index(n)], None) is not None])
    temps = np.array([temperatures[k] for k in nodes.keys() if k in temperatures])
    tmin, tmax = float(np.nanmin(temps)), float(np.nanmax(temps))

    # 콘크리트 dims 파싱 (꼭짓점, 높이)
    try:
        dims = ast.literal_eval(row["dims"]) if isinstance(row["dims"], str) else row["dims"]
        poly_nodes = np.array(dims["nodes"])
        poly_h = float(dims["h"])
    except Exception:
        poly_nodes = None
        poly_h = None

    # 1. 3D 볼륨 렌더링
    coords = np.array([[x, y, z] for x, y, z in zip(x_coords, y_coords, z_coords)])
    temps = np.array(temps)
    fig_3d = go.Figure(data=go.Volume(
        x=coords[:,0], y=coords[:,1], z=coords[:,2], value=temps,
        opacity=0.2, surface_count=15, colorscale='RdBu',
        colorbar=dict(title='Temperature (°C)')
    ))

    # 2. 콘크리트 모서리 강조 (꼭짓점/천장/세로 엣지만)
    if poly_nodes is not None and poly_h is not None:
        n = len(poly_nodes)
        x0, y0, z0 = poly_nodes[:,0], poly_nodes[:,1], np.zeros(n)
        x1, y1, z1 = x0, y0, np.full(n, poly_h)
        # 바닥 외곽선
        fig_3d.add_trace(go.Scatter3d(
            x=np.append(x0, x0[0]), y=np.append(y0, y0[0]), z=np.append(z0, z0[0]),
            mode='lines', line=dict(width=8, color='black'), name='바닥', hoverinfo='skip'))
        # 천장 외곽선
        fig_3d.add_trace(go.Scatter3d(
            x=np.append(x1, x1[0]), y=np.append(y1, y1[0]), z=np.append(z1, z1[0]),
            mode='lines', line=dict(width=8, color='black'), name='천장', hoverinfo='skip'))
        # 세로 엣지
        for i in range(n):
            fig_3d.add_trace(go.Scatter3d(
                x=[x0[i], x1[i]], y=[y0[i], y1[i]], z=[z0[i], z1[i]],
                mode='lines', line=dict(width=8, color='black'), name='세로', hoverinfo='skip'))

    # 3. 단면 위치: 중앙값 기본, 클릭 시 해당 위치
    x0 = float(section_coord['x']) if section_coord and 'x' in section_coord else float(np.median(x_coords))
    y0 = float(section_coord['y']) if section_coord and 'y' in section_coord else float(np.median(y_coords))
    z0 = float(section_coord['z']) if section_coord and 'z' in section_coord else float(np.median(z_coords))

    # 4. 3D 뷰에 단면 위치 표시 (빨간 평면/선)
    if poly_nodes is not None and poly_h is not None:
        # X 단면 (빨간 YZ 평면)
        fig_3d.add_trace(go.Scatter3d(
            x=[x0]*5, y=[poly_nodes[:,1].min(), poly_nodes[:,1].max(), poly_nodes[:,1].max(), poly_nodes[:,1].min(), poly_nodes[:,1].min()],
            z=[0, 0, poly_h, poly_h, 0],
            mode="lines", line=dict(color="red", width=8), name="Section-X", hoverinfo="skip"
        ))
        # Y 단면 (파란 XZ 평면)
        fig_3d.add_trace(go.Scatter3d(
            x=[poly_nodes[:,0].min(), poly_nodes[:,0].max(), poly_nodes[:,0].max(), poly_nodes[:,0].min(), poly_nodes[:,0].min()],
            y=[y0]*5,
            z=[0, 0, poly_h, poly_h, 0],
            mode="lines", line=dict(color="blue", width=8), name="Section-Y", hoverinfo="skip"
        ))
        # Z 단면 (녹색 XY 평면)
        fig_3d.add_trace(go.Scatter3d(
            x=[poly_nodes[:,0].min(), poly_nodes[:,0].max(), poly_nodes[:,0].max(), poly_nodes[:,0].min(), poly_nodes[:,0].min()],
            y=[poly_nodes[:,1].min(), poly_nodes[:,1].min(), poly_nodes[:,1].max(), poly_nodes[:,1].max(), poly_nodes[:,1].min()],
            z=[z0]*5,
            mode="lines", line=dict(color="green", width=8), name="Section-Z", hoverinfo="skip"
        ))

    # 이하 기존 단면도 코드 (중앙값/클릭 위치 반영)
    tol = 0.05
    # X 단면 (x ≈ x0)
    mask_x = np.abs(x_coords - x0) < tol
    if np.any(mask_x):
        yb, zb, tb = y_coords[mask_x], z_coords[mask_x], temps[mask_x]
        if len(yb) > 3:
            y_bins = np.linspace(yb.min(), yb.max(), 20)
            z_bins = np.linspace(zb.min(), zb.max(), 20)
            hist, yedges, zedges = np.histogram2d(yb, zb, bins=[y_bins, z_bins], weights=tb)
            counts, _, _ = np.histogram2d(yb, zb, bins=[y_bins, z_bins])
            with np.errstate(invalid='ignore'): hist = np.divide(hist, counts, where=counts>0)
            fig_x = go.Figure(go.Heatmap(
                x=y_bins, y=z_bins, z=hist.T, colorscale='RdBu', zmin=tmin, zmax=tmax, colorbar=None, zsmooth='best'))
        else:
            fig_x = go.Figure()
    else:
        fig_x = go.Figure()
    fig_x.update_layout(title=f"X={x0:.2f}m 단면", xaxis_title="Y (m)", yaxis_title="Z (m)", margin=dict(l=0, r=0, b=0, t=30))
    # Y 단면 (y ≈ y0)
    mask_y = np.abs(y_coords - y0) < tol
    if np.any(mask_y):
        xb, zb, tb = x_coords[mask_y], z_coords[mask_y], temps[mask_y]
        if len(xb) > 3:
            x_bins = np.linspace(xb.min(), xb.max(), 20)
            z_bins = np.linspace(zb.min(), zb.max(), 20)
            hist, xedges, zedges = np.histogram2d(xb, zb, bins=[x_bins, z_bins], weights=tb)
            counts, _, _ = np.histogram2d(xb, zb, bins=[x_bins, z_bins])
            with np.errstate(invalid='ignore'): hist = np.divide(hist, counts, where=counts>0)
            fig_y = go.Figure(go.Heatmap(
                x=x_bins, y=z_bins, z=hist.T, colorscale='RdBu', zmin=tmin, zmax=tmax, colorbar=None, zsmooth='best'))
        else:
            fig_y = go.Figure()
    else:
        fig_y = go.Figure()
    fig_y.update_layout(title=f"Y={y0:.2f}m 단면", xaxis_title="X (m)", yaxis_title="Z (m)", margin=dict(l=0, r=0, b=0, t=30))
    # Z 단면 (z ≈ z0)
    mask_z = np.abs(z_coords - z0) < tol
    if np.any(mask_z):
        xb, yb, tb = x_coords[mask_z], y_coords[mask_z], temps[mask_z]
        if len(xb) > 3:
            x_bins = np.linspace(xb.min(), xb.max(), 20)
            y_bins = np.linspace(yb.min(), yb.max(), 20)
            hist, xedges, yedges = np.histogram2d(xb, yb, bins=[x_bins, y_bins], weights=tb)
            counts, _, _ = np.histogram2d(xb, yb, bins=[x_bins, y_bins])
            with np.errstate(invalid='ignore'): hist = np.divide(hist, counts, where=counts>0)
            fig_z = go.Figure(go.Heatmap(
                x=x_bins, y=y_bins, z=hist.T, colorscale='RdBu', zmin=tmin, zmax=tmax, colorbar=None, zsmooth='best'))
        else:
            fig_z = go.Figure()
    else:
        fig_z = go.Figure()
    fig_z.update_layout(title=f"Z={z0:.2f}m 단면", xaxis_title="X (m)", yaxis_title="Y (m)", margin=dict(l=0, r=0, b=0, t=30))
    return fig_3d, fig_x, fig_y, fig_z, current_time

# 시간 슬라이더 마크: 처음/중간/끝만 표시
@callback(
    Output("time-slider", "min", allow_duplicate=True),
    Output("time-slider", "max", allow_duplicate=True),
    Output("time-slider", "marks", allow_duplicate=True),
    Output("time-slider", "value", allow_duplicate=True),
    Input("tbl-concrete", "selected_rows"),
    State("tbl-concrete", "data"),
    State("time-slider", "value"),
    prevent_initial_call=True,
)
def update_time_slider(selected_rows, tbl_data, current_value):
    if not selected_rows:
        return 0, 5, {}, 0
    
    # 콜백 컨텍스트 확인
    ctx = dash.callback_context
    trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
    
    row = pd.DataFrame(tbl_data).iloc[selected_rows[0]]
    concrete_pk = row["concrete_pk"]
    inp_dir = f"inp/{concrete_pk}"
    if not os.path.exists(inp_dir):
        return 0, 5, {}, 0
    inp_files = sorted(glob.glob(f"{inp_dir}/*.inp"))
    if not inp_files:
        return 0, 5, {}, 0
    
    # 시간 파싱
    times = []
    for f in inp_files:
        try:
            time_str = os.path.basename(f).split(".")[0]
            dt = datetime.strptime(time_str, "%Y%m%d%H")
            times.append(dt)
        except:
            continue
    if not times:
        return 0, 5, {}, 0
    
    # 1일(24시간) 간격으로 마크 표시
    marks = {}
    for i, t in enumerate(times):
        if t.hour == 0:
            marks[i] = t.strftime("%m/%d")
    # 첫번째와 마지막은 항상 표시
    if 0 not in marks:
        marks[0] = times[0].strftime("%m/%d")
    if (len(times)-1) not in marks:
        marks[len(times)-1] = times[-1].strftime("%m/%d")
    
    max_idx = len(times)-1
    
    # 콘크리트 선택 시 최근 시간으로 이동
    if trigger_id == "tbl-concrete":
        value = max_idx
    else:
        # value가 max보다 크면 max로 맞춤
        value = min(current_value if current_value is not None else 0, max_idx)
    
    return 0, max_idx, marks, value

# ───────────────────── ⑤ 분석 시작 콜백 ─────────────────────
@callback(
    Output("project-alert", "children"),
    Output("project-alert", "color"),
    Output("project-alert", "is_open"),
    Output("tbl-concrete", "data", allow_duplicate=True),
    Input("btn-concrete-analyze", "n_clicks"),
    State("tbl-concrete", "selected_rows"),
    State("tbl-concrete", "data"),
    prevent_initial_call=True,
)
def start_analysis(n_clicks, selected_rows, tbl_data):
    if not selected_rows:
        return "콘크리트를 선택하세요", "warning", True, dash.no_update

    row = pd.DataFrame(tbl_data).iloc[selected_rows[0]]
    concrete_pk = row["concrete_pk"]

    try:
        # activate를 0으로 변경
        api_db.update_concrete_data(concrete_pk=concrete_pk, activate=0)
        
        # 테이블 데이터 업데이트
        updated_data = tbl_data.copy()
        updated_data[selected_rows[0]]["activate"] = "비활성"
        
        return f"{concrete_pk} 분석이 시작되었습니다", "success", True, updated_data
    except Exception as e:
        return f"분석 시작 실패: {e}", "danger", True, dash.no_update

# ───────────────────── ⑥ 삭제 컨펌 토글 콜백 ───────────────────
@callback(
    Output("confirm-del-concrete", "displayed"),
    Input("btn-concrete-del", "n_clicks"),
    State("tbl-concrete", "selected_rows"),
    prevent_initial_call=True
)
def ask_delete_concrete(n, sel):
    return bool(n and sel)

# ───────────────────── ⑦ 삭제 실행 콜백 ─────────────────────
@callback(
    Output("project-alert", "children", allow_duplicate=True),
    Output("project-alert", "color", allow_duplicate=True),
    Output("project-alert", "is_open", allow_duplicate=True),
    Output("tbl-concrete", "data", allow_duplicate=True),
    Input("confirm-del-concrete", "submit_n_clicks"),
    State("tbl-concrete", "selected_rows"),
    State("tbl-concrete", "data"),
    prevent_initial_call=True,
)
def delete_concrete_confirm(_click, sel, tbl_data):
    if not sel:
        raise PreventUpdate

    row = pd.DataFrame(tbl_data).iloc[sel[0]]
    concrete_pk = row["concrete_pk"]

    try:
        # 1) /inp/{concrete_pk} 디렉토리 삭제
        inp_dir = f"inp/{concrete_pk}"
        if os.path.exists(inp_dir):
            shutil.rmtree(inp_dir)

        # 2) 센서 데이터 삭제
        df_sensors = api_db.get_sensors_data(concrete_pk=concrete_pk)
        for _, sensor in df_sensors.iterrows():
            api_db.delete_sensors_data(sensor["sensor_pk"])

        # 3) 콘크리트 삭제
        api_db.delete_concrete_data(concrete_pk)

        # 4) 테이블에서 해당 행 제거
        updated_data = tbl_data.copy()
        updated_data.pop(sel[0])

        return f"{concrete_pk} 삭제 완료", "success", True, updated_data
    except Exception as e:
        return f"삭제 실패: {e}", "danger", True, dash.no_update
