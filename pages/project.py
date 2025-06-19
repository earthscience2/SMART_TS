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
import auto_sensor
import auto_inp
import time
from urllib.parse import parse_qs, urlparse
from dash.dependencies import ALL
from dash import html
import dash_vtk

import api_db

register_page(__name__, path="/project")

# ────────────────────────────── 레이아웃 ────────────────────────────
layout = dbc.Container(
    fluid=True,
    children=[
        dcc.Location(id="project-url", refresh=False),
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
        dcc.Store(id="current-file-title-store", data=""),

        # ── (★) 클릭 좌표 저장
        dcc.Store(id="section-coord-store", data=None),

        # ── (★) 3D 뷰 정보 저장
        dcc.Store(id="viewer-3d-store", data=None),

        # section-colorbar 항상 포함 (처음엔 숨김)
        dcc.Graph(id='section-colorbar', style={'display':'none'}),

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
                    md=2,
                ),
                dbc.Col(
                    [
                        html.H6(id="concrete-title", className="mb-2"),
                        # 현재 파일명 표시
                        html.H6(id="current-file-title", className="mb-2"),
                        # 탭 메뉴
                        dbc.Tabs([
                            dbc.Tab(label="3D뷰", tab_id="tab-3d"),
                            dbc.Tab(label="단면도", tab_id="tab-section"),
                            dbc.Tab(label="온도 변화", tab_id="tab-temp"),
                            dbc.Tab(label="수치해석", tab_id="tab-analysis"),
                            dbc.Tab(label="inp 파일 목록", tab_id="tab-inp-files"),
                            dbc.Tab(label="frd 파일 업로드", tab_id="tab-frd-upload"),
                            dbc.Tab(label="vtk 파일 목록", tab_id="tab-vtk-files"),
                            dbc.Tab(label="vtp 파일 목록", tab_id="tab-vtp-files"),
                        ], id="tabs-main", active_tab="tab-3d"),
                        # 탭 콘텐츠
                        html.Div(id="tab-content", children=[
                            # 시간 슬라이더 (3D 뷰 위에 배치)
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
                            ], className="mb-3"),
                            dbc.Row([
                                dbc.Col([
                                    html.Div([
                                        dcc.Graph(
                                            id="viewer-3d",
                                            style={"height": "70vh", "border": "2px solid #dee2e6", "borderRadius": "8px"},
                                            config={"scrollZoom": True},
                                        ),
                                    ], style={"padding": "10px"}),
                                ], md=12),
                            ]),
                        ]),
                    ],
                    md=10,
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
    Input("project-url", "search"),
    prevent_initial_call=False,
)
def init_dropdown(selected_value, search):
    """
    페이지 로드 또는 값이 None일 때 프로젝트 목록을 Dropdown 옵션으로 설정.
    URL 쿼리스트링에 page=프로젝트PK가 있으면 해당 값을 우선 적용.
    """
    df_proj = api_db.get_project_data()
    options = [
        {"label": f"{row['name']}", "value": row["project_pk"]}
        for _, row in df_proj.iterrows()
    ]
    if not options:
        return [], None

    # 쿼리스트링에서 page 파라미터 추출
    project_from_url = None
    if search:
        qs = parse_qs(search.lstrip('?'))
        project_from_url = qs.get('page', [None])[0]
        if project_from_url and project_from_url in [opt['value'] for opt in options]:
            return options, project_from_url

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
    Output("concrete-title", "children", allow_duplicate=True),
    Input("tbl-concrete", "selected_rows"),
    State("tbl-concrete", "data"),
    prevent_initial_call=True,
)
def on_concrete_select(selected_rows, tbl_data):
    if not selected_rows:
        return True, True, ""
    
    row = pd.DataFrame(tbl_data).iloc[selected_rows[0]]
    is_active = row["activate"] == "활성"
    
    # 안내 메시지 생성
    if is_active:
        title = "⚠️ 분석을 시작하려면 왼쪽의 '분석 시작' 버튼을 클릭하세요."
    else:
        # 비활성 상태일 때 데이터 존재 여부 확인
        concrete_pk = row["concrete_pk"]
        inp_dir = f"inp/{concrete_pk}"
        inp_files = glob.glob(f"{inp_dir}/*.inp")
        if not inp_files:
            title = "⏳ 아직 수집된 데이터가 없습니다. 잠시 후 다시 확인해주세요."
        else:
            title = ""
            
    return False, not is_active, title

# ───────────────────── 3D 뷰 클릭 → 단면 위치 저장 ────────────────────
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

