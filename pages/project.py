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
                        # 3D 히트맵 뷰어
                        dcc.Graph(
                            id="viewer-heatmap",
                            style={"height": "60vh"},
                            config={"scrollZoom": True},
                        ),
                        # 시간 슬라이더
                        html.Div([
                            html.Label("시간", className="form-label"),
                            dcc.Slider(
                                id="time-slider",
                                min=0,
                                max=100,
                                step=1,
                                value=0,
                                marks={},
                                tooltip={"placement": "bottom", "always_visible": True},
                            ),
                        ], className="mt-3"),
                        # 단면도 조절 슬라이더
                        html.Div([
                            html.Label("단면도 높이 (m)", className="form-label"),
                            dcc.Slider(
                                id="section-slider",
                                min=0,
                                max=100,
                                step=1,
                                value=50,
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
        return [], [], [], True, True, "", 0, 100, 0, {}, None

    # 1) 프로젝트 정보 로드
    try:
        proj_row = api_db.get_project_data(project_pk=selected_proj).iloc[0]
        proj_name = proj_row["name"]
    except Exception:
        return [], [], [], True, True, "프로젝트 정보를 불러올 수 없음", 0, 100, 0, {}, None

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
    return table_data, columns, [], True, True, title, 0, 100, 0, {}, None

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
        return True, True, 0, 100, 0, {}, None
    
    # 선택된 콘크리트의 activate 상태 확인
    row = pd.DataFrame(tbl_data).iloc[selected_rows[0]]
    is_active = row["activate"] == "활성"
    concrete_pk = row["concrete_pk"]
    
    # inp 파일 목록 조회
    inp_dir = f"inp/{concrete_pk}"
    if not os.path.exists(inp_dir):
        return False, not is_active, 0, 100, 0, {}, None
    
    # inp 파일 시간 목록 생성
    inp_files = sorted(glob.glob(f"{inp_dir}/*.inp"))
    if not inp_files:
        return False, not is_active, 0, 100, 0, {}, None
    
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
        return False, not is_active, 0, 100, 0, {}, None
    
    # 슬라이더 마크 생성
    marks = {}
    for i, t in enumerate(times):
        if i % 6 == 0:  # 6시간 간격으로 마크 표시
            marks[i] = t.strftime("%m/%d %H:00")
    
    return False, not is_active, 0, len(times)-1, 0, marks, times[0].strftime("%Y%m%d%H")

# ───────────────────── ④ 시간 슬라이더 콜백 ─────────────────────
@callback(
    Output("current-time-store", "data", allow_duplicate=True),
    Output("viewer-heatmap", "figure"),
    Input("time-slider", "value"),
    Input("section-slider", "value"),
    State("tbl-concrete", "selected_rows"),
    State("tbl-concrete", "data"),
    State("current-time-store", "data"),
    prevent_initial_call=True,
)
def update_heatmap(time_idx, section_height, selected_rows, tbl_data, current_time):
    if not selected_rows:
        raise PreventUpdate
    
    # 선택된 콘크리트 정보
    row = pd.DataFrame(tbl_data).iloc[selected_rows[0]]
    concrete_pk = row["concrete_pk"]
    
    # inp 파일 목록 조회
    inp_dir = f"inp/{concrete_pk}"
    if not os.path.exists(inp_dir):
        raise PreventUpdate
    
    # inp 파일 시간 목록 생성
    inp_files = sorted(glob.glob(f"{inp_dir}/*.inp"))
    if not inp_files or time_idx >= len(inp_files):
        raise PreventUpdate
    
    # 현재 시간의 inp 파일 읽기
    current_file = inp_files[time_idx]
    current_time = os.path.basename(current_file).split(".")[0]
    
    try:
        # inp 파일 읽기
        with open(current_file, 'r') as f:
            lines = f.readlines()
        
        # 노드 정보 파싱
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
        
        # 온도 정보 파싱
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
        
        # 3D 데이터 준비
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
        
        # 단면도 높이에 해당하는 z 값 계산
        z_min = min(z_coords)
        z_max = max(z_coords)
        section_z = z_min + (z_max - z_min) * (section_height / 100)
        
        # 3D 히트맵 생성
        fig = go.Figure()
        
        # 전체 3D 히트맵
        fig.add_trace(go.Scatter3d(
            x=x_coords,
            y=y_coords,
            z=z_coords,
            mode='markers',
            marker=dict(
                size=5,
                color=temps,
                colorscale='RdBu',
                showscale=True,
                colorbar=dict(title='Temperature (°C)')
            ),
            name='3D View'
        ))
        
        # 단면도
        section_mask = [abs(z - section_z) < 0.1 for z in z_coords]
        if any(section_mask):
            fig.add_trace(go.Scatter3d(
                x=[x for i, x in enumerate(x_coords) if section_mask[i]],
                y=[y for i, y in enumerate(y_coords) if section_mask[i]],
                z=[z for i, z in enumerate(z_coords) if section_mask[i]],
                mode='markers',
                marker=dict(
                    size=8,
                    color=[t for i, t in enumerate(temps) if section_mask[i]],
                    colorscale='RdBu',
                    showscale=False
                ),
                name='Section View'
            ))
        
        # 레이아웃 설정
        fig.update_layout(
            title=f"시간: {current_time}",
            scene=dict(
                xaxis_title="X (m)",
                yaxis_title="Y (m)",
                zaxis_title="Z (m)",
                aspectmode='data'
            ),
            margin=dict(l=0, r=0, b=0, t=30),
            showlegend=True
        )
        
        return current_time, fig
        
    except Exception as e:
        print(f"Error reading inp file: {e}")
        raise PreventUpdate

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
