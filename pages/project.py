#!/usr/bin/env python3
# pages/project.py
# 현재 파일: pages/project.py
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
import json

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
                        # 현재 파일명 표시
                        html.H6(id="current-file-title", className="mb-2"),
                        # 3D 뷰와 단면도를 나란히 배치
                        dbc.Row([
                            # 3D 뷰
                            dbc.Col([
                                dcc.Graph(
                                    id="viewer-3d",
                                    style={"height": "80vh"},
                                    config={"scrollZoom": True},
                                ),
                            ], md=12),
                            # 단면도는 숨김 처리(필요시 완전히 제거 가능)
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
            "dims": row["dims"],
            "activate": "활성" if row["activate"] == 1 else "비활성",
        })

    # 3) 테이블 컬럼 정의
    columns = [
        {"name": "이름", "id": "name"},
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
    Output("current-time-store", "data", allow_duplicate=True),
    Output("current-file-title", "children"),
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

    # 전체 파일의 온도 min/max 계산
    all_temps = []
    for f in inp_files:
        with open(f, 'r') as file:
            lines = file.readlines()
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
                    try:
                        temp = float(parts[1])
                        all_temps.append(temp)
                    except:
                        continue
    if all_temps:
        tmin, tmax = float(np.nanmin(all_temps)), float(np.nanmax(all_temps))
    else:
        tmin, tmax = 0, 100

    # 시간 슬라이더: 1시간 단위로 표시
    current_file = inp_files[time_idx]
    current_time = os.path.basename(current_file).split(".")[0]
    
    # 현재 파일의 온도 통계 계산
    current_temps = []
    with open(current_file, 'r') as f:
        lines = f.readlines()
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
                try:
                    temp = float(parts[1])
                    current_temps.append(temp)
                except:
                    continue
    
    if current_temps:
        current_min = float(np.nanmin(current_temps))
        current_max = float(np.nanmax(current_temps))
        current_avg = float(np.nanmean(current_temps))
        current_file_title = f"현재 파일: {current_time} (최저: {current_min:.1f}°C, 최고: {current_max:.1f}°C, 평균: {current_avg:.1f}°C)"
    else:
        current_file_title = f"현재 파일: {current_time}"

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

    # 콘크리트 dims 파싱 (꼭짓점, 높이)
    try:
        dims = ast.literal_eval(row["dims"]) if isinstance(row["dims"], str) else row["dims"]
        poly_nodes = np.array(dims["nodes"])  # (n, 2)
        poly_h = float(dims["h"])
    except Exception:
        poly_nodes = None
        poly_h = None

    # 1. 3D 볼륨 렌더링 (노드 기반, 원래 방식)
    coords = np.array([[x, y, z] for x, y, z in zip(x_coords, y_coords, z_coords)])
    temps = np.array(temps)
    fig_3d = go.Figure(data=go.Volume(
        x=coords[:,0], y=coords[:,1], z=coords[:,2], value=temps,
        opacity=0.1, surface_count=15, 
        colorscale=[[0, 'blue'], [1, 'red']],
        colorbar=dict(title='Temperature (°C)', thickness=10),
        cmin=np.nanmin(temps), cmax=np.nanmax(temps),
        showscale=True
    ))
    # 모서리 강조(기존 코드)
    if poly_nodes is not None and poly_h is not None:
        n = len(poly_nodes)
        x0, y0 = poly_nodes[:,0], poly_nodes[:,1]
        z0 = np.zeros(n)
        x1, y1 = x0, y0
        z1 = np.full(n, poly_h)
        fig_3d.add_trace(go.Scatter3d(
            x=np.append(x0, x0[0]), y=np.append(y0, y0[0]), z=np.append(z0, z0[0]),
            mode='lines', line=dict(width=2, color='black'), showlegend=False, hoverinfo='skip'))
        fig_3d.add_trace(go.Scatter3d(
            x=np.append(x1, x1[0]), y=np.append(y1, y1[0]), z=np.append(z1, z1[0]),
            mode='lines', line=dict(width=2, color='black'), showlegend=False, hoverinfo='skip'))
        for i in range(n):
            fig_3d.add_trace(go.Scatter3d(
                x=[x0[i], x1[i]], y=[y0[i], y1[i]], z=[z0[i], z1[i]],
                mode='lines', line=dict(width=2, color='black'), showlegend=False, hoverinfo='skip'))
    # 센서 위치 표시
    try:
        df_sensors = api_db.get_sensors_data(concrete_pk=concrete_pk)
        if not df_sensors.empty:
            xs, ys, zs, names = [], [], [], []
            for _, srow in df_sensors.iterrows():
                try:
                    dims = json.loads(srow['dims'])
                    xs.append(dims['nodes'][0])
                    ys.append(dims['nodes'][1])
                    zs.append(dims['nodes'][2])
                    names.append(srow['name'])
                except Exception as e:
                    print('센서 파싱 오류:', e)
            fig_3d.add_trace(go.Scatter3d(
                x=xs, y=ys, z=zs,
                mode='markers',
                marker=dict(size=4, color='red', symbol='circle'),
                text=names,
                hoverinfo='text',
                name='센서',
                showlegend=False
            ))
    except Exception as e:
        print('센서 표시 오류:', e)
    return fig_3d, current_time, current_file_title

# 시간 슬라이더 마크: 날짜의 00시만 표시, 텍스트는 MM/DD 형식
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
    
    # 날짜의 00시만 마크 표시, 텍스트는 MM/DD
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
    if trigger_id == "tbl-concrete":
        value = max_idx
    else:
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