# ───────────────────── 3D/단면도 업데이트 콜백 ────────────────────
@callback(
    Output("viewer-3d", "figure"),
    Output("current-time-store", "data", allow_duplicate=True),
    Output("current-file-title", "children"),
    Output("viewer-3d-store", "data"),
    Output("time-slider", "min", allow_duplicate=True),
    Output("time-slider", "max", allow_duplicate=True),
    Output("time-slider", "marks", allow_duplicate=True),
    Output("time-slider", "value", allow_duplicate=True),
    Output("current-file-title-store", "data", allow_duplicate=True),
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

    # 시간 파싱 및 슬라이더 상태 계산
    times = []
    for f in inp_files:
        try:
            time_str = os.path.basename(f).split(".")[0]
            dt = datetime.strptime(time_str, "%Y%m%d%H")
            times.append(dt)
        except:
            continue
    if not times:
        return dash.no_update, dash.no_update, dash.no_update, dash.no_update, 0, 5, {}, 0, ""
    marks = {}
    for i, t in enumerate(times):
        if t.hour == 0:
            marks[i] = t.strftime("%m/%d")
    if 0 not in marks:
        marks[0] = times[0].strftime("%m/%d")
    if (len(times)-1) not in marks:
        marks[len(times)-1] = times[-1].strftime("%m/%d")
    max_idx = len(times)-1
    # value가 max보다 크거나 None/NaN이면 max로 맞춤
    import math
    if time_idx is None or (isinstance(time_idx, float) and math.isnan(time_idx)) or (isinstance(time_idx, str) and not time_idx.isdigit()):
        value = max_idx
    else:
        value = min(int(time_idx), max_idx)

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
    current_file = inp_files[value]
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
    # 3D 뷰 시점 고정 및 경계선 추가
    fig_3d.update_layout(
        uirevision='constant',  # 시점 고정
        scene=dict(
            aspectmode='data',  # 데이터 비율 유지
            bgcolor='white',    # 배경색
            xaxis=dict(showgrid=True, gridcolor='lightgray', showline=True, linecolor='black'),
            yaxis=dict(showgrid=True, gridcolor='lightgray', showline=True, linecolor='black'),
            zaxis=dict(showgrid=True, gridcolor='lightgray', showline=True, linecolor='black'),
        ),
        margin=dict(l=0, r=0, t=0, b=0)
    )
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
                    names.append(srow['device_id'])
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
    
    # 3D 뷰 정보를 Store에 저장
    viewer_data = {
        'figure': fig_3d,
        'current_time': current_time,
        'current_file_title': current_file_title,
        'slider': {
            'min': 0,
            'max': max_idx,
            'marks': marks,
            'value': value
        }
    }
    
    return fig_3d, current_time, current_file_title, viewer_data, 0, max_idx, marks, value, current_file_title

# 탭 콘텐츠 처리 콜백 (수정)
@callback(
    Output("tab-content", "children"),
    Output("current-file-title", "children", allow_duplicate=True),
    Input("tabs-main", "active_tab"),
    State("tbl-concrete", "selected_rows"),
    State("tbl-concrete", "data"),
    State("viewer-3d-store", "data"),
    State("current-file-title-store", "data"),
    prevent_initial_call=True,
)
def switch_tab(active_tab, selected_rows, tbl_data, viewer_data, current_file_title):
    # 안내 문구만 보여야 하는 경우(분석 시작 안내, 데이터 없음)
    guide_message = None
    if selected_rows and tbl_data:
        row = pd.DataFrame(tbl_data).iloc[selected_rows[0]]
        is_active = row["activate"] == "활성"
        concrete_pk = row["concrete_pk"]
        inp_dir = f"inp/{concrete_pk}"
        inp_files = glob.glob(f"{inp_dir}/*.inp")
        if is_active:
            guide_message = "⚠️ 분석을 시작하려면 왼쪽의 '분석 시작' 버튼을 클릭하세요."
        elif not inp_files:
            guide_message = "⏳ 아직 수집된 데이터가 없습니다. 잠시 후 다시 확인해주세요."
    elif tbl_data is not None and len(tbl_data) == 0:
        guide_message = "분석할 콘크리트를 추가하세요."
    if guide_message:
        return html.Div([
            html.Div(guide_message, style={
                "textAlign": "center", "fontSize": "1.3rem", "color": "#555", "marginTop": "120px"
            })
        ]), ""
    # 이하 기존 코드 유지
    if active_tab == "tab-3d":
        # 저장된 3D 뷰 정보가 있으면 복원, 없으면 기본 뷰
        if viewer_data and 'figure' in viewer_data:
            fig_3d = viewer_data['figure']
            slider = viewer_data.get('slider', {})
            slider_min = slider.get('min', 0)
            slider_max = slider.get('max', 5)
            slider_marks = slider.get('marks', {})
            slider_value = slider.get('value', 0)
        else:
            # 기본 빈 3D 뷰
            fig_3d = go.Figure()
            fig_3d.update_layout(
                scene=dict(
                    xaxis=dict(title="X"),
                    yaxis=dict(title="Y"),
                    zaxis=dict(title="Z"),
                ),
                title="콘크리트를 선택하고 시간을 조절하세요"
            )
            slider_min, slider_max, slider_marks, slider_value = 0, 5, {}, 0
        return html.Div([
            # 시간 슬라이더 (3D 뷰 위에 배치)
            html.Div([
                html.Label("시간", className="form-label"),
                dcc.Slider(
                    id="time-slider",
                    min=slider_min,
                    max=slider_max,
                    step=1,
                    value=slider_value,
                    marks=slider_marks,
                    tooltip={"placement": "bottom", "always_visible": True},
                ),
            ], className="mb-3"),
            dbc.Row([
                dbc.Col([
                    html.Div([
                        dcc.Graph(
                            id="viewer-3d",
                            style={"height": "70vh", "border": "2px solid #dee2e6", "borderRadius": "8px"},
                            config={"scrollZoom": True},
                            figure=fig_3d,
                        ),
                    ], style={"padding": "10px"}),
                ], md=12),
            ]),
        ]), current_file_title
    elif active_tab == "tab-section":
        # 단면도 탭: 2x2 배열 배치, 입력창 상단, 3D 뷰/단면도
        if viewer_data and 'slider' in viewer_data:
            slider = viewer_data['slider']
            slider_min = slider.get('min', 0)
            slider_max = slider.get('max', 5)
            slider_marks = slider.get('marks', {})
            slider_value = slider.get('value', 0)
        else:
            slider_min, slider_max, slider_marks, slider_value = 0, 5, {}, 0
        return html.Div([
            # 시간 슬라이더 (상단)
            html.Div([
                html.Label("시간", className="form-label"),
                dcc.Slider(
                    id="time-slider-section",
                    min=slider_min,
                    max=slider_max,
                    step=1,
                    value=slider_value,
                    marks=slider_marks,
                    tooltip={"placement": "bottom", "always_visible": True},
                ),
            ], className="mb-3"),
            # 입력창 (x, y, z)
            html.Div([
                html.Label("단면 위치 설정", className="mb-2"),
                html.Div([
                    dbc.InputGroup([
                        html.Span(style={"display": "inline-block", "width": "18px", "height": "18px", "borderRadius": "50%", "backgroundColor": "#ff3333", "marginRight": "6px", "marginTop": "8px"}),
                        dbc.InputGroupText("X"),
                        dbc.Input(id="section-x-input", type="number", step=0.1, value=None, style={"width": "80px"}),
                    ], className="me-2", style={"display": "inline-flex", "verticalAlign": "middle"}),
                    dbc.InputGroup([
                        html.Span(style={"display": "inline-block", "width": "18px", "height": "18px", "borderRadius": "50%", "backgroundColor": "#3388ff", "marginRight": "6px", "marginTop": "8px"}),
                        dbc.InputGroupText("Y"),
                        dbc.Input(id="section-y-input", type="number", step=0.1, value=None, style={"width": "80px"}),
                    ], className="me-2", style={"display": "inline-flex", "verticalAlign": "middle"}),
                    dbc.InputGroup([
                        html.Span(style={"display": "inline-block", "width": "18px", "height": "18px", "borderRadius": "50%", "backgroundColor": "#33cc33", "marginRight": "6px", "marginTop": "8px"}),
                        dbc.InputGroupText("Z"),
                        dbc.Input(id="section-z-input", type="number", step=0.1, value=None, style={"width": "80px"}),
                    ], style={"display": "inline-flex", "verticalAlign": "middle"}),
                ], style={"display": "flex", "flexDirection": "row", "alignItems": "center"}),
            ], style={"padding": "10px"}),
            # 2x2 배열 배치 (컬러바 제거)
            dbc.Row([
                dbc.Col([
                    dbc.Row([
                        dbc.Col([
                            dcc.Graph(id="viewer-3d-section", style={"height": "32vh", "border": "2px solid #dee2e6", "borderRadius": "8px"}, config={"scrollZoom": True}),
                        ], md=6),
                        dbc.Col([
                            dcc.Graph(id="viewer-section-x", style={"height": "32vh"}),
                        ], md=6),
                    ], className="mb-2"),
                    dbc.Row([
                        dbc.Col([
                            dcc.Graph(id="viewer-section-y", style={"height": "32vh"}),
                        ], md=6),
                        dbc.Col([
                            dcc.Graph(id="viewer-section-z", style={"height": "32vh"}),
                        ], md=6),
                    ]),
                ], md=12),
            ]),
        ]), current_file_title
    elif active_tab == "tab-temp":
        # 온도 변화 탭: 입력창(맨 위), 3D 뷰(왼쪽, 콘크리트 모양만, 온도 없음, 입력 위치 표시), 오른쪽 시간에 따른 온도 정보(그래프)
        # 기본값 계산용
        if selected_rows and tbl_data:
            row = pd.DataFrame(tbl_data).iloc[selected_rows[0]]
            try:
                dims = ast.literal_eval(row["dims"]) if isinstance(row["dims"], str) else row["dims"]
                poly_nodes = np.array(dims["nodes"])
                poly_h = float(dims["h"])
                x_mid = float(np.mean(poly_nodes[:,0]))
                y_mid = float(np.mean(poly_nodes[:,1]))
                z_mid = float(poly_h/2)
                x_min, x_max = float(np.min(poly_nodes[:,0])), float(np.max(poly_nodes[:,0]))
                y_min, y_max = float(np.min(poly_nodes[:,1])), float(np.max(poly_nodes[:,1]))
                z_min, z_max = 0.0, float(poly_h)
            except Exception:
                x_mid, y_mid, z_mid = 0.5, 0.5, 0.5
                x_min, x_max = 0.0, 1.0
                y_min, y_max = 0.0, 1.0
                z_min, z_max = 0.0, 1.0
        else:
            x_mid, y_mid, z_mid = 0.5, 0.5, 0.5
            x_min, x_max = 0.0, 1.0
            y_min, y_max = 0.0, 1.0
            z_min, z_max = 0.0, 1.0
        # dcc.Store로 기본값 저장: 탭 진입 시 자동으로 콜백이 실행되도록
        store_data = {'x': round(x_mid,1), 'y': round(y_mid,1), 'z': round(z_mid,1)}
        return html.Div([
            dcc.Store(id="temp-coord-store", data=store_data),
            # 입력창 (맨 위)
            html.Div([
                html.Label("위치 설정", className="mb-2"),
                html.Div([
                    dbc.InputGroup([
                        dbc.InputGroupText("X"),
                        dbc.Input(id="temp-x-input", type="number", step=0.1, value=round(x_mid,1), min=round(x_min,2), max=round(x_max,2), style={"width": "80px"}),
                    ], className="me-2", style={"display": "inline-flex", "verticalAlign": "middle"}),
                    dbc.InputGroup([
                        dbc.InputGroupText("Y"),
                        dbc.Input(id="temp-y-input", type="number", step=0.1, value=round(y_mid,1), min=round(y_min,2), max=round(y_max,2), style={"width": "80px"}),
                    ], className="me-2", style={"display": "inline-flex", "verticalAlign": "middle"}),
                    dbc.InputGroup([
                        dbc.InputGroupText("Z"),
                        dbc.Input(id="temp-z-input", type="number", step=0.1, value=round(z_mid,1), min=round(z_min,2), max=round(z_max,2), style={"width": "80px"}),
                    ], style={"display": "inline-flex", "verticalAlign": "middle"}),
                ], style={"display": "flex", "flexDirection": "row", "alignItems": "center"}),
            ], style={"padding": "10px"}),
            # 3D 뷰 + 온도 정보 (좌우 배치)
            dbc.Row([
                dbc.Col([
                    dcc.Graph(id="temp-viewer-3d", style={"height": "50vh", "border": "2px solid #dee2e6", "borderRadius": "8px"}, config={"scrollZoom": True}),
                ], md=6),
                dbc.Col([
                    dcc.Graph(id="temp-time-graph", style={"height": "50vh"}),
                ], md=6),
            ]),
        ]), "전체 파일"
    elif active_tab == "tab-analysis":
        # 수치해석 탭: 서버에서 VTK/VTP 파일을 파싱하여 dash_vtk.Mesh로 시각화 + 컬러맵 필드/프리셋 선택
        if not (selected_rows and tbl_data):
            return html.Div("콘크리트를 선택하세요."), ""
        
        row = pd.DataFrame(tbl_data).iloc[selected_rows[0]]
        concrete_pk = row["concrete_pk"]
        assets_vtk_dir = f"assets/vtk/{concrete_pk}"
        assets_vtp_dir = f"assets/vtp/{concrete_pk}"
        
        vtk_files = []
        vtp_files = []
        if os.path.exists(assets_vtk_dir):
            vtk_files = sorted([f for f in os.listdir(assets_vtk_dir) if f.endswith('.vtk')])
        if os.path.exists(assets_vtp_dir):
            vtp_files = sorted([f for f in os.listdir(assets_vtp_dir) if f.endswith('.vtp')])
        
        if not vtk_files and not vtp_files:
            return html.Div("VTK/VTP 파일이 없습니다."), ""
        
        # 시간 정보 파싱
        from datetime import datetime
        times = []
        file_type = None
        files = []
        
        if vtk_files:
            files = vtk_files
            file_type = 'vtk'
        elif vtp_files:
            files = vtp_files
            file_type = 'vtp'
        
        for f in files:
            try:
                time_str = os.path.splitext(f)[0]
                dt = datetime.strptime(time_str, "%Y%m%d%H")
                times.append((dt, f))
            except:
                continue
        
        if not times:
            return html.Div("시간 정보가 포함된 VTK/VTP 파일이 없습니다.")
        
        times.sort()
        max_idx = len(times) - 1
        
        # 첫 번째 파일을 기본으로 사용하여 필드 정보 추출
        first_file = times[-1][1]  # 최신 파일 사용
        file_path = os.path.join(assets_vtk_dir if file_type=='vtk' else assets_vtp_dir, first_file)
        
        field_options = []
        try:
            import vtk
            if file_type == 'vtk':
                reader = vtk.vtkUnstructuredGridReader()
                reader.SetFileName(file_path)
                reader.Update()
                ds = reader.GetOutput()
            else:
                reader = vtk.vtkXMLPolyDataReader()
                reader.SetFileName(file_path)
                reader.Update()
                ds = reader.GetOutput()
            
            # UnstructuredGrid → PolyData 변환 (GeometryFilter)  ⭐ 추가
            if isinstance(ds, vtk.vtkUnstructuredGrid):
                geom_filter = vtk.vtkGeometryFilter()
                geom_filter.SetInputData(ds)
                geom_filter.Update()
                ds = geom_filter.GetOutput()
            
            # 사용 가능한 필드 추출
            point_data = ds.GetPointData()
            field_names = []
            for i in range(point_data.GetNumberOfArrays()):
                arr_name = point_data.GetArrayName(i)
                if arr_name:
                    field_names.append(arr_name)
            
            # 한글 필드명 매핑
            field_mapping = {
                'Temperature': '온도(Temperature)',
                'Displacement': '변위(Displacement)', 
                'Stress': '응력(Stress)',
                'Strain': '변형률(Strain)',
                'Velocity': '속도(Velocity)',
                'Pressure': '압력(Pressure)',
                'U': '변위(U)',
                'S': '응력(S)',
                'S_Mises': '미세스응력(S_Mises)',
                'S_Principal': '주응력(S_Principal)'
            }
            
            for name in field_names:
                display_name = field_mapping.get(name, f"{name}")
                field_options.append({"label": display_name, "value": name})
            
        except Exception as e:
            print(f"필드 추출 오류: {e}")
        
        # 컬러맵 프리셋 옵션 (5개로 제한)
        preset_options = [
            {"label": "무지개", "value": "rainbow"},
            {"label": "블루-레드", "value": "Cool to Warm"},
            {"label": "회색", "value": "Grayscale"},
            {"label": "Viridis", "value": "viridis"},
            {"label": "Plasma", "value": "plasma"}
        ]
        
        # 시간 슬라이더 마크
        time_marks = {}
        for i, (dt, _) in enumerate(times):
            if dt.hour == 0 or i == 0 or i == max_idx:
                time_marks[i] = dt.strftime("%m/%d")
        
        return html.Div([
            # 컨트롤 패널
            dbc.Row([
                dbc.Col([
                    html.Label("컬러맵 필드"),
                    dcc.Dropdown(
                        id="analysis-field-dropdown",
                        options=field_options,
                        value=field_options[0]["value"] if field_options else None,
                        placeholder="필드 선택"
                    )
                ], md=3),
                dbc.Col([
                    html.Label("컬러맵 프리셋"),
                    dcc.Dropdown(
                        id="analysis-preset-dropdown", 
                        options=preset_options,
                        value="rainbow",
                        placeholder="프리셋 선택"
                    )
                ], md=3),
                dbc.Col([
                    html.Label("시간"),
                    dcc.Slider(
                        id="analysis-time-slider",
                        min=0,
                        max=max_idx,
                        step=1,
                        value=max_idx,
                        marks=time_marks,
                        tooltip={"placement": "bottom", "always_visible": True}
                    )
                ], md=6),
            ], className="mb-3"),
            
            # 현재 파일/범위 표시
            html.Div(id="analysis-current-file-label", style={"marginBottom":"8px", "fontWeight":"500"}),
            
            # 3D 뷰어
            html.Div(id="analysis-3d-viewer", style={"height": "60vh"})
            
        ]), f"수치해석 결과 ({len(files)}개 파일)"
    elif active_tab == "tab-inp-files":
        # inp 파일 목록 탭
        if not (selected_rows and tbl_data):
            return html.Div("콘크리트를 선택하세요."), ""
        row = pd.DataFrame(tbl_data).iloc[selected_rows[0]]
        concrete_pk = row["concrete_pk"]
        inp_dir = f"inp/{concrete_pk}"
        try:
            if not os.path.exists(inp_dir):
                return html.Div("inp 폴더가 존재하지 않습니다."), ""
            files = sorted([f for f in os.listdir(inp_dir) if f.endswith('.inp')])
        except Exception as e:
            return html.Div(f"파일 목록을 불러오는 중 오류 발생: {e}"), ""
        if not files:
            return html.Div("inp 파일이 없습니다."), ""
        # 파일 목록 테이블 + 다운로드 버튼
        table = dash_table.DataTable(
            id="inp-file-table",
            columns=[
                {"name": "파일명", "id": "filename"},
            ],
            data=[{"filename": f} for f in files],
            style_cell={"textAlign": "center"},
            style_header={"backgroundColor": "#f1f3f5", "fontWeight": 600},
            style_table={"width": "60%", "margin": "auto"},
            page_size=10,
            row_selectable="multi",
            cell_selectable=False,
        )
        return html.Div([
            table,
            html.Div([
                dbc.Button("전체 선택", id="btn-inp-select-all", color="secondary", className="me-2 mt-3", n_clicks=0),
                dbc.Button("전체 해제", id="btn-inp-deselect-all", color="light", className="me-2 mt-3", n_clicks=0),
                dbc.Button("선택 파일 다운로드", id="btn-inp-download", color="success", className="mt-3", n_clicks=0),
                dcc.Download(id="inp-file-download")
            ], style={"textAlign": "center"})
        ]), f"inp 파일 {len(files)}개"
    elif active_tab == "tab-frd-upload":
        # frd 파일 업로드 탭
        if not (selected_rows and tbl_data):
            return html.Div("콘크리트를 선택하세요."), ""
        row = pd.DataFrame(tbl_data).iloc[selected_rows[0]]
        concrete_pk = row["concrete_pk"]
        upload_dir = f"frd/{concrete_pk}"
        os.makedirs(upload_dir, exist_ok=True)
        # 현재 업로드된 파일 목록
        file_list = []
        try:
            file_list = sorted([f for f in os.listdir(upload_dir) if os.path.isfile(os.path.join(upload_dir, f))])
        except Exception:
            file_list = []
        return html.Div([
            html.H5("frd 파일 업로드", className="mb-3"),
            dcc.Upload(
                id="frd-upload",
                children=html.Div([
                    '여기에 frd 파일을 드래그하거나 ',
                    html.A('클릭하여 업로드')
                ]),
                multiple=True,
                style={
                    'width': '100%', 'height': '80px', 'lineHeight': '80px',
                    'borderWidth': '1px', 'borderStyle': 'dashed', 'borderRadius': '8px',
                    'textAlign': 'center', 'margin': '20px 0', 'background': '#f8f9fa'
                },
            ),
            html.Div(id="frd-upload-msg", className="mt-3"),
            html.H6("현재 업로드된 파일 목록", className="mt-4 mb-2"),
            html.Ul([html.Li(f) for f in file_list]) if file_list else html.Div("업로드된 파일이 없습니다.", style={"color": "#888"}),
        ]), "frd 파일 업로드"
    elif active_tab == "tab-vtk-files":
        # vtk 파일 목록 탭
        if not (selected_rows and tbl_data):
            return html.Div("콘크리트를 선택하세요."), ""
        row = pd.DataFrame(tbl_data).iloc[selected_rows[0]]
        concrete_pk = row["concrete_pk"]
        vtk_dir = f"assets/vtk/{concrete_pk}"
        try:
            if not os.path.exists(vtk_dir):
                return html.Div("vtk 폴더가 존재하지 않습니다."), ""
            files = sorted([f for f in os.listdir(vtk_dir) if f.endswith('.vtk')])
        except Exception as e:
            return html.Div(f"파일 목록을 불러오는 중 오류 발생: {e}"), ""
        if not files:
            return html.Div("vtk 파일이 없습니다."), ""
        # 파일 목록 테이블 + 다운로드 버튼
        table = dash_table.DataTable(
            id="vtk-file-table",
            columns=[
                {"name": "파일명", "id": "filename"},
            ],
            data=[{"filename": f} for f in files],
            style_cell={"textAlign": "center"},
            style_header={"backgroundColor": "#f1f3f5", "fontWeight": 600},
            style_table={"width": "60%", "margin": "auto"},
            page_size=10,
            row_selectable="multi",
            cell_selectable=False,
        )
        return html.Div([
            table,
            html.Div([
                dbc.Button("전체 선택", id="btn-vtk-select-all", color="secondary", className="me-2 mt-3", n_clicks=0),
                dbc.Button("전체 해제", id="btn-vtk-deselect-all", color="light", className="me-2 mt-3", n_clicks=0),
                dbc.Button("선택 파일 다운로드", id="btn-vtk-download", color="success", className="mt-3", n_clicks=0),
                dcc.Download(id="vtk-file-download")
            ], style={"textAlign": "center"})
        ]), f"vtk 파일 {len(files)}개"
    elif active_tab == "tab-vtp-files":
        # vtp 파일 목록 탭
        if not (selected_rows and tbl_data):
            return html.Div("콘크리트를 선택하세요."), ""
        row = pd.DataFrame(tbl_data).iloc[selected_rows[0]]
        concrete_pk = row["concrete_pk"]
        vtp_dir = f"assets/vtp/{concrete_pk}"
        try:
            if not os.path.exists(vtp_dir):
                return html.Div("vtp 폴더가 존재하지 않습니다."), ""
            files = sorted([f for f in os.listdir(vtp_dir) if f.endswith('.vtp')])
        except Exception as e:
            return html.Div(f"파일 목록을 불러오는 중 오류 발생: {e}"), ""
        if not files:
            return html.Div("vtp 파일이 없습니다."), ""
        # 파일 목록 테이블 + 다운로드 버튼
        table = dash_table.DataTable(
            id="vtp-file-table",
            columns=[
                {"name": "파일명", "id": "filename"},
            ],
            data=[{"filename": f} for f in files],
            style_cell={"textAlign": "center"},
            style_header={"backgroundColor": "#f1f3f5", "fontWeight": 600},
            style_table={"width": "60%", "margin": "auto"},
            page_size=10,
            row_selectable="multi",
            cell_selectable=False,
        )
        return html.Div([
            table,
            html.Div([
                dbc.Button("전체 선택", id="btn-vtp-select-all", color="secondary", className="me-2 mt-3", n_clicks=0),
                dbc.Button("전체 해제", id="btn-vtp-deselect-all", color="light", className="me-2 mt-3", n_clicks=0),
                dbc.Button("선택 파일 다운로드", id="btn-vtp-download", color="success", className="mt-3", n_clicks=0),
                dcc.Download(id="vtp-file-download")
            ], style={"textAlign": "center"})
        ]), f"vtp 파일 {len(files)}개"
    return html.Div(), current_file_title

# 선택 파일 zip 다운로드 콜백
@callback(
    Output("inp-file-download", "data"),
    Input("btn-inp-download", "n_clicks"),
    State("inp-file-table", "selected_rows"),
    State("inp-file-table", "data"),
    State("tbl-concrete", "selected_rows"),
    State("tbl-concrete", "data"),
    prevent_initial_call=True,
)
def download_selected_inp_files(n_clicks, selected_rows, table_data, selected_conc_rows, tbl_data):
    from dash.exceptions import PreventUpdate
    import io, zipfile, os
    if not n_clicks or not selected_rows or not selected_conc_rows or not tbl_data:
        raise PreventUpdate
    row = pd.DataFrame(tbl_data).iloc[selected_conc_rows[0]]
    concrete_pk = row["concrete_pk"]
    inp_dir = os.path.join("inp", str(concrete_pk))
    files = [table_data[i]["filename"] for i in selected_rows]
    if not files:
        raise PreventUpdate
    # zip 파일 메모리 생성
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zf:
        for fname in files:
            fpath = os.path.join(inp_dir, fname)
            if os.path.exists(fpath):
                zf.write(fpath, arcname=fname)
    zip_buffer.seek(0)
    return dcc.send_bytes(zip_buffer.getvalue(), filename=f"inp_files_{concrete_pk}.zip")

# 전체 선택/해제 콜백
@callback(
    Output("inp-file-table", "selected_rows"),
    Input("btn-inp-select-all", "n_clicks"),
    Input("btn-inp-deselect-all", "n_clicks"),
    State("inp-file-table", "data"),
    prevent_initial_call=True,
)
def select_deselect_all(n_all, n_none, table_data):
    import dash
    ctx = dash.callback_context
    if not ctx.triggered or not table_data:
        raise dash.exceptions.PreventUpdate
    trig = ctx.triggered_id
    if trig == "btn-inp-select-all":
        return list(range(len(table_data)))
    elif trig == "btn-inp-deselect-all":
        return []
    raise dash.exceptions.PreventUpdate

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
    Output("btn-concrete-analyze", "disabled", allow_duplicate=True),
    Input("btn-concrete-analyze", "n_clicks"),
    State("tbl-concrete", "selected_rows"),
    State("tbl-concrete", "data"),
    prevent_initial_call=True,
)
def start_analysis(n_clicks, selected_rows, tbl_data):
    if not selected_rows:
        return "콘크리트를 선택하세요", "warning", True, dash.no_update, dash.no_update

    row = pd.DataFrame(tbl_data).iloc[selected_rows[0]]
    concrete_pk = row["concrete_pk"]

    try:
        # activate를 0으로 변경
        api_db.update_concrete_data(concrete_pk=concrete_pk, activate=0)
        
        # (1) 센서 데이터 자동 저장
        auto_sensor.auto_sensor_data()
        # (2) 1초 대기 후 INP 자동 생성
        time.sleep(1)
        auto_inp.auto_inp()
        
        # 테이블 데이터 업데이트
        updated_data = tbl_data.copy()
        updated_data[selected_rows[0]]["activate"] = "비활성"
        
        return f"{concrete_pk} 분석이 시작되었습니다", "success", True, updated_data, True
    except Exception as e:
        return f"분석 시작 실패: {e}", "danger", True, dash.no_update, dash.no_update

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

