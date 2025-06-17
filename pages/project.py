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
                            dbc.Tab(label="온도분포", tab_id="tab-temp"),
                            dbc.Tab(label="수치해석", tab_id="tab-analysis"),
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
    Output("viewer-3d-store", "data"),
    Output("time-slider", "min", allow_duplicate=True),
    Output("time-slider", "max", allow_duplicate=True),
    Output("time-slider", "marks", allow_duplicate=True),
    Output("time-slider", "value", allow_duplicate=True),
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
        return dash.no_update, dash.no_update, dash.no_update, dash.no_update, 0, 5, {}, 0
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

    # 노드번호 기준으로 온도와 좌표를 매칭해서 배열 생성
    x_coords = []
    y_coords = []
    z_coords = []
    temps = []
    for node_id, node in nodes.items():
        if node_id in temperatures:
            x_coords.append(node['x'])
            y_coords.append(node['y'])
            z_coords.append(node['z'])
            temps.append(temperatures[node_id])
    x_coords = np.array(x_coords)
    y_coords = np.array(y_coords)
    z_coords = np.array(z_coords)
    temps = np.array(temps)

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
    
    return fig_3d, current_time, current_file_title, viewer_data, 0, max_idx, marks, value

# 탭 콘텐츠 처리 콜백
@callback(
    Output("tab-content", "children"),
    Input("tabs-main", "active_tab"),
    State("tbl-concrete", "selected_rows"),
    State("tbl-concrete", "data"),
    State("viewer-3d-store", "data"),
    prevent_initial_call=True,
)
def switch_tab(active_tab, selected_rows, tbl_data, viewer_data):
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
        ])
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
            # 입력창 (x, y, z)
            html.Div([
                html.Label("단면 위치 설정", className="mb-2"),
                dbc.Row([
                    dbc.Col([
                        dbc.InputGroup([
                            dbc.InputGroupText("X"),
                            dcc.Input(id="section-x-input", type="number", step=0.1, value=None, className="form-control", inputMode="numeric", style={"width": "100%"}),
                        ]),
                    ], width=4),
                    dbc.Col([
                        dbc.InputGroup([
                            dbc.InputGroupText("Y"),
                            dcc.Input(id="section-y-input", type="number", step=0.1, value=None, className="form-control", inputMode="numeric", style={"width": "100%"}),
                        ]),
                    ], width=4),
                    dbc.Col([
                        dbc.InputGroup([
                            dbc.InputGroupText("Z"),
                            dcc.Input(id="section-z-input", type="number", step=0.1, value=None, className="form-control", inputMode="numeric", style={"width": "100%"}),
                        ]),
                    ], width=4),
                ], className="g-2 mb-2"),
            ], style={"padding": "10px"}),
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
            # 2x2+컬러바 배열 배치
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
                ], md=10),
                dbc.Col([
                    dcc.Graph(id="section-colorbar", style={"height": "66vh", "width": "80px", "marginLeft": "-30px", "display": "block"}),
                ], md=2),
            ]),
        ])
    elif active_tab == "tab-temp":
        return html.Div([
            html.H4("온도분포", className="text-center mt-5"),
            html.P("준비 중입니다...", className="text-center text-muted"),
        ])
    elif active_tab == "tab-analysis":
        return html.Div([
            html.H4("수치해석", className="text-center mt-5"),
            html.P("준비 중입니다...", className="text-center text-muted"),
        ])
    return html.Div()

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

