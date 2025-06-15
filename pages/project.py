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
                                max=5,
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
    Output("time-slider", "min"),
    Output("time-slider", "max"),
    Output("time-slider", "value"),
    Output("time-slider", "marks"),
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
    Output("time-slider", "min", allow_duplicate=True),
    Output("time-slider", "max", allow_duplicate=True),
    Output("time-slider", "value", allow_duplicate=True),
    Output("time-slider", "marks", allow_duplicate=True),
    Output("current-time-store", "data", allow_duplicate=True),
    Input("tbl-concrete", "selected_rows"),
    State("tbl-concrete", "data"),
    prevent_initial_call=True,
)
def on_concrete_select(selected_rows, tbl_data):
    if not selected_rows:
        return True, True, 0, 5, 0, {}, None
    
    # 선택된 콘크리트의 activate 상태 확인
    row = pd.DataFrame(tbl_data).iloc[selected_rows[0]]
    is_active = row["activate"] == "활성"
    concrete_pk = row["concrete_pk"]
    
    # inp 파일 목록 조회
    inp_dir = f"inp/{concrete_pk}"
    if not os.path.exists(inp_dir):
        return False, not is_active, 0, 5, 0, {}, None
    
    # inp 파일 시간 목록 생성
    inp_files = sorted(glob.glob(f"{inp_dir}/*.inp"))
    if not inp_files:
        return False, not is_active, 0, 5, 0, {}, None
    
    # 시간 범위 계산
    times = []
    for f in inp_files:
        try:
            time_str = os.path.basename(f).split(".")[0]
            dt = datetime.strptime(time_str, "%Y%m%d%H")
            times.append(dt)
        except:
            continue
    
    if not times:
        return False, not is_active, 0, 5, 0, {}, None
    
    # 슬라이더 마크 생성
    marks = {}
    for i, t in enumerate(times):
        if i % 6 == 0:  # 6시간 간격으로 마크 표시
            marks[i] = t.strftime("%m/%d %H:00")
    
    return False, not is_active, 0, len(times)-1, 0, marks, times[0].strftime("%Y%m%d%H")

# ───────────────────── ④ 시간 슬라이더 콜백 ─────────────────────
@callback(
    Output("time-slider", "marks"),
    Output("time-slider", "max"),
    Output("current-time-store", "data", allow_duplicate=True),
    Input("tbl-concrete", "selected_rows"),
    State("tbl-concrete", "data"),
    prevent_initial_call=True,
)
def update_time_slider(selected_rows, tbl_data):
    if not selected_rows:
        raise PreventUpdate
    row = pd.DataFrame(tbl_data).iloc[selected_rows[0]]
    concrete_pk = row["concrete_pk"]
    inp_dir = f"inp/{concrete_pk}"
    if not os.path.exists(inp_dir):
        raise PreventUpdate
    inp_files = sorted(glob.glob(f"{inp_dir}/*.inp"))
    if not inp_files:
        raise PreventUpdate
    # 6등분
    n = len(inp_files)
    idxs = [round(i * (n-1)/5) for i in range(6)]
    marks = {i: os.path.basename(inp_files[idxs[i]]).split(".")[0] for i in range(6)}
    return marks, 5, 0

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
    if not inp_files or time_idx >= len(inp_files):
        raise PreventUpdate
    current_file = inp_files[round(time_idx * (len(inp_files)-1)/5)]
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
    # 컬러바 범위 통일
    tmin, tmax = float(np.nanmin(temps)), float(np.nanmax(temps))
    # 3D 뷰 (컬러바 1개)
    fig_3d = go.Figure()
    fig_3d.add_trace(go.Scatter3d(
        x=x_coords, y=y_coords, z=z_coords,
        mode='markers',
        marker=dict(size=3, color=temps, colorscale='RdBu', cmin=tmin, cmax=tmax, showscale=True, colorbar=dict(title='Temperature (°C)')),
        name='Nodes'))
    fig_3d.update_layout(title=f"시간: {current_time}", scene=dict(aspectmode='data'), margin=dict(l=0, r=0, b=0, t=30), showlegend=False)
    # 단면 위치 (클릭 없으면 중앙)
    x0 = float(section_coord['x']) if section_coord and 'x' in section_coord else float(np.median(x_coords))
    y0 = float(section_coord['y']) if section_coord and 'y' in section_coord else float(np.median(y_coords))
    z0 = float(section_coord['z']) if section_coord and 'z' in section_coord else float(np.median(z_coords))
    # X, Y, Z 단면도 (0.1m 간격, ±0.05 tolerance)
    tol = 0.05
    # X 단면 (x ≈ x0)
    mask_x = np.abs(x_coords - x0) < tol
    fig_x = go.Figure(go.Heatmap(
        x=y_coords[mask_x], y=z_coords[mask_x], z=temps[mask_x],
        colorscale='RdBu', zmin=tmin, zmax=tmax, colorbar=None, zsmooth='best'))
    fig_x.update_layout(title=f"X={x0:.2f}m 단면", xaxis_title="Y (m)", yaxis_title="Z (m)", margin=dict(l=0, r=0, b=0, t=30))
    # Y 단면 (y ≈ y0)
    mask_y = np.abs(y_coords - y0) < tol
    fig_y = go.Figure(go.Heatmap(
        x=x_coords[mask_y], y=z_coords[mask_y], z=temps[mask_y],
        colorscale='RdBu', zmin=tmin, zmax=tmax, colorbar=None, zsmooth='best'))
    fig_y.update_layout(title=f"Y={y0:.2f}m 단면", xaxis_title="X (m)", yaxis_title="Z (m)", margin=dict(l=0, r=0, b=0, t=30))
    # Z 단면 (z ≈ z0)
    mask_z = np.abs(z_coords - z0) < tol
    fig_z = go.Figure(go.Heatmap(
        x=x_coords[mask_z], y=y_coords[mask_z], z=temps[mask_z],
        colorscale='RdBu', zmin=tmin, zmax=tmax, colorbar=None, zsmooth='best'))
    fig_z.update_layout(title=f"Z={z0:.2f}m 단면", xaxis_title="X (m)", yaxis_title="Y (m)", margin=dict(l=0, r=0, b=0, t=30))
    return fig_3d, fig_x, fig_y, fig_z, current_time

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