# 단면도 탭 콜백: 3D 뷰(작게)와 X/Y/Z 단면도, 입력창 min/max 자동 설정
@callback(
    Output("viewer-3d-section", "figure"),
    Output("viewer-section-x", "figure"),
    Output("viewer-section-y", "figure"),
    Output("viewer-section-z", "figure"),
    Output("section-x-input", "min"), Output("section-x-input", "max"), Output("section-x-input", "value"),
    Output("section-y-input", "min"), Output("section-y-input", "max"), Output("section-y-input", "value"),
    Output("section-z-input", "min"), Output("section-z-input", "max"), Output("section-z-input", "value"),
    Output("current-file-title", "children", allow_duplicate=True),
    Input("time-slider-section", "value"),
    Input("section-x-input", "value"),
    Input("section-y-input", "value"),
    Input("section-z-input", "value"),
    State("tbl-concrete", "selected_rows"),
    State("tbl-concrete", "data"),
    prevent_initial_call=True,
)
def update_section_views(time_idx, x_val, y_val, z_val, selected_rows, tbl_data):
    import math
    import plotly.graph_objects as go
    import numpy as np
    from scipy.interpolate import griddata
    if not selected_rows:
        return go.Figure(), go.Figure(), go.Figure(), go.Figure(), 0, 1, 0.5, 0, 1, 0.5, 0, 1, 0.5, ""
    row = pd.DataFrame(tbl_data).iloc[selected_rows[0]]
    concrete_pk = row["concrete_pk"]
    inp_dir = f"inp/{concrete_pk}"
    inp_files = sorted(glob.glob(f"{inp_dir}/*.inp"))
    if not inp_files:
        return go.Figure(), go.Figure(), go.Figure(), go.Figure(), 0, 1, 0.5, 0, 1, 0.5, 0, 1, 0.5, ""
    # 시간 인덱스 안전 처리
    if time_idx is None or (isinstance(time_idx, float) and math.isnan(time_idx)) or (isinstance(time_idx, str) and not str(time_idx).isdigit()):
        file_idx = len(inp_files)-1
    else:
        file_idx = min(int(time_idx), len(inp_files)-1)
    current_file = inp_files[file_idx]
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
    # 입력창 min/max/기본값 자동 설정
    x_min, x_max = float(np.min(x_coords)), float(np.max(x_coords))
    y_min, y_max = float(np.min(y_coords)), float(np.max(y_coords))
    z_min, z_max = float(np.min(z_coords)), float(np.max(z_coords))
    x_mid = float(np.median(x_coords))
    y_mid = float(np.median(y_coords))
    z_mid = float(np.median(z_coords))
    def round01(val):
        return round(val * 10) / 10 if val is not None else None
    x0 = round01(x_val) if x_val is not None else round01(x_mid)
    y0 = round01(y_val) if y_val is not None else round01(y_mid)
    z0 = round01(z_val) if z_val is not None else round01(z_mid)
    # 3D 뷰(작게)
    coords = np.array([[x, y, z] for x, y, z in zip(x_coords, y_coords, z_coords)])
    fig_3d = go.Figure(data=go.Volume(
        x=coords[:,0], y=coords[:,1], z=coords[:,2], value=temps,
        opacity=0.1, surface_count=15, colorscale=[[0, 'blue'], [1, 'red']],
        colorbar=None, cmin=tmin, cmax=tmax, showscale=False
    ))
    fig_3d.update_layout(
        uirevision='constant',
        scene=dict(aspectmode='data', bgcolor='white'),
        margin=dict(l=0, r=0, t=0, b=0)
    )
    # 단면 위치 평면(케이크 자르듯)
    # X 평면
    fig_3d.add_trace(go.Surface(
        x=[[x0, x0], [x0, x0]],
        y=[[y_min, y_max], [y_min, y_max]],
        z=[[z_min, z_min], [z_max, z_max]],
        showscale=False, opacity=0.3, colorscale=[[0, 'red'], [1, 'red']],
        hoverinfo='skip', name='X-section', showlegend=False
    ))
    # Y 평면
    fig_3d.add_trace(go.Surface(
        x=[[x_min, x_max], [x_min, x_max]],
        y=[[y0, y0], [y0, y0]],
        z=[[z_min, z_min], [z_max, z_max]],
        showscale=False, opacity=0.3, colorscale=[[0, 'blue'], [1, 'blue']],
        hoverinfo='skip', name='Y-section', showlegend=False
    ))
    # Z 평면
    fig_3d.add_trace(go.Surface(
        x=[[x_min, x_max], [x_min, x_max]],
        y=[[y_min, y_min], [y_max, y_max]],
        z=[[z0, z0], [z0, z0]],
        showscale=False, opacity=0.3, colorscale=[[0, 'green'], [1, 'green']],
        hoverinfo='skip', name='Z-section', showlegend=False
    ))
    # X 단면 (x ≈ x0, 리니어 보간, 컬러바 없음)
    tol = 0.05
    mask_x = np.abs(x_coords - x0) < tol
    if np.any(mask_x):
        yb, zb, tb = y_coords[mask_x], z_coords[mask_x], temps[mask_x]
        if len(yb) > 3:
            y_bins = np.linspace(yb.min(), yb.max(), 40)
            z_bins = np.linspace(zb.min(), zb.max(), 40)
            yy, zz = np.meshgrid(y_bins, z_bins)
            points = np.column_stack([yb, zb])
            values = tb
            grid = griddata(points, values, (yy, zz), method='linear')
            fig_x = go.Figure(go.Heatmap(
                x=y_bins, y=z_bins, z=grid.T, colorscale=[[0, 'blue'], [1, 'red']], zmin=tmin, zmax=tmax, colorbar=None, zsmooth='best'))
        else:
            fig_x = go.Figure()
    else:
        fig_x = go.Figure()
    fig_x.update_layout(
        title=f"X={x0:.2f}m 단면", xaxis_title="Y (m)", yaxis_title="Z (m)", margin=dict(l=0, r=0, b=0, t=30),
        xaxis=dict(scaleanchor="y", scaleratio=1),
        yaxis=dict(constrain='domain')
    )
    # Y 단면 (y ≈ y0, 리니어 보간, 컬러바 없음)
    mask_y = np.abs(y_coords - y0) < tol
    if np.any(mask_y):
        xb, zb, tb = x_coords[mask_y], z_coords[mask_y], temps[mask_y]
        if len(xb) > 3:
            x_bins = np.linspace(xb.min(), xb.max(), 40)
            z_bins = np.linspace(zb.min(), zb.max(), 40)
            xx, zz = np.meshgrid(x_bins, z_bins)
            points = np.column_stack([xb, zb])
            values = tb
            grid = griddata(points, values, (xx, zz), method='linear')
            fig_y = go.Figure(go.Heatmap(
                x=x_bins, y=z_bins, z=grid.T, colorscale=[[0, 'blue'], [1, 'red']], zmin=tmin, zmax=tmax, colorbar=None, zsmooth='best'))
        else:
            fig_y = go.Figure()
    else:
        fig_y = go.Figure()
    fig_y.update_layout(
        title=f"Y={y0:.2f}m 단면", xaxis_title="X (m)", yaxis_title="Z (m)", margin=dict(l=0, r=0, b=0, t=30),
        xaxis=dict(scaleanchor="y", scaleratio=1),
        yaxis=dict(constrain='domain')
    )
    # Z 단면 (z ≈ z0, 리니어 보간, 컬러바 없음)
    mask_z = np.abs(z_coords - z0) < tol
    if np.any(mask_z):
        xb, yb, tb = x_coords[mask_z], y_coords[mask_z], temps[mask_z]
        if len(xb) > 3:
            x_bins = np.linspace(xb.min(), xb.max(), 40)
            y_bins = np.linspace(yb.min(), yb.max(), 40)
            xx, yy = np.meshgrid(x_bins, y_bins)
            points = np.column_stack([xb, yb])
            values = tb
            grid = griddata(points, values, (xx, yy), method='linear')
            fig_z = go.Figure(go.Heatmap(
                x=x_bins, y=y_bins, z=grid.T, colorscale=[[0, 'blue'], [1, 'red']], zmin=tmin, zmax=tmax, colorbar=None, zsmooth='best'))
        else:
            fig_z = go.Figure()
    else:
        fig_z = go.Figure()
    fig_z.update_layout(
        title=f"Z={z0:.2f}m 단면", xaxis_title="X (m)", yaxis_title="Y (m)", margin=dict(l=0, r=0, b=0, t=30),
        xaxis=dict(scaleanchor="y", scaleratio=1),
        yaxis=dict(constrain='domain')
    )
    # 현재 파일명/온도 통계 계산
    try:
        time_str = os.path.basename(current_file).split(".")[0]
        current_min = float(np.nanmin(temps))
        current_max = float(np.nanmax(temps))
        current_avg = float(np.nanmean(temps))
        current_file_title = f"현재 파일: {time_str} (최저: {current_min:.1f}°C, 최고: {current_max:.1f}°C, 평균: {current_avg:.1f}°C)"
    except Exception:
        current_file_title = f"현재 파일: {os.path.basename(current_file)}"
    # step=0.1로 반환
    return fig_3d, fig_x, fig_y, fig_z, x_min, x_max, x0, y_min, y_max, y0, z_min, z_max, z0, current_file_title