# 단면도 탭 콜백: 3D 뷰(작게)와 X/Y/Z 단면도, 입력창 min/max 자동 설정
@callback(
    Output("viewer-3d-section", "figure"),
    Output("viewer-section-x", "figure"),
    Output("viewer-section-y", "figure"),
    Output("viewer-section-z", "figure"),
    Output("section-x-input", "min"), Output("section-x-input", "max"), Output("section-x-input", "value"),
    Output("section-y-input", "min"), Output("section-y-input", "max"), Output("section-y-input", "value"),
    Output("section-z-input", "min"), Output("section-z-input", "max"), Output("section-z-input", "value"),
    Output("section-colorbar", "figure"),
    Input("time-slider-section", "value"),
    Input("section-x-input", "value"),
    Input("section-y-input", "value"),
    Input("section-z-input", "value"),
    State("section-x-input", "value"),
    State("section-y-input", "value"),
    State("section-z-input", "value"),
    State("tbl-concrete", "selected_rows"),
    State("tbl-concrete", "data"),
    prevent_initial_call=False,
)
def update_section_views(time_idx, x_val, y_val, z_val, prev_x, prev_y, prev_z, selected_rows, tbl_data):
    import math
    import plotly.graph_objects as go
    import numpy as np
    from scipy.interpolate import griddata
    if not selected_rows:
        return go.Figure(), go.Figure(), go.Figure(), go.Figure(), 0, 1, 0.5, 0, 1, 0.5, 0, 1, 0.5, go.Figure()
    row = pd.DataFrame(tbl_data).iloc[selected_rows[0]]
    concrete_pk = row["concrete_pk"]
    inp_dir = f"inp/{concrete_pk}"
    inp_files = sorted(glob.glob(f"{inp_dir}/*.inp"))
    if not inp_files:
        return go.Figure(), go.Figure(), go.Figure(), go.Figure(), 0, 1, 0.5, 0, 1, 0.5, 0, 1, 0.5, go.Figure()
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
    x_coords = []
    y_coords = []
    z_coords = []
    temps = []
    for node_id, node in nodes.items():
        if node_id in temperatures:
            x_coords.append(node['x'])
            y_coords.append(node['y'])
            z_coords.append(node['z'])
            temps.append(temperatures[node_id])
    x_coords = np.array(x_coords)
    y_coords = np.array(y_coords)
    z_coords = np.array(z_coords)
    temps = np.array(temps)
    tmin, tmax = float(np.nanmin(temps)), float(np.nanmax(temps))
    # 입력창 min/max/기본값 자동 설정
    x_min, x_max = float(np.min(x_coords)), float(np.max(x_coords))
    y_min, y_max = float(np.min(y_coords)), float(np.max(y_coords))
    z_min, z_max = float(np.min(z_coords)), float(np.max(z_coords))
    x_mid = float(np.median(x_coords))
    y_mid = float(np.median(y_coords))
    z_mid = float(np.median(z_coords))
    # 최초 진입 시에만 중앙값, 이후에는 사용자가 조작한 값 유지
    def ensure_scalar(val, default):
        # 리스트/배열이면 첫 번째 값만 사용
        if isinstance(val, (list, np.ndarray)):
            if len(val) > 0:
                return float(val[0])
            else:
                return float(default)
        elif val is not None:
            return float(val)
        else:
            return float(default)
    x0 = ensure_scalar(x_val, x_mid)
    y0 = ensure_scalar(y_val, y_mid)
    z0 = ensure_scalar(z_val, z_mid)
    # 디버깅용: 실제 값과 shape 출력
    print(f"[DEBUG] x0: {x0}, type: {type(x0)}, y0: {y0}, type: {type(y0)}, z0: {z0}, type: {type(z0)}")
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
    # 콘크리트 외곽선(모서리) 항상 표시
    try:
        dims = ast.literal_eval(row["dims"]) if isinstance(row["dims"], str) else row["dims"]
        poly_nodes = np.array(dims["nodes"])
        poly_h = float(dims["h"])
        n = len(poly_nodes)
        x0, y0 = poly_nodes[:,0], poly_nodes[:,1]
        z0 = np.zeros(n)
        x1, y1 = x0, y0
        z1 = np.full(n, poly_h)
        fig_3d.add_trace(go.Scatter3d(
            x=np.append(x0, x0[0]), y=np.append(y0, y0[0]), z=np.append(z0, z0[0]),
            mode='lines', line=dict(width=3, color='black'), showlegend=False, hoverinfo='skip'))
        fig_3d.add_trace(go.Scatter3d(
            x=np.append(x1, x1[0]), y=np.append(y1, y1[0]), z=np.append(z1, z1[0]),
            mode='lines', line=dict(width=3, color='black'), showlegend=False, hoverinfo='skip'))
        for i in range(n):
            fig_3d.add_trace(go.Scatter3d(
                x=[x0[i], x1[i]], y=[y0[i], y1[i]], z=[z0[i], z1[i]],
                mode='lines', line=dict(width=3, color='black'), showlegend=False, hoverinfo='skip'))
    except Exception:
        pass
    # 컬러바(3D 뷰 기준)만 따로 생성
    colorbar_fig = go.Figure()
    colorbar_fig.add_trace(go.Scatter(
        x=[None], y=[None],
        mode='markers',
        marker=dict(
            colorscale=[[0, 'blue'], [1, 'red']],
            cmin=tmin, cmax=tmax,
            colorbar=dict(
                title=dict(text='온도 (°C)', font=dict(size=18)),
                thickness=30,
                len=0.95,
                y=0.5,
                yanchor='middle',
                tickfont=dict(size=16),
                outlinewidth=1,
                outlinecolor='black',
                ticks='outside',
                ticklen=8,
            ),
            showscale=True,
        ),
        showlegend=False
    ))
    colorbar_fig.update_layout(
        margin=dict(l=0, r=0, t=0, b=0),
        width=90, height=420,
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)'
    )
    # X/Y/Z 단면도(Heatmap) 복구
    tol = 0.05
    # X 단면
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
                x=y_bins, y=z_bins, z=grid.T, colorscale=[[0, 'blue'], [1, 'red']],
                zmin=tmin, zmax=tmax, showscale=False, zsmooth='best'))
        else:
            fig_x = go.Figure()
    else:
        fig_x = go.Figure()
    fig_x.update_layout(title=f"X={x0:.2f}m 단면", xaxis_title="Y (m)", yaxis_title="Z (m)", margin=dict(l=0, r=0, b=0, t=30))
    # Y 단면
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
                x=x_bins, y=z_bins, z=grid.T, colorscale=[[0, 'blue'], [1, 'red']],
                zmin=tmin, zmax=tmax, showscale=False, zsmooth='best'))
        else:
            fig_y = go.Figure()
    else:
        fig_y = go.Figure()
    fig_y.update_layout(title=f"Y={y0:.2f}m 단면", xaxis_title="X (m)", yaxis_title="Z (m)", margin=dict(l=0, r=0, b=0, t=30))
    # Z 단면
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
                x=x_bins, y=y_bins, z=grid.T, colorscale=[[0, 'blue'], [1, 'red']],
                zmin=tmin, zmax=tmax, showscale=False, zsmooth='best'))
        else:
            fig_z = go.Figure()
    else:
        fig_z = go.Figure()
    fig_z.update_layout(title=f"Z={z0:.2f}m 단면", xaxis_title="X (m)", yaxis_title="Y (m)", margin=dict(l=0, r=0, b=0, t=30))
    # step=0.1로 반환
    return fig_3d, fig_x, fig_y, fig_z, x_min, x_max, x0, y_min, y_max, y0, z_min, z_max, z0, colorbar_fig
