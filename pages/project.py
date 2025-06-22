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
    dash_table, register_page, callback, clientside_callback
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
        
        # 키보드 이벤트를 위한 JavaScript (서버 부하 없음)
        html.Div([
            html.Script("""
                window.addEventListener('load', function() {
                    if (!window.sliderKeyboardHandler) {
                        window.sliderKeyboardHandler = true;
                        
                        document.addEventListener('keydown', function(event) {
                            // 입력 필드에서는 무시
                            if (event.target.tagName === 'INPUT' || 
                                event.target.tagName === 'TEXTAREA' ||
                                event.target.isContentEditable) {
                                return;
                            }
                            
                            if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
                                event.preventDefault();
                                
                                // 현재 보이는 슬라이더 찾기
                                const sliders = ['time-slider', 'time-slider-section', 'analysis-time-slider'];
                                let activeSlider = null;
                                
                                for (const sliderId of sliders) {
                                    const slider = document.getElementById(sliderId);
                                    if (slider && slider.offsetParent !== null) { // 보이는 슬라이더
                                        activeSlider = slider;
                                        break;
                                    }
                                }
                                
                                if (activeSlider) {
                                    const handle = activeSlider.querySelector('.rc-slider-handle');
                                    if (handle) {
                                        const current = parseInt(handle.getAttribute('aria-valuenow') || '0');
                                        const min = parseInt(handle.getAttribute('aria-valuemin') || '0');
                                        const max = parseInt(handle.getAttribute('aria-valuemax') || '100');
                                        
                                        let newValue = current;
                                        if (event.key === 'ArrowLeft' && current > min) {
                                            newValue = current - 1;
                                        } else if (event.key === 'ArrowRight' && current < max) {
                                            newValue = current + 1;
                                        }
                                        
                                        if (newValue !== current) {
                                            // 슬라이더 값 직접 설정
                                            const percentage = (newValue - min) / (max - min) * 100;
                                            
                                            // 핸들 위치 업데이트
                                            handle.style.left = percentage + '%';
                                            handle.setAttribute('aria-valuenow', newValue);
                                            
                                            // 트랙 업데이트
                                            const track = activeSlider.querySelector('.rc-slider-track');
                                            if (track) {
                                                track.style.width = percentage + '%';
                                            }
                                            
                                            // 툴팁 업데이트
                                            const tooltip = activeSlider.querySelector('.rc-slider-tooltip-content');
                                            if (tooltip) {
                                                tooltip.textContent = newValue;
                                            }
                                            
                                            // Dash 콜백 트리거 (React 이벤트)
                                            setTimeout(function() {
                                                const changeEvent = new Event('input', { bubbles: true });
                                                Object.defineProperty(changeEvent, 'target', {
                                                    value: { value: newValue },
                                                    enumerable: true
                                                });
                                                activeSlider.dispatchEvent(changeEvent);
                                                
                                                // 추가 이벤트
                                                const changeEvent2 = new Event('change', { bubbles: true });
                                                Object.defineProperty(changeEvent2, 'target', {
                                                    value: { value: newValue },
                                                    enumerable: true
                                                });
                                                activeSlider.dispatchEvent(changeEvent2);
                                            }, 50);
                                        }
                                    }
                                }
                            }
                        });
                    }
                });
            """)
        ], style={"display": "none"}),

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
                        html.Small("💡 컬럼 헤더를 클릭하여 정렬할 수 있습니다", className="text-muted mb-2 d-block"),
                        dash_table.DataTable(
                            id="tbl-concrete",
                            page_size=10,
                            row_selectable="single",
                            sort_action="native",
                            sort_mode="single",
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
                    md=3,  # 2에서 3으로 변경 (1.5배)
                ),
                dbc.Col(
                    [
                        html.H6(id="concrete-title", className="mb-2"),
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
                                html.Div("", style={"textAlign": "center", "fontSize": "14px", "color": "#666", "marginTop": "8px"}),
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
                    md=9,  # 10에서 9로 변경 (3+9=12)
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
    Output("tbl-concrete", "style_data_conditional"),
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
        return [], [], [], [], True, True, "", 0, 5, 0, {}, None

    # 1) 프로젝트 정보 로드
    try:
        proj_row = api_db.get_project_data(project_pk=selected_proj).iloc[0]
        proj_name = proj_row["name"]
    except Exception:
        return [], [], [], [], True, True, "프로젝트 정보를 불러올 수 없음", 0, 5, 0, {}, None

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
        
        # 센서 데이터 확인
        concrete_pk = row["concrete_pk"]
        df_sensors = api_db.get_sensors_data(concrete_pk=concrete_pk)
        has_sensors = not df_sensors.empty
        
        # 상태 결정 (정렬을 위해 우선순위도 함께 설정)
        if row["activate"] == 1:  # 활성
            if has_sensors:
                status = "분석 가능"
                status_color = "#cce5ff"  # 연한 파란색
                status_sort = 2  # 두 번째 우선순위
            else:
                status = "센서 부족"
                status_color = "#fff3cd"  # 연한 노란색
                status_sort = 3  # 세 번째 우선순위
        else:  # 비활성 (activate == 0)
            status = "분석중"
            status_color = "#d4edda"  # 연한 초록색
            status_sort = 1  # 첫 번째 우선순위
        
        # 타설날짜 포맷팅
        pour_date = "N/A"
        if row.get("con_t") and row["con_t"] not in ["", "N/A", None]:
            try:
                from datetime import datetime
                # datetime 객체인 경우
                if hasattr(row["con_t"], 'strftime'):
                    dt = row["con_t"]
                # 문자열인 경우 파싱
                elif isinstance(row["con_t"], str):
                    if 'T' in row["con_t"]:
                        # ISO 형식 (2024-01-01T10:00 또는 2024-01-01T10:00:00)
                        dt = datetime.fromisoformat(row["con_t"].replace('Z', ''))
                    else:
                        # 다른 형식 시도
                        dt = datetime.strptime(str(row["con_t"]), '%Y-%m-%d %H:%M:%S')
                else:
                    dt = None
                
                if dt:
                    pour_date = dt.strftime('%y.%m.%d')
            except Exception:
                pour_date = "N/A"
        
        # 경과일 계산 (현재 시간 - 타설일)
        elapsed_days = "N/A"
        if pour_date != "N/A":
            try:
                from datetime import datetime
                pour_dt = datetime.strptime(pour_date, '%y.%m.%d')
                now = datetime.now()
                elapsed = (now - pour_dt).days
                elapsed_days = f"{elapsed}일"
            except Exception:
                elapsed_days = "N/A"
        
        table_data.append({
            "concrete_pk": row["concrete_pk"],
            "name": row["name"],
            "status": status,
            "status_color": status_color,
            "status_sort": status_sort,  # 정렬용 숨겨진 필드
            "pour_date": pour_date,
            "elapsed_days": elapsed_days,
            "shape": shape_info,
            "dims": row["dims"],
            "activate": "활성" if row["activate"] == 1 else "비활성",
            "has_sensors": has_sensors,
        })

    # 3) 테이블 컬럼 정의
    columns = [
        {"name": "이름", "id": "name", "type": "text"},
        {"name": "상태", "id": "status", "type": "text"},
        {"name": "타설일", "id": "pour_date", "type": "text"},
        {"name": "경과일", "id": "elapsed_days", "type": "numeric"},
    ]

    title = f"{proj_name} · 콘크리트 전체"
    
    # 테이블 스타일 설정 (상태별 색상)
    style_data_conditional = []
    for i, data in enumerate(table_data):
        # 상태별 텍스트 색상 설정
        if data['status'] == '분석중':
            text_color = '#155724'  # 진한 초록색
        elif data['status'] == '분석 가능':
            text_color = '#004085'  # 진한 파란색
        elif data['status'] == '센서 부족':
            text_color = '#856404'  # 진한 노란색(갈색)
        else:
            text_color = '#212529'  # 기본 색상
            
        style_data_conditional.append({
            'if': {'row_index': i, 'column_id': 'status'},
            'backgroundColor': data['status_color'],
            'color': text_color,
            'fontWeight': 'bold'
        })
    
    # 날짜 및 경과일 컬럼 스타일 추가
    style_data_conditional.extend([
        {
            'if': {'column_id': 'pour_date'},
            'fontSize': '0.85rem',
            'color': '#6c757d'
        },
        {
            'if': {'column_id': 'elapsed_days'},
            'fontSize': '0.85rem',
            'color': '#495057',
            'fontWeight': '500'
        }
    ])
    
    # 상태별 기본 정렬 적용 (분석중 → 분석 가능 → 센서 부족)
    if table_data:
        table_data = sorted(table_data, key=lambda x: x.get('status_sort', 999))
    
    return table_data, columns, [], style_data_conditional, True, True, title, 0, 5, 0, {}, None

# ───────────────────── ③ 콘크리트 선택 콜백 ────────────────────
@callback(
    Output("btn-concrete-del", "disabled", allow_duplicate=True),
    Output("btn-concrete-analyze", "disabled", allow_duplicate=True),
    Output("concrete-title", "children", allow_duplicate=True),
    Output("current-file-title-store", "data", allow_duplicate=True),
    Output("time-slider", "min", allow_duplicate=True),
    Output("time-slider", "max", allow_duplicate=True),
    Output("time-slider", "value", allow_duplicate=True),
    Output("time-slider", "marks", allow_duplicate=True),
    Input("tbl-concrete", "selected_rows"),
    State("tbl-concrete", "data"),
    prevent_initial_call=True,
)
def on_concrete_select(selected_rows, tbl_data):
    if not selected_rows:
        return True, True, "", "", 0, 5, 0, {}
    
    row = pd.DataFrame(tbl_data).iloc[selected_rows[0]]
    is_active = row["activate"] == "활성"
    has_sensors = row["has_sensors"]
    concrete_pk = row["concrete_pk"]
    
    # 버튼 상태 결정
    # 활성도가 1이고 센서가 있으면: 분석 시작 활성화, 삭제 비활성화
    # 나머지 경우: 분석 시작 비활성화, 삭제 활성화
    can_analyze = is_active and has_sensors
    analyze_disabled = not can_analyze
    delete_disabled = can_analyze
    
    # 초기값 설정
    current_file_title = ""
    slider_min, slider_max, slider_value = 0, 5, 0
    slider_marks = {}
    
    # 안내 메시지 생성
    if can_analyze:
        title = "⚠️ 분석을 시작하려면 왼쪽의 '분석 시작' 버튼을 클릭하세요."
    elif is_active and not has_sensors:
        title = "⚠️ 센서가 부족합니다. 센서를 추가한 후 분석을 시작하세요."
    else:
        # 비활성 상태일 때 데이터 존재 여부 확인 및 초기 파일 정보 로드
        inp_dir = f"inp/{concrete_pk}"
        inp_files = sorted(glob.glob(f"{inp_dir}/*.inp"))
        if not inp_files:
            title = "⏳ 아직 수집된 데이터가 없습니다. 잠시 후 다시 확인해주세요."
        else:
            title = ""
            
            # 시간 파싱 및 슬라이더 설정
            times = []
            for f in inp_files:
                try:
                    time_str = os.path.basename(f).split(".")[0]
                    dt = datetime.strptime(time_str, "%Y%m%d%H")
                    times.append(dt)
                except:
                    continue
            
            if times:
                max_idx = len(times) - 1
                slider_min, slider_max = 0, max_idx
                slider_value = max_idx  # 최신 파일로 초기화
                slider_marks = {0: times[0].strftime("%m/%d"), max_idx: times[-1].strftime("%m/%d")}
                
                # 최신 파일의 온도 통계 계산
                latest_file = inp_files[max_idx]
                try:
                    # 시간 형식을 읽기 쉽게 변환
                    from datetime import datetime as dt_module
                    time_str = os.path.basename(latest_file).split(".")[0]
                    dt = dt_module.strptime(time_str, "%Y%m%d%H")
                    formatted_time = dt.strftime("%Y년 %m월 %d일 %H시")
                    
                    # 온도 데이터 파싱
                    with open(latest_file, 'r') as f:
                        lines = f.readlines()
                    
                    current_temps = []
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
                        current_file_title = f"{formatted_time} (최저: {current_min:.1f}°C, 최고: {current_max:.1f}°C, 평균: {current_avg:.1f}°C)"
                    else:
                        current_file_title = f"{formatted_time}"
                        
                except Exception as e:
                    print(f"온도 데이터 파싱 오류: {e}")
                    current_file_title = f"{os.path.basename(latest_file)}"
            
    return delete_disabled, analyze_disabled, title, current_file_title, slider_min, slider_max, slider_value, slider_marks

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
    Output("viewer-3d-store", "data"),
    Output("time-slider", "min", allow_duplicate=True),
    Output("time-slider", "max", allow_duplicate=True),
    Output("time-slider", "marks", allow_duplicate=True),
    Output("time-slider", "value", allow_duplicate=True),
    Output("current-file-title-store", "data", allow_duplicate=True),
    Input("time-slider", "value"),
    Input("section-coord-store", "data"),
    Input("tbl-concrete", "selected_rows"),
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
    # 슬라이더 마크: 모든 시간을 일 단위로 표시
    max_idx = len(times) - 1
    marks = {}
    seen_dates = set()
    for i, dt in enumerate(times):
        date_str = dt.strftime("%-m/%-d")  # 6/13, 6/14 형식
        if date_str not in seen_dates:
            marks[i] = date_str
            seen_dates.add(date_str)
    
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
    
    # 시간 형식을 읽기 쉽게 변환
    try:
        dt = datetime.strptime(current_time, "%Y%m%d%H")
        formatted_time = dt.strftime("%Y년 %m월 %d일 %H시")
    except:
        formatted_time = current_time
    
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
        current_file_title = f"{formatted_time} (최저: {current_min:.1f}°C, 최고: {current_max:.1f}°C, 평균: {current_avg:.1f}°C)"
    else:
        current_file_title = f"{formatted_time}"

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
    
    return fig_3d, current_time, viewer_data, 0, max_idx, marks, value, current_file_title

# 탭 콘텐츠 처리 콜백 (수정)
@callback(
    Output("tab-content", "children"),
    Input("tabs-main", "active_tab"),
    Input("current-file-title-store", "data"),
    Input("tbl-concrete", "selected_rows"),
    State("tbl-concrete", "data"),
    State("viewer-3d-store", "data"),
    prevent_initial_call=True,
)
def switch_tab(active_tab, current_file_title, selected_rows, tbl_data, viewer_data):
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
            # 시간 슬라이더 (항상 포함, 숨김 처리)
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
            ], className="mb-3", style={"display": "none"}),
            # 3D 뷰어 (항상 포함, 숨김 처리)
            dcc.Graph(
                id="viewer-3d",
                style={"display": "none"},
                config={"scrollZoom": True},
            ),
            # 단면도 탭 관련 컴포넌트들 (숨김 처리)
            html.Div([
                dcc.Slider(id="time-slider-section", min=0, max=5, value=0, marks={}),
            ], style={"display": "none"}),
            dcc.Graph(id="viewer-3d-section", style={"display": "none"}),
            dcc.Graph(id="viewer-section-x", style={"display": "none"}),
            dcc.Graph(id="viewer-section-y", style={"display": "none"}),
            dcc.Graph(id="viewer-section-z", style={"display": "none"}),
            dbc.Input(id="section-x-input", type="number", value=0, style={"display": "none"}),
            dbc.Input(id="section-y-input", type="number", value=0, style={"display": "none"}),
            dbc.Input(id="section-z-input", type="number", value=0, style={"display": "none"}),
            # 온도 탭 관련 컴포넌트들 (숨김 처리)
            dcc.Store(id="temp-coord-store", data={}),
            dbc.Input(id="temp-x-input", type="number", value=0, style={"display": "none"}),
            dbc.Input(id="temp-y-input", type="number", value=0, style={"display": "none"}),
            dbc.Input(id="temp-z-input", type="number", value=0, style={"display": "none"}),
            dcc.Graph(id="temp-viewer-3d", style={"display": "none"}),
            dcc.Graph(id="temp-time-graph", style={"display": "none"}),
            html.Div(guide_message, style={
                "textAlign": "center", "fontSize": "1.3rem", "color": "#555", "marginTop": "120px"
            })
        ])
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
        # 시간 정보 계산 (콘크리트가 선택된 경우 항상 계산)
        display_title = current_file_title
        
        # 콘크리트가 선택된 경우 시간 정보를 직접 계산하여 확실히 표시
        if selected_rows and tbl_data:
            try:
                from datetime import datetime as dt_module
                row = pd.DataFrame(tbl_data).iloc[selected_rows[0]]
                concrete_pk = row["concrete_pk"]
                inp_dir = f"inp/{concrete_pk}"
                inp_files = sorted(glob.glob(f"{inp_dir}/*.inp"))
                
                if inp_files:
                    # 현재 슬라이더 값에 해당하는 파일 선택
                    file_idx = min(slider_value if slider_value is not None else len(inp_files)-1, len(inp_files)-1)
                    latest_file = inp_files[file_idx]
                    time_str = os.path.basename(latest_file).split(".")[0]
                    dt = dt_module.strptime(time_str, "%Y%m%d%H")
                    formatted_time = dt.strftime("%Y년 %m월 %d일 %H시")
                    
                    # 온도 데이터 파싱
                    with open(latest_file, 'r') as f:
                        lines = f.readlines()
                    
                    current_temps = []
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
                        display_title = f"{formatted_time} (최저: {current_min:.1f}°C, 최고: {current_max:.1f}°C, 평균: {current_avg:.1f}°C)"
                    else:
                        display_title = f"{formatted_time}"
            except Exception as e:
                print(f"3D 뷰 제목 계산 오류: {e}")
                # 계산 실패 시 viewer_data에서 가져오기 시도
                if not display_title and viewer_data and 'current_file_title' in viewer_data:
                    display_title = viewer_data['current_file_title']
                else:
                    display_title = ""
        
        # 콘크리트가 선택되지 않은 경우 viewer_data에서 가져오기 시도
        if not selected_rows and not display_title and viewer_data and 'current_file_title' in viewer_data:
            display_title = viewer_data['current_file_title']
        
        return html.Div([
            # 시간 슬라이더
            html.Div([
                dcc.Slider(
                    id="time-slider",
                    min=slider_min,
                    max=slider_max,
                    step=1,
                    value=slider_value,
                    marks=slider_marks,
                    tooltip={"placement": "bottom", "always_visible": True},
                ),
            ], className="mb-2", style={
                # 슬라이더 색상을 진하게 설정
                "--slider-track-color": "#007bff",
                "--slider-thumb-color": "#0056b3",
                "--slider-mark-color": "#343a40"
            }),
            # 시간 정보 (슬라이더 아래, 3D 뷰 위)
            html.Div(id="main-file-title", children=display_title, style={
                "fontSize": "16px", 
                "color": "#495057", 
                "marginBottom": "10px", 
                "textAlign": "center",
                "fontWeight": "500",
                "padding": "8px",
                "backgroundColor": "#f8f9fa",
                "borderRadius": "6px",
                "border": "1px solid #dee2e6"
            }),
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
        
        # 단면도 탭에서도 시간 정보를 직접 계산
        section_display_title = current_file_title
        
        # 콘크리트가 선택된 경우 시간 정보를 직접 계산하여 확실히 표시
        if selected_rows and tbl_data:
            try:
                from datetime import datetime as dt_module
                row = pd.DataFrame(tbl_data).iloc[selected_rows[0]]
                concrete_pk = row["concrete_pk"]
                inp_dir = f"inp/{concrete_pk}"
                inp_files = sorted(glob.glob(f"{inp_dir}/*.inp"))
                
                if inp_files:
                    # 현재 슬라이더 값에 해당하는 파일 선택
                    file_idx = min(slider_value if slider_value is not None else len(inp_files)-1, len(inp_files)-1)
                    current_file = inp_files[file_idx]
                    time_str = os.path.basename(current_file).split(".")[0]
                    dt = dt_module.strptime(time_str, "%Y%m%d%H")
                    formatted_time = dt.strftime("%Y년 %m월 %d일 %H시")
                    
                    # 온도 데이터 파싱
                    with open(current_file, 'r') as f:
                        lines = f.readlines()
                    
                    current_temps = []
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
                        section_display_title = f"{formatted_time} (최저: {current_min:.1f}°C, 최고: {current_max:.1f}°C, 평균: {current_avg:.1f}°C)"
                    else:
                        section_display_title = f"{formatted_time}"
            except Exception as e:
                print(f"단면도 제목 계산 오류: {e}")
                # 계산 실패 시 기존 값 또는 viewer_data 사용
                if not section_display_title and viewer_data and 'current_file_title' in viewer_data:
                    section_display_title = viewer_data['current_file_title']
        
        # 콘크리트가 선택되지 않은 경우 viewer_data에서 가져오기 시도
        elif not section_display_title and viewer_data and 'current_file_title' in viewer_data:
            section_display_title = viewer_data['current_file_title']
        
        return html.Div([
            # 시간 슬라이더 (상단)
            html.Div([
                dcc.Slider(
                    id="time-slider-section",
                    min=slider_min,
                    max=slider_max,
                    step=1,
                    value=slider_value,
                    marks=slider_marks,
                    tooltip={"placement": "bottom", "always_visible": True},
                ),
            ], className="mb-2", style={
                # 슬라이더 색상을 진하게 설정
                "--slider-track-color": "#007bff",
                "--slider-thumb-color": "#0056b3",
                "--slider-mark-color": "#343a40"
            }),
            # 시간 정보 (슬라이더 아래)
            html.Div(id="section-file-title", children=section_display_title, style={
                "fontSize": "16px", 
                "color": "#495057", 
                "marginBottom": "10px", 
                "textAlign": "center",
                "fontWeight": "500",
                "padding": "8px",
                "backgroundColor": "#f8f9fa",
                "borderRadius": "6px",
                "border": "1px solid #dee2e6"
            }),
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
        ])
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
        ])
    elif active_tab == "tab-analysis":
        # 수치해석 탭: 서버에서 VTK/VTP 파일을 파싱하여 dash_vtk.Mesh로 시각화 + 컬러맵 필드/프리셋 선택
        if not (selected_rows and tbl_data):
            return html.Div("콘크리트를 선택하세요.")
        
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
            return html.Div("VTK/VTP 파일이 없습니다.")
        
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
        
        # 컬러맵 프리셋 옵션 (3개로 제한)
        preset_options = [
            {"label": "무지개", "value": "rainbow"},
            {"label": "블루-레드", "value": "Cool to Warm"},
            {"label": "회색", "value": "Grayscale"},
        ]
        
        # 시간 슬라이더 마크: 모든 시간을 일 단위로 표시
        time_marks = {}
        seen_dates = set()
        for i, (dt, _) in enumerate(times):
            date_str = dt.strftime("%-m/%-d")  # 6/13, 6/14 형식
            if date_str not in seen_dates:
                time_marks[i] = date_str
                seen_dates.add(date_str)
        
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
                    html.Div([
                        dcc.Slider(
                            id="analysis-time-slider",
                            min=0,
                            max=max_idx,
                            step=1,
                            value=max_idx,
                            marks=time_marks,
                            tooltip={"placement": "bottom", "always_visible": True},
                        )
                    ], style={
                        # 슬라이더 색상을 진하게 설정
                        "--slider-track-color": "#007bff",
                        "--slider-thumb-color": "#0056b3",
                        "--slider-mark-color": "#343a40"
                    })
                ], md=6),
            ], className="mb-3"),
            
            # 현재 파일/범위 표시
            html.Div(id="analysis-current-file-label", style={"marginBottom":"8px", "fontWeight":"500"}),
            
            # 단면(slice) 컨트롤
            dbc.Row([
                dbc.Col([
                    dbc.Checklist(
                        options=[{"label": "단면 보기", "value": "on"}],
                        value=[],
                        id="slice-enable",
                        switch=True,
                    )
                ], md=2),
                dbc.Col([
                    html.Label("축 선택", style={"fontSize": "12px", "marginBottom": "2px"}),
                    dcc.Dropdown(
                        id="slice-axis",
                        options=[
                            {"label": "X축 (좌→우)", "value": "X"},
                            {"label": "Y축 (앞→뒤)", "value": "Y"},
                            {"label": "Z축 (아래→위)", "value": "Z"},
                        ],
                        value="Z",
                        clearable=False,
                    )
                ], md=2),
                dbc.Col([
                    html.Label("절단 위치 (선택 위치 이상 영역 표시)", style={"fontSize": "12px", "marginBottom": "2px"}),
                    dcc.Slider(
                        id="slice-slider",
                        min=0, max=1, step=0.05, value=0.5,
                        marks={0: '0.0', 1: '1.0'},
                        tooltip={"placement": "bottom", "always_visible": True},
                    )
                ], md=8),
            ], className="mb-2"),
            
            # 3D 뷰어
            html.Div(id="analysis-3d-viewer", style={"height": "60vh"}),

            # 컬러바 (조건부 표시)
            html.Div(id="analysis-colorbar-container", children=[
                dcc.Graph(id="analysis-colorbar", style={"height":"120px", "display": "none"})
            ])
            
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
        updated_data[selected_rows[0]]["status"] = "분석중"
        updated_data[selected_rows[0]]["status_color"] = "#d4edda"  # 연한 초록색
        
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
    Output("current-file-title-store", "data", allow_duplicate=True),
    Input("time-slider-section", "value"),
    Input("section-x-input", "value"),
    Input("section-y-input", "value"),
    Input("section-z-input", "value"),
    State("tbl-concrete", "selected_rows"),
    State("tbl-concrete", "data"),
    prevent_initial_call=True,
)
def update_section_views(time_idx,
                         x_val, y_val, z_val,
                         selected_rows, tbl_data):
    """time_idx는 두 슬라이더 중 변경된 쪽을 우선 사용"""
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
    # 슬라이싱 허용 오차를 콘크리트 크기에 비례하도록 동적으로 계산
    dx = x_max - x_min
    dy = y_max - y_min
    dz = z_max - z_min
    tol = max(dx, dy, dz) * 0.02  # 전체 치수의 약 2%
    tol = max(tol, 0.01)  # 최소 1 cm 보장
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
        # 시간 형식을 읽기 쉽게 변환
        try:
            dt = datetime.strptime(time_str, "%Y%m%d%H")
            formatted_time = dt.strftime("%Y년 %m월 %d일 %H시")
        except:
            formatted_time = time_str
        
        current_min = float(np.nanmin(temps))
        current_max = float(np.nanmax(temps))
        current_avg = float(np.nanmean(temps))
        current_file_title = f"{formatted_time} (최저: {current_min:.1f}°C, 최고: {current_max:.1f}°C, 평균: {current_avg:.1f}°C)"
    except Exception:
        current_file_title = f"{os.path.basename(current_file)}"
    # step=0.1로 반환
    return fig_3d, fig_x, fig_y, fig_z, x_min, x_max, x0, y_min, y_max, y0, z_min, z_max, z0, current_file_title