# 온도분포 탭 콜백: 입력값 변경 시 3D 뷰와 온도 정보 갱신
@callback(
    Output("temp-viewer-3d", "figure"),
    Output("temp-time-graph", "figure"),
    Input("temp-coord-store", "data"),
    Input("temp-x-input", "value"),
    Input("temp-y-input", "value"),
    Input("temp-z-input", "value"),
    State("tbl-concrete", "selected_rows"),
    State("tbl-concrete", "data"),
    prevent_initial_call=False,
)
def update_temp_tab(store_data, x, y, z, selected_rows, tbl_data):
    import plotly.graph_objects as go
    import numpy as np
    import glob, os
    from datetime import datetime
    if not selected_rows or not tbl_data:
        return go.Figure(), go.Figure()
    # store_data가 있으면 기본값으로 사용, 입력값이 있으면 입력값 우선
    if store_data is not None:
        x0 = store_data.get('x', 0.5)
        y0 = store_data.get('y', 0.5)
        z0 = store_data.get('z', 0.5)
    else:
        x0, y0, z0 = 0.5, 0.5, 0.5
    x = x if x is not None else x0
    y = y if y is not None else y0
    z = z if z is not None else z0
    # poly_nodes, poly_h 정의 (NameError 방지)
    row = pd.DataFrame(tbl_data).iloc[selected_rows[0]]
    try:
        dims = ast.literal_eval(row["dims"]) if isinstance(row["dims"], str) else row["dims"]
        poly_nodes = np.array(dims["nodes"])
        poly_h = float(dims["h"])
    except Exception:
        poly_nodes = np.array([[0,0]])
        poly_h = 1.0
    # 콘크리트 외곽선(윗면, 아랫면)
    n = len(poly_nodes)
    x0s, y0s = poly_nodes[:,0], poly_nodes[:,1]
    z0s = np.zeros(n)
    z1 = np.full(n, poly_h)
    fig_3d = go.Figure()
    # 아래면
    fig_3d.add_trace(go.Scatter3d(
        x=np.append(x0s, x0s[0]), y=np.append(y0s, y0s[0]), z=np.append(z0s, z0s[0]),
        mode='lines', line=dict(width=2, color='black'), showlegend=False, hoverinfo='skip'))
    # 윗면
    fig_3d.add_trace(go.Scatter3d(
        x=np.append(x0s, x0s[0]), y=np.append(y0s, y0s[0]), z=np.append(z1, z1[0]),
        mode='lines', line=dict(width=2, color='black'), showlegend=False, hoverinfo='skip'))
    # 기둥
    for i in range(n):
        fig_3d.add_trace(go.Scatter3d(
            x=[x0s[i], x0s[i]], y=[y0s[i], y0s[i]], z=[z0s[i], z1[i]],
            mode='lines', line=dict(width=2, color='black'), showlegend=False, hoverinfo='skip'))
    # 입력 위치 표시 + 보조선
    if x is not None and y is not None and z is not None:
        # 점
        fig_3d.add_trace(go.Scatter3d(
            x=[x], y=[y], z=[z],
            mode='markers', marker=dict(size=6, color='red', symbol='circle'),
            name='위치', showlegend=False, hoverinfo='text', text=['선택 위치']
        ))
        # 보조선: x/y/z축 평면까지
        fig_3d.add_trace(go.Scatter3d(
            x=[x, x], y=[y, y], z=[0, z],
            mode='lines', line=dict(width=2, color='gray', dash='dash'), showlegend=False, hoverinfo='skip'))
        fig_3d.add_trace(go.Scatter3d(
            x=[x, x], y=[y, y], z=[z, poly_h],
            mode='lines', line=dict(width=2, color='gray', dash='dash'), showlegend=False, hoverinfo='skip'))
        fig_3d.add_trace(go.Scatter3d(
            x=[x, x], y=[min(y0s), max(y0s)], z=[z, z],
            mode='lines', line=dict(width=2, color='gray', dash='dash'), showlegend=False, hoverinfo='skip'))
        fig_3d.add_trace(go.Scatter3d(
            x=[min(x0s), max(x0s)], y=[y, y], z=[z, z],
            mode='lines', line=dict(width=2, color='gray', dash='dash'), showlegend=False, hoverinfo='skip'))
    fig_3d.update_layout(
        scene=dict(aspectmode='data', bgcolor='white'),
        margin=dict(l=0, r=0, t=0, b=0)
    )
    # 오른쪽 온도 정보(시간에 따른 입력 위치 온도)
    temp_times = []
    temp_values = []
    concrete_pk = row["concrete_pk"]
    inp_dir = f"inp/{concrete_pk}"
    inp_files = sorted(glob.glob(f"{inp_dir}/*.inp"))
    for f in inp_files:
        # 시간 파싱
        try:
            time_str = os.path.basename(f).split(".")[0]
            dt = datetime.strptime(time_str, "%Y%m%d%H")
        except:
            continue
        # inp 파일 파싱 (노드, 온도)
        with open(f, 'r') as file:
            lines = file.readlines()
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
                    nx = float(parts[1])
                    ny = float(parts[2])
                    nz = float(parts[3])
                    nodes[node_id] = {'x': nx, 'y': ny, 'z': nz}
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
        # 입력 위치와 가장 가까운 노드 찾기
        if x is not None and y is not None and z is not None and nodes:
            coords = np.array([[v['x'], v['y'], v['z']] for v in nodes.values()])
            node_ids = list(nodes.keys())
            dists = np.linalg.norm(coords - np.array([x, y, z]), axis=1)
            min_idx = np.argmin(dists)
            closest_id = node_ids[min_idx]
            temp_val = temperatures.get(closest_id, None)
            if temp_val is not None:
                temp_times.append(dt)
                temp_values.append(temp_val)
    # 그래프 생성
    fig_temp = go.Figure()
    if temp_times and temp_values:
        # 모든 시간 정보를 'M/D H시' 형식으로 표시
        x_labels = [dt.strftime('%-m/%-d %H시') for dt in temp_times]
        fig_temp.add_trace(go.Scatter(x=x_labels, y=temp_values, mode='lines+markers', name='온도'))
        fig_temp.update_layout(
            title="시간에 따른 온도 정보",
            xaxis_title="시간",
            yaxis_title="온도(°C)"
        )
    return fig_3d, fig_temp