# 시간 슬라이더 동기화 콜백 (메인 3D 뷰 ↔ 단면도 탭)
@callback(
    Output("time-slider-section", "value", allow_duplicate=True),
    Output("time-slider-section", "min", allow_duplicate=True),
    Output("time-slider-section", "max", allow_duplicate=True),
    Output("time-slider-section", "marks", allow_duplicate=True),
    Input("time-slider", "value"),
    Input("time-slider", "min"),
    Input("time-slider", "max"),
    Input("time-slider", "marks"),
    prevent_initial_call=True,
)
def sync_time_sliders_to_section(main_value, main_min, main_max, main_marks):
    return main_value, main_min, main_max, main_marks

@callback(
    Output("time-slider", "value", allow_duplicate=True),
    Output("time-slider", "min", allow_duplicate=True),
    Output("time-slider", "max", allow_duplicate=True),
    Output("time-slider", "marks", allow_duplicate=True),
    Input("time-slider-section", "value"),
    State("time-slider-section", "min"),
    State("time-slider-section", "max"),
    State("time-slider-section", "marks"),
    prevent_initial_call=True,
)
def sync_section_slider_to_main(section_value, section_min, section_max, section_marks):
    return section_value, section_min, section_max, section_marks

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

# 수치해석 3D 뷰 콜백 (필드/프리셋/시간/단면)
@callback(
    Output("analysis-3d-viewer", "children"),
    Output("analysis-current-file-label", "children"),
    Output("analysis-colorbar", "figure"),
    Output("slice-slider", "min"),
    Output("slice-slider", "max"),
    Input("analysis-field-dropdown", "value"),
    Input("analysis-preset-dropdown", "value"),
    Input("analysis-time-slider", "value"),
    Input("slice-enable", "value"),
    Input("slice-axis", "value"),
    Input("slice-slider", "value"),
    State("tbl-concrete", "selected_rows"),
    State("tbl-concrete", "data"),
    prevent_initial_call=False,
)
def update_analysis_3d_view(field_name, preset, time_idx, slice_enable, slice_axis, slice_slider, selected_rows, tbl_data):
    import os
    import vtk
    from dash_vtk.utils import to_mesh_state
    
    if not selected_rows or not tbl_data:
        return html.Div("콘크리트를 선택하세요."), go.Figure(), 0.0, 1.0
    
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
        return html.Div("VTK/VTP 파일이 없습니다."), go.Figure(), 0.0, 1.0
    
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
        return html.Div("시간 정보가 포함된 VTK/VTP 파일이 없습니다."), go.Figure(), 0.0, 1.0
    
    times.sort()
    max_idx = len(times) - 1
    
    # 시간 인덱스 처리 (처음 로드시에는 최신 파일)
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
            ]), go.Figure(), 0.0, 1.0
        
        # 점의 개수 확인
        num_points = ds.GetNumberOfPoints()
        if num_points == 0:
            return html.Div([
                html.H5("빈 데이터셋", style={"color": "red"}),
                html.P(f"파일: {selected_file}"),
                html.P("점이 없는 데이터셋입니다.")
            ]), go.Figure(), 0.0, 1.0
        
        # 바운딩 박스 정보 추출 (단면 슬라이더용)
        bounds = ds.GetBounds()  # (xmin,xmax,ymin,ymax,zmin,zmax)
        xmin, xmax, ymin, ymax, zmin, zmax = bounds
        
        # 선택된 축에 따른 슬라이더 범위 결정
        if slice_axis == "X":
            slice_min, slice_max = xmin, xmax
        elif slice_axis == "Y":
            slice_min, slice_max = ymin, ymax
        else:  # Z
            slice_min, slice_max = zmin, zmax
        
        # 필드 데이터 검증
        if field_name:
            arr = ds.GetPointData().GetArray(field_name)
            if arr is None:
                field_name = None  # 필드가 없으면 기본 시각화로 변경
        
        # 단면 적용 (slice_enable에 "on"이 있으면 활성화)
        ds_for_vis = ds
        if slice_enable and "on" in slice_enable:
            try:
                # 슬라이더의 값을 절대 좌표로 직접 사용하도록 변경
                slice_value = slice_slider
                
                # 방법 1: vtkTableBasedClipDataSet 사용 (더 안정적)
                clipper = vtk.vtkTableBasedClipDataSet()
                clipper.SetInputData(ds)
                
                # 평면 생성
                plane = vtk.vtkPlane()
                if slice_axis == "X":
                    plane.SetOrigin(slice_value, 0, 0)
                    plane.SetNormal(-1, 0, 0)  # X >= slice_value 영역 유지
                elif slice_axis == "Y":
                    plane.SetOrigin(0, slice_value, 0) 
                    plane.SetNormal(0, -1, 0)  # Y >= slice_value 영역 유지
                else:  # Z
                    plane.SetOrigin(0, 0, slice_value)
                    plane.SetNormal(0, 0, -1)  # Z >= slice_value 영역 유지
                
                clipper.SetClipFunction(plane)
                clipper.SetInsideOut(False)
                clipper.Update()
                
                # 클리핑 결과를 PolyData로 변환
                geom_filter = vtk.vtkGeometryFilter()
                geom_filter.SetInputData(clipper.GetOutput())
                geom_filter.Update()
                clipped_data = geom_filter.GetOutput()
                
                # 클리핑이 성공했는지 확인
                if clipped_data.GetNumberOfCells() > 0:
                    # 빈 공간을 채우기 위해 Delaunay 3D 사용
                    try:
                        # 먼저 점들로부터 3D 메쉬 생성
                        delaunay3d = vtk.vtkDelaunay3D()
                        delaunay3d.SetInputData(clipped_data)
                        delaunay3d.SetTolerance(0.001)
                        delaunay3d.SetAlpha(0.0)  # 모든 점 포함
                        delaunay3d.Update()
                        
                        # 3D 메쉬에서 표면 추출
                        surface_filter = vtk.vtkGeometryFilter()
                        surface_filter.SetInputData(delaunay3d.GetOutput())
                        surface_filter.Update()
                        
                        filled_data = surface_filter.GetOutput()
                        
                        # 결과가 있으면 사용, 없으면 원본 클리핑 결과 사용
                        if filled_data.GetNumberOfCells() > 0:
                            ds_for_vis = filled_data
                        else:
                            ds_for_vis = clipped_data
                            
                    except Exception as delaunay_error:
                        print(f"Delaunay 3D 오류: {delaunay_error}")
                        # Delaunay가 실패하면 단순히 클리핑 결과 사용
                        ds_for_vis = clipped_data
                
                else:
                    # 클리핑 실패시 다중 방법 시도
                    try:
                        # 방법 2: Box를 이용한 클리핑 + 볼륨 필링
                        box = vtk.vtkBox()
                        if slice_axis == "X":
                            box.SetBounds(slice_value, xmax+0.1, ymin-0.1, ymax+0.1, zmin-0.1, zmax+0.1)
                        elif slice_axis == "Y":
                            box.SetBounds(xmin-0.1, xmax+0.1, slice_value, ymax+0.1, zmin-0.1, zmax+0.1)
                        else:  # Z
                            box.SetBounds(xmin-0.1, xmax+0.1, ymin-0.1, ymax+0.1, slice_value, zmax+0.1)
                        
                        box_clipper = vtk.vtkTableBasedClipDataSet()
                        box_clipper.SetInputData(ds)
                        box_clipper.SetClipFunction(box)
                        box_clipper.SetInsideOut(False)
                        box_clipper.Update()
                        
                        box_result = box_clipper.GetOutput()
                        
                        if box_result.GetNumberOfCells() > 0:
                            # Box 클리핑 성공 - 표면 생성
                            box_geom = vtk.vtkGeometryFilter()
                            box_geom.SetInputData(box_result)
                            box_geom.Update()
                            
                            # 빈 공간을 채우기 위해 contour 필터 추가
                            try:
                                # 좀 더 조밀한 메쉬 생성
                                tessellator = vtk.vtkTessellatorFilter()
                                tessellator.SetInputData(box_result)
                                tessellator.Update()
                                
                                tess_geom = vtk.vtkGeometryFilter()
                                tess_geom.SetInputData(tessellator.GetOutput())
                                tess_geom.Update()
                                
                                ds_for_vis = tess_geom.GetOutput()
                                
                            except Exception:
                                # Tessellator 실패시 기본 geometry filter 결과 사용
                                ds_for_vis = box_geom.GetOutput()
                        else:
                            # 방법 3: 임계값 기반 필터링 (마지막 수단)
                            # 원본 데이터에서 해당 영역의 점들만 추출
                            extract = vtk.vtkExtractGeometry()
                            extract.SetInputData(ds)
                            extract.SetImplicitFunction(box)
                            extract.SetExtractInside(True)
                            extract.SetExtractBoundaryCells(True)
                            extract.Update()
                            
                            extract_geom = vtk.vtkGeometryFilter()
                            extract_geom.SetInputData(extract.GetOutput())
                            extract_geom.Update()
                            
                            ds_for_vis = extract_geom.GetOutput()
                        
                        # 여전히 결과가 없으면 원본 사용
                        if ds_for_vis.GetNumberOfCells() == 0:
                            ds_for_vis = ds
                            
                    except Exception as box_error:
                        print(f"고급 클리핑 오류: {box_error}")
                        ds_for_vis = ds
                    
            except Exception as slice_error:
                print(f"단면 적용 오류: {slice_error}")
                ds_for_vis = ds
        
        # 메시 상태 생성 (더 안전한 방식)
        try:
            # 단면이 활성화된 경우 추가 처리
            if slice_enable and "on" in slice_enable and ds_for_vis.GetNumberOfCells() > 0:
                # 단면에서 빈 공간을 최소화하기 위해 삼각형화
                try:
                    triangulator = vtk.vtkTriangleFilter()
                    triangulator.SetInputData(ds_for_vis)
                    triangulator.Update()
                    
                    triangulated = triangulator.GetOutput()
                    if triangulated.GetNumberOfCells() > 0:
                        ds_for_vis = triangulated
                        
                except Exception as tri_error:
                    print(f"삼각형화 오류: {tri_error}")
                    # 삼각형화 실패해도 원본 ds_for_vis 계속 사용
            
            # 메쉬 상태 생성
            if field_name:
                mesh_state = to_mesh_state(ds_for_vis, field_name)
            else:
                mesh_state = to_mesh_state(ds_for_vis)
            
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
                html.P(f"셀 개수: {ds_for_vis.GetNumberOfCells()}"),
                html.Hr(),
                html.P("VTK 파일 형식을 확인해주세요. FRD → VTK 변환이 올바르게 되었는지 점검이 필요합니다.", style={"color": "gray"})
            ]), go.Figure(), slice_min, slice_max
        
        # 컬러 데이터 범위 추출
        color_range = None
        colorbar_fig = go.Figure()
        if field_name:
            arr = ds_for_vis.GetPointData().GetArray(field_name)
            if arr is not None:
                range_val = arr.GetRange()
                if range_val[0] != range_val[1]:  # 값이 모두 같지 않을 때만 범위 설정
                    color_range = [range_val[0], range_val[1]]
                    
                    # 컬러바 생성
                    try:
                        # 프리셋에 따른 컬러스케일 매핑
                        colorscale_map = {
                            "rainbow": [[0, 'blue'], [0.25, 'cyan'], [0.5, 'green'], [0.75, 'yellow'], [1, 'red']],
                            "Cool to Warm": [[0, 'blue'], [0.5, 'white'], [1, 'red']],
                            "Grayscale": [[0, 'black'], [1, 'white']]
                        }
                        
                        colorbar_fig = go.Figure(data=go.Scatter(
                            x=[None], y=[None],
                            mode='markers',
                            marker=dict(
                                colorscale=colorscale_map.get(preset, 'viridis'),
                                cmin=color_range[0],
                                cmax=color_range[1],
                                colorbar=dict(
                                    title=dict(text="값", font=dict(size=14)),
                                    thickness=15,
                                    len=0.7,
                                    x=0.5,
                                    xanchor="center",
                                    tickfont=dict(size=12)
                                ),
                                showscale=True
                            )
                        ))
                        colorbar_fig.update_layout(
                            showlegend=False,
                            xaxis=dict(visible=False),
                            yaxis=dict(visible=False),
                            margin=dict(l=0, r=0, t=10, b=0),
                            height=120,
                            plot_bgcolor='rgba(0,0,0,0)',
                            paper_bgcolor='rgba(0,0,0,0)'
                        )
                    except Exception as colorbar_error:
                        print(f"컬러바 생성 오류: {colorbar_error}")
        
        # 기본 프리셋 설정
        if not preset:
            preset = "rainbow"
        
        # dash_vtk 컴포넌트 생성 (더 안전한 방식)
        try:
            # Mesh 컴포넌트 먼저 생성
            mesh_component = dash_vtk.Mesh(state=mesh_state)
            
            # GeometryRepresentation 생성 (필수 속성만 사용)
            geometry_rep_props = {
                "children": [mesh_component]
            }
            
            # 안전하게 속성 추가
            if preset:
                geometry_rep_props["colorMapPreset"] = preset
            
            if color_range and len(color_range) == 2:
                geometry_rep_props["colorDataRange"] = color_range
            
            geometry_rep = dash_vtk.GeometryRepresentation(**geometry_rep_props)
            
            # --- Bounding box wireframe 추가 (원본 데이터 기준) ---
            view_children = [geometry_rep]
            try:
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
                
                # 바운딩 박스용 Mesh와 GeometryRepresentation 생성
                bbox_mesh = dash_vtk.Mesh(state=bbox_state)
                bbox_rep = dash_vtk.GeometryRepresentation(children=[bbox_mesh])
                view_children.append(bbox_rep)
            except Exception as bbox_error:
                print(f"바운딩 박스 생성 오류: {bbox_error}")
            
            # View 컴포넌트 생성 (안전한 방식)
            vtk_viewer = dash_vtk.View(
                children=view_children, 
                style={"height": "60vh", "width": "100%"}
            )
            
            label = f"파일: {selected_file}"
            if color_range:
                label += f" | 값 범위: {color_range[0]:.2f} ~ {color_range[1]:.2f}"
            if slice_enable and "on" in slice_enable:
                slice_value = slice_slider
                if slice_axis == "X":
                    label += f" | X ≥ {slice_value:.1f} 영역"
                elif slice_axis == "Y":
                    label += f" | Y ≥ {slice_value:.1f} 영역"
                else:  # Z
                    label += f" | Z ≥ {slice_value:.1f} 영역"
                
            return vtk_viewer, label, colorbar_fig, slice_min, slice_max
            
        except Exception as vtk_error:
            print(f"dash_vtk 컴포넌트 생성 오류: {vtk_error}")
            return html.Div([
                html.H5("3D 뷰어 생성 오류", style={"color": "red"}),
                html.P(f"파일: {selected_file}"),
                html.P(f"오류: {str(vtk_error)}"),
                html.Hr(),
                html.P("브라우저를 새로고침하거나 다른 파일을 선택해보세요.", style={"color": "gray"})
            ]), go.Figure(), slice_min, slice_max
        
    except Exception as e:
        print(f"VTK 처리 전체 오류: {e}")
        return html.Div([
            html.H5("VTK/VTP 파싱 오류", style={"color": "red"}),
            html.P(f"파일: {selected_file}"),
            html.P(f"파일 타입: {file_type}"),
            html.P(f"오류: {str(e)}"),
            html.Hr(),
            html.P("다른 파일을 선택하거나 VTK 파일을 확인해주세요.", style={"color": "gray"})
        ]), go.Figure(), 0.0, 1.0

# 수치해석 컬러바 표시/숨김 콜백
@callback(
    Output("analysis-colorbar", "style"),
    Input("analysis-field-dropdown", "value"),
    prevent_initial_call=True,
)
def toggle_colorbar_visibility(field_name):
    if field_name:
        return {"height": "120px", "display": "block"}
    else:
        return {"height": "120px", "display": "none"}