# frd 파일 업로드 콜백 (중복 파일명 방지)
@callback(
    Output("frd-upload-msg", "children"),
    Input("frd-upload", "contents"),
    State("frd-upload", "filename"),
    State("tbl-concrete", "selected_rows"),
    State("tbl-concrete", "data"),
    prevent_initial_call=True,
)
def save_frd_files(contents, filenames, selected_rows, tbl_data):
    import base64, os
    from dash.exceptions import PreventUpdate
    if not contents or not filenames or not (selected_rows and tbl_data):
        raise PreventUpdate
    row = pd.DataFrame(tbl_data).iloc[selected_rows[0]]
    concrete_pk = row["concrete_pk"]
    upload_dir = f"frd/{concrete_pk}"
    os.makedirs(upload_dir, exist_ok=True)
    if isinstance(contents, str):
        contents = [contents]
        filenames = [filenames]
    # 중복 파일명 체크
    existing_files = set(os.listdir(upload_dir))
    for fname in filenames:
        if fname in existing_files:
            return html.Div([
                html.Span(f"중복된 파일명: {fname} (업로드 취소)", style={"color": "red"})
            ])
    saved_files = []
    for content, fname in zip(contents, filenames):
        try:
            header, data = content.split(",", 1)
            with open(os.path.join(upload_dir, fname), "wb") as f:
                f.write(base64.b64decode(data))
            saved_files.append(fname)
        except Exception as e:
            return html.Div([f"업로드 실패: {fname} ({e})"], style={"color": "red"})
    return html.Div([
        html.Span(f"{len(saved_files)}개 파일 업로드 완료: "),
        html.Ul([html.Li(f) for f in saved_files])
    ], style={"color": "green"})

# vtk 파일 다운로드 콜백
@callback(
    Output("vtk-file-download", "data"),
    Input("btn-vtk-download", "n_clicks"),
    State("vtk-file-table", "selected_rows"),
    State("vtk-file-table", "data"),
    State("tbl-concrete", "selected_rows"),
    State("tbl-concrete", "data"),
    prevent_initial_call=True,
)
def download_selected_vtk_files(n_clicks, selected_rows, table_data, selected_conc_rows, tbl_data):
    from dash.exceptions import PreventUpdate
    import io, zipfile, os
    if not n_clicks or not selected_rows or not selected_conc_rows or not tbl_data:
        raise PreventUpdate
    row = pd.DataFrame(tbl_data).iloc[selected_conc_rows[0]]
    concrete_pk = row["concrete_pk"]
    vtk_dir = os.path.join("assets/vtk", str(concrete_pk))
    files = [table_data[i]["filename"] for i in selected_rows]
    if not files:
        raise PreventUpdate
    # zip 파일 메모리 생성
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zf:
        for fname in files:
            fpath = os.path.join(vtk_dir, fname)
            if os.path.exists(fpath):
                zf.write(fpath, arcname=fname)
    zip_buffer.seek(0)
    return dcc.send_bytes(zip_buffer.getvalue(), filename=f"vtk_files_{concrete_pk}.zip")

# 전체 선택/해제 콜백 (vtk)
@callback(
    Output("vtk-file-table", "selected_rows"),
    Input("btn-vtk-select-all", "n_clicks"),
    Input("btn-vtk-deselect-all", "n_clicks"),
    State("vtk-file-table", "data"),
    prevent_initial_call=True,
)
def select_deselect_all_vtk(n_all, n_none, table_data):
    import dash
    ctx = dash.callback_context
    if not ctx.triggered or not table_data:
        raise dash.exceptions.PreventUpdate
    trig = ctx.triggered_id
    if trig == "btn-vtk-select-all":
        return list(range(len(table_data)))
    elif trig == "btn-vtk-deselect-all":
        return []
    raise dash.exceptions.PreventUpdate

# vtp 파일 다운로드 콜백
@callback(
    Output("vtp-file-download", "data"),
    Input("btn-vtp-download", "n_clicks"),
    State("vtp-file-table", "selected_rows"),
    State("vtp-file-table", "data"),
    State("tbl-concrete", "selected_rows"),
    State("tbl-concrete", "data"),
    prevent_initial_call=True,
)
def download_selected_vtp_files(n_clicks, selected_rows, table_data, selected_conc_rows, tbl_data):
    from dash.exceptions import PreventUpdate
    import io, zipfile, os
    if not n_clicks or not selected_rows or not selected_conc_rows or not tbl_data:
        raise PreventUpdate
    row = pd.DataFrame(tbl_data).iloc[selected_conc_rows[0]]
    concrete_pk = row["concrete_pk"]
    vtp_dir = os.path.join("assets/vtp", str(concrete_pk))
    files = [table_data[i]["filename"] for i in selected_rows]
    if not files:
        raise PreventUpdate
    # zip 파일 메모리 생성
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zf:
        for fname in files:
            fpath = os.path.join(vtp_dir, fname)
            if os.path.exists(fpath):
                zf.write(fpath, arcname=fname)
    zip_buffer.seek(0)
    return dcc.send_bytes(zip_buffer.getvalue(), filename=f"vtp_files_{concrete_pk}.zip")

# 전체 선택/해제 콜백 (vtp)
@callback(
    Output("vtp-file-table", "selected_rows"),
    Input("btn-vtp-select-all", "n_clicks"),
    Input("btn-vtp-deselect-all", "n_clicks"),
    State("vtp-file-table", "data"),
    prevent_initial_call=True,
)
def select_deselect_all_vtp(n_all, n_none, table_data):
    import dash
    ctx = dash.callback_context
    if not ctx.triggered or not table_data:
        raise dash.exceptions.PreventUpdate
    trig = ctx.triggered_id
    if trig == "btn-vtp-select-all":
        return list(range(len(table_data)))
    elif trig == "btn-vtp-deselect-all":
        return []
    raise dash.exceptions.PreventUpdate

# 수치해석 3D 뷰 콜백 (필드/프리셋/시간)
@callback(
    Output("analysis-3d-viewer", "children"),
    Output("analysis-current-file-label", "children"),
    Input("analysis-field-dropdown", "value"),
    Input("analysis-preset-dropdown", "value"),
    Input("analysis-time-slider", "value"),
    State("tbl-concrete", "selected_rows"),
    State("tbl-concrete", "data"),
    prevent_initial_call=True,
)
def update_analysis_3d_view(field_name, preset, time_idx, selected_rows, tbl_data):
    import os
    import vtk
    from dash_vtk.utils import to_mesh_state
    
    if not selected_rows or not tbl_data:
        return html.Div("콘크리트를 선택하세요."), ""
    
    row = pd.DataFrame(tbl_data).iloc[selected_rows[0]]
    concrete_pk = row["concrete_pk"]
    assets_vtk_dir = f"assets/vtk/{concrete_pk}"
    assets_vtp_dir = f"assets/vtp/{concrete_pk}"
    
    vtk_files = []
    vtp_files = []
    if os.path.exists(assets_vtk_dir):
        vtk_files = sorted([f for f in os.listdir(assets_vtk_dir) if f.endswith('.vtk')])
    if os.path.exists(assets_vtp_dir):
        vtp_files = sorted([f for f in os.listdir(assets_vtp_dir) if f.endswith('.vtp')])
    
    if not vtk_files and not vtp_files:
        return html.Div("VTK/VTP 파일이 없습니다."), ""
    
    from datetime import datetime
    times = []
    file_type = None
    files = []
    
    if vtk_files:
        files = vtk_files
        file_type = 'vtk'
    elif vtp_files:
        files = vtp_files
        file_type = 'vtp'
    
    for f in files:
        try:
            time_str = os.path.splitext(f)[0]
            dt = datetime.strptime(time_str, "%Y%m%d%H")
            times.append((dt, f))
        except:
            continue
    
    if not times:
        return html.Div("시간 정보가 포함된 VTK/VTP 파일이 없습니다.")
    
    times.sort()
    max_idx = len(times) - 1
    
    # 시간 인덱스 처리
    if time_idx is None:
        idx = max_idx
    else:
        idx = min(int(time_idx), max_idx)
    
    selected_file = times[idx][1]
    file_path = os.path.join(assets_vtk_dir if file_type=='vtk' else assets_vtp_dir, selected_file)
    
    try:
        # VTK 파일 읽기
        if file_type == 'vtk':
            reader = vtk.vtkUnstructuredGridReader()
            reader.SetFileName(file_path)
            reader.Update()
            ds = reader.GetOutput()
        else:
            reader = vtk.vtkXMLPolyDataReader()
            reader.SetFileName(file_path)
            reader.Update()
            ds = reader.GetOutput()
        
        # UnstructuredGrid → PolyData 변환 (GeometryFilter)  ⭐ 추가
        if isinstance(ds, vtk.vtkUnstructuredGrid):
            geom_filter = vtk.vtkGeometryFilter()
            geom_filter.SetInputData(ds)
            geom_filter.Update()
            ds = geom_filter.GetOutput()
        
        # 데이터 검증
        if ds is None:
            return html.Div([
                html.H5("VTK 파일 읽기 실패", style={"color": "red"}),
                html.P(f"파일: {selected_file}")
            ])
        
        # 점의 개수 확인
        num_points = ds.GetNumberOfPoints()
        if num_points == 0:
            return html.Div([
                html.H5("빈 데이터셋", style={"color": "red"}),
                html.P(f"파일: {selected_file}"),
                html.P("점이 없는 데이터셋입니다.")
            ])
        
        # 필드 데이터 검증
        if field_name:
            arr = ds.GetPointData().GetArray(field_name)
            if arr is None:
                field_name = None  # 필드가 없으면 기본 시각화로 변경
        
        # 메시 상태 생성 (더 안전한 방식)
        try:
            if field_name:
                mesh_state = to_mesh_state(ds, field_name)
            else:
                mesh_state = to_mesh_state(ds)
            
            # mesh_state 검증
            if mesh_state is None or not isinstance(mesh_state, dict):
                raise ValueError("mesh_state가 올바르지 않습니다")
            
            # mesh_state 구조는 dash_vtk 버전에 따라 다릅니다.
            # 'mesh' 키 또는 'points' 키 중 하나라도 있으면 정상으로 간주
            if not (('mesh' in mesh_state) or ('points' in mesh_state)):
                raise ValueError("mesh_state에 필수 데이터가 없습니다")
            
        except Exception as mesh_error:
            print(f"mesh_state 생성 오류: {mesh_error}")
            return html.Div([
                html.H5("메시 생성 오류", style={"color": "red"}),
                html.P(f"파일: {selected_file}"),
                html.P(f"오류: {str(mesh_error)}"),
                html.P(f"점 개수: {num_points}"),
                html.Hr(),
                html.P("VTK 파일 형식을 확인해주세요. FRD → VTK 변환이 올바르게 되었는지 점검이 필요합니다.", style={"color": "gray"})
            ]), f"파일: {selected_file}"
        
        # 컬러 데이터 범위 추출
        color_range = None
        if field_name:
            arr = ds.GetPointData().GetArray(field_name)
            if arr is not None:
                range_val = arr.GetRange()
                if range_val[0] != range_val[1]:  # 값이 모두 같지 않을 때만 범위 설정
                    color_range = [range_val[0], range_val[1]]
        
        # 기본 프리셋 설정
        if not preset:
            preset = "rainbow"
        
        # dash_vtk 컴포넌트 생성 (더 안전한 방식)
        try:
            geometry_rep = dash_vtk.GeometryRepresentation(
                colorMapPreset=preset,
                children=[dash_vtk.Mesh(state=mesh_state)]
            )
            
            # 컬러 범위가 있을 때만 설정
            if color_range:
                geometry_rep.colorDataRange = color_range
            
            # --- Bounding box wireframe 추가 ---
            try:
                bounds = ds.GetBounds()  # (xmin,xmax,ymin,ymax,zmin,zmax)
                xmin,xmax,ymin,ymax,zmin,zmax = bounds
                import vtk
                pts = vtk.vtkPoints()
                corners = [
                    (xmin,ymin,zmin), (xmax,ymin,zmin), (xmax,ymax,zmin), (xmin,ymax,zmin),
                    (xmin,ymin,zmax), (xmax,ymin,zmax), (xmax,ymax,zmax), (xmin,ymax,zmax)
                ]
                for p in corners:
                    pts.InsertNextPoint(*p)
                lines = vtk.vtkCellArray()
                edges = [
                    (0,1),(1,2),(2,3),(3,0),  # bottom
                    (4,5),(5,6),(6,7),(7,4),  # top
                    (0,4),(1,5),(2,6),(3,7)   # vertical
                ]
                for a,b in edges:
                    line = vtk.vtkLine()
                    line.GetPointIds().SetId(0,a)
                    line.GetPointIds().SetId(1,b)
                    lines.InsertNextCell(line)
                poly = vtk.vtkPolyData()
                poly.SetPoints(pts)
                poly.SetLines(lines)
                bbox_state = to_mesh_state(poly)
                bbox_rep = dash_vtk.GeometryRepresentation(
                    color=[0,0,0],  # black
                    opacity=0.3,
                    children=[dash_vtk.Mesh(state=bbox_state)]
                )
                view_children = [geometry_rep, bbox_rep]
            except Exception:
                view_children = [geometry_rep]
            
            vtk_viewer = dash_vtk.View(view_children, style={"height": "60vh", "width": "100%"})
            
            label = f"파일: {selected_file}"
            if color_range:
                label += f" | 값 범위: {color_range[0]:.2f} ~ {color_range[1]:.2f}"
            return vtk_viewer, label
            
        except Exception as vtk_error:
            print(f"dash_vtk 컴포넌트 생성 오류: {vtk_error}")
            return html.Div([
                html.H5("3D 뷰어 생성 오류", style={"color": "red"}),
                html.P(f"파일: {selected_file}"),
                html.P(f"오류: {str(vtk_error)}"),
                html.Hr(),
                html.P("브라우저를 새로고침하거나 다른 파일을 선택해보세요.", style={"color": "gray"})
            ]), f"파일: {selected_file}"
        
    except Exception as e:
        print(f"VTK 처리 전체 오류: {e}")
        return html.Div([
            html.H5("VTK/VTP 파싱 오류", style={"color": "red"}),
            html.P(f"파일: {selected_file}"),
            html.P(f"파일 타입: {file_type}"),
            html.P(f"오류: {str(e)}"),
            html.Hr(),
            html.P("다른 파일을 선택하거나 VTK 파일을 확인해주세요.", style={"color": "gray"})
        ]), f"파일: {selected_file}"
