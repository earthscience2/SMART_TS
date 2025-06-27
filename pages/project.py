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
    className="px-4 py-3",
    style={"backgroundColor": "#f7f9fc", "minHeight": "100vh"},
    children=[
        dcc.Location(id="project-url", refresh=False),
        


        # ── 컨펌 다이얼로그 및 알림
        dcc.ConfirmDialog(
            id="confirm-del-concrete",
            message="선택한 콘크리트를 정말 삭제하시겠습니까?"
        ),
        dbc.Alert(
            id="project-alert",
            is_open=False,
            duration=3000,
            color="danger",
            style={"borderRadius": "8px", "border": "none"}
        ),

        # ── 데이터 저장용 Store들
        dcc.Store(id="current-time-store", data=None),
        dcc.Store(id="current-file-title-store", data=""),
        dcc.Store(id="section-coord-store", data=None),
        dcc.Store(id="viewer-3d-store", data=None),
        dcc.Graph(id='section-colorbar', style={'display':'none'}),
        
        # 키보드 이벤트 처리 스크립트
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
                                            
                                            // 툴클 업데이트
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

        # 메인 콘텐츠 영역
        dbc.Row([
            # 왼쪽 사이드바 - 콘크리트 목록
            dbc.Col([
                html.Div([
                    # 프로젝트 제목 (숨김)
                    html.Div([
                        html.Span(
                            id="concrete-title",
                            style={"display": "none"},
                            children="프로젝트를 선택하세요"
                        )
                    ]),
                    
                    # 콘크리트 목록 섹션
                    html.Div([
                        html.Div([
                            html.H5("🏗️ 콘크리트 목록", style={
                                "fontWeight": "600", 
                                "color": "#2d3748",
                                "fontSize": "16px",
                                "margin": "0"
                            }),
                            html.Small("💡 행을 클릭하여 선택", className="text-muted", style={
                                "fontSize": "12px"
                            })
                        ], className="d-flex justify-content-between align-items-center mb-3"),
                        
                        html.Div([
                            dash_table.DataTable(
                                id="tbl-concrete",
                                page_size=10,
                                row_selectable="single",
                                sort_action="native",
                                sort_mode="single",
                                style_table={
                                    "overflowY": "auto", 
                                    "height": "500px",
                                    "borderRadius": "8px",
                                    "border": "1px solid #e2e8f0"
                                },
                                style_cell={
                                    "whiteSpace": "nowrap", 
                                    "textAlign": "center",
                                    "padding": "12px 8px",
                                    "fontSize": "13px",
                                    "fontFamily": "-apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui",
                                    "border": "1px solid #f1f5f9"
                                },
                                style_header={
                                    "backgroundColor": "#f8fafc", 
                                    "fontWeight": "600",
                                    "color": "#475569",
                                    "border": "1px solid #e2e8f0",
                                    "textAlign": "center"
                                },
                                style_data_conditional=[
                                    {
                                        'if': {'row_index': 'odd'},
                                        'backgroundColor': '#fafbfc'
                                    },
                                    {
                                        'if': {'state': 'selected'},
                                        'backgroundColor': '#e6f3ff',
                                        'border': '1px solid #3182ce'
                                    }
                                ]
                            ),
                        ], style={
                            "backgroundColor": "white",
                            "borderRadius": "8px",
                            "overflow": "hidden"
                        }),
                        
                        # 액션 버튼들
                        html.Div([
                            dbc.ButtonGroup([
                                dbc.Button(
                                    [html.I(className="fas fa-play me-2"), "분석 시작"],
                                    id="btn-concrete-analyze",
                                    color="success",
                                    disabled=True,
                                    size="sm",
                                    style={
                                        "borderRadius": "6px",
                                        "fontWeight": "500",
                                        "boxShadow": "0 1px 2px rgba(0,0,0,0.1)"
                                    }
                                ),
                                dbc.Button(
                                    [html.I(className="fas fa-trash me-2"), "삭제"],
                                    id="btn-concrete-del",
                                    color="danger",
                                    disabled=True,
                                    size="sm",
                                    style={
                                        "borderRadius": "6px",
                                        "fontWeight": "500",
                                        "boxShadow": "0 1px 2px rgba(0,0,0,0.1)"
                                    }
                                ),
                            ], className="w-100")
                        ], className="mt-3"),
                    ])
                ], style={
                    "backgroundColor": "white",
                    "padding": "20px",
                    "borderRadius": "12px",
                    "boxShadow": "0 1px 3px rgba(0,0,0,0.1)",
                    "border": "1px solid #e2e8f0",
                    "height": "fit-content"
                })
            ], width=3),
            
            # 오른쪽 메인 콘텐츠 영역
            dbc.Col([
                html.Div([

                    
                    # 탭 메뉴 (노션 스타일)
                    html.Div([
                        dbc.Tabs([
                            dbc.Tab(
                                label="🎯 3D 뷰", 
                                tab_id="tab-3d",
                                tab_style={
                                    "marginLeft": "2px",
                                    "marginRight": "2px",
                                    "border": "none",
                                    "borderRadius": "6px 6px 0 0",
                                    "backgroundColor": "#f8fafc"
                                },
                                active_tab_style={
                                    "backgroundColor": "white",
                                    "border": "1px solid #e2e8f0",
                                    "borderBottom": "1px solid white",
                                    "color": "#3182ce",
                                    "fontWeight": "600"
                                }
                            ),
                            dbc.Tab(
                                label="📊 단면도", 
                                tab_id="tab-section",
                                tab_style={
                                    "marginLeft": "2px",
                                    "marginRight": "2px",
                                    "border": "none",
                                    "borderRadius": "6px 6px 0 0",
                                    "backgroundColor": "#f8fafc"
                                },
                                active_tab_style={
                                    "backgroundColor": "white",
                                    "border": "1px solid #e2e8f0",
                                    "borderBottom": "1px solid white",
                                    "color": "#3182ce",
                                    "fontWeight": "600"
                                }
                            ),
                            dbc.Tab(
                                label="🌡️ 온도 변화", 
                                tab_id="tab-temp",
                                tab_style={
                                    "marginLeft": "2px",
                                    "marginRight": "2px",
                                    "border": "none",
                                    "borderRadius": "6px 6px 0 0",
                                    "backgroundColor": "#f8fafc"
                                },
                                active_tab_style={
                                    "backgroundColor": "white",
                                    "border": "1px solid #e2e8f0",
                                    "borderBottom": "1px solid white",
                                    "color": "#3182ce",
                                    "fontWeight": "600"
                                }
                            ),
                            dbc.Tab(
                                label="🔬 수치해석", 
                                tab_id="tab-analysis",
                                tab_style={
                                    "marginLeft": "2px",
                                    "marginRight": "2px",
                                    "border": "none",
                                    "borderRadius": "6px 6px 0 0",
                                    "backgroundColor": "#f8fafc"
                                },
                                active_tab_style={
                                    "backgroundColor": "white",
                                    "border": "1px solid #e2e8f0",
                                    "borderBottom": "1px solid white",
                                    "color": "#3182ce",
                                    "fontWeight": "600"
                                }
                            ),
                        ], 
                        id="tabs-main", 
                        active_tab="tab-3d",
                        style={"borderBottom": "1px solid #e2e8f0"}
                        ),
                    ], style={"marginBottom": "0px"}),
                    
                    # 탭 콘텐츠 영역
                    html.Div([
                        html.Div(id="tab-content", style={
                            "backgroundColor": "white",
                            "border": "1px solid #e2e8f0",
                            "borderTop": "none",
                            "borderRadius": "0 0 12px 12px",
                            "padding": "24px",
                            "minHeight": "600px"
                        })
                    ]),
                    
                    # 숨김 처리된 콜백 대상 컴포넌트들 (항상 포함)
                    html.Div([
                        dcc.Slider(id="time-slider", min=0, max=5, step=1, value=0, marks={}),
                        dcc.Slider(id="time-slider-display", min=0, max=5, step=1, value=0, marks={}),
                        dcc.Slider(id="time-slider-section", min=0, max=5, step=1, value=0, marks={}),
                        dcc.Graph(id="viewer-3d"),
                        dcc.Graph(id="viewer-3d-display"),
                        dbc.Input(id="section-x-input", type="number", value=None),
                        dbc.Input(id="section-y-input", type="number", value=None),
                        dbc.Input(id="section-z-input", type="number", value=None),
                        dcc.Graph(id="viewer-3d-section"),
                        dcc.Graph(id="viewer-section-x"),
                        dcc.Graph(id="viewer-section-y"),
                        dcc.Graph(id="viewer-section-z"),
                        dcc.Store(id="temp-coord-store", data={}),
                        dbc.Input(id="temp-x-input", type="number", value=0),
                        dbc.Input(id="temp-y-input", type="number", value=0),
                        dbc.Input(id="temp-z-input", type="number", value=0),
                        dcc.Graph(id="temp-viewer-3d"),
                        dcc.Graph(id="temp-time-graph"),
                        dcc.Dropdown(id="analysis-field-dropdown", value=None),
                        dcc.Dropdown(id="analysis-preset-dropdown", value="rainbow"),
                        dcc.Slider(id="analysis-time-slider", min=0, max=5, value=0),
                        dbc.Checklist(id="slice-enable", value=[]),
                        dcc.Dropdown(id="slice-axis", value="Z"),
                        dcc.Slider(id="slice-slider", min=0, max=1, value=0.5),
                        html.Div(id="analysis-3d-viewer"),
                        html.Div(id="analysis-current-file-label"),
                        dcc.Graph(id="analysis-colorbar"),
                    ], style={"display": "none"}),
                    
                ], style={
                    "backgroundColor": "white",
                    "borderRadius": "12px",
                    "boxShadow": "0 1px 3px rgba(0,0,0,0.1)",
                    "border": "1px solid #e2e8f0",
                    "overflow": "hidden"
                })
            ], width=9),
        ], className="g-4"),
    ],
)

# ───────────────────── ① 콘크리트 목록 초기화 ─────────────────────
@callback(
    Output("tbl-concrete", "data"),
    Output("tbl-concrete", "columns"),
    Output("tbl-concrete", "selected_rows"),
    Output("tbl-concrete", "style_data_conditional"),
    Output("btn-concrete-del", "disabled"),
    Output("btn-concrete-analyze", "disabled"),
    Output("concrete-title", "children"),
    Output("time-slider", "min"),
    Output("time-slider", "max"),
    Output("time-slider", "value"),
    Output("time-slider", "marks"),
    Output("current-time-store", "data"),
    Input("project-url", "search"),
    Input("project-url", "pathname"),
    prevent_initial_call=False,
)
def load_concrete_data(search, pathname):
    # URL에서 프로젝트 정보 추출
    project_pk = None
    if search:
        try:
            qs = parse_qs(search.lstrip('?'))
            project_pk = qs.get('page', [None])[0]
        except Exception:
            pass
    
    if not project_pk:
        return [], [], [], [], True, True, "프로젝트를 선택하세요", 0, 5, 0, {}, None
    
    try:
        # 프로젝트 정보 로드
        df_proj = api_db.get_project_data(project_pk=project_pk)
        if df_proj.empty:
            return [], [], [], [], True, True, "존재하지 않는 프로젝트", 0, 5, 0, {}, None
            
        proj_row = df_proj.iloc[0]
        proj_name = proj_row["name"]
        
        # 해당 프로젝트의 콘크리트 데이터 로드
        df_conc = api_db.get_concrete_data(project_pk=project_pk)
        if df_conc.empty:
            return [], [], [], [], True, True, f"{proj_name} · 콘크리트 목록 (0개)", 0, 5, 0, {}, None
        
    except Exception as e:
        print(f"프로젝트 로딩 오류: {e}")
        return [], [], [], [], True, True, "프로젝트 정보를 불러올 수 없음", 0, 5, 0, {}, None
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
        try:
            df_sensors = api_db.get_sensors_data(concrete_pk=concrete_pk)
        except:
            df_sensors = pd.DataFrame()
        has_sensors = not df_sensors.empty
        
        # 상태 결정 (정렬을 위해 우선순위도 함께 설정)
        if row["activate"] == 1:  # 활성
            if has_sensors:
                status = "분석 가능"
                status_sort = 2  # 두 번째 우선순위
            else:
                status = "센서 부족"
                status_sort = 3  # 세 번째 우선순위
        else:  # 비활성 (activate == 0)
            status = "분석중"
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

    title = f"{proj_name} · 콘크리트 목록"
    
    # 테이블 스타일 설정 (문자열 비교 기반 색상)
    style_data_conditional = [
        # 분석중 상태 (초록색)
        {
            'if': {
                'filter_query': '{status} = "분석중"',
                'column_id': 'status'
            },
            'backgroundColor': '#e8f5e8',
            'color': '#2e7d32',
            'fontWeight': 'bold'
        },
        # 분석 가능 상태 (파란색)
        {
            'if': {
                'filter_query': '{status} = "분석 가능"',
                'column_id': 'status'
            },
            'backgroundColor': '#e3f2fd',
            'color': '#1565c0',
            'fontWeight': 'bold'
        },
        # 센서 부족 상태 (오렌지색)
        {
            'if': {
                'filter_query': '{status} = "센서 부족"',
                'column_id': 'status'
            },
            'backgroundColor': '#fff3e0',
            'color': '#ef6c00',
            'fontWeight': 'bold'
        }
    ]
    
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

    # 초기값 설정
    current_file_title = ""

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
    
    # INP 파일에서 물성치 정보 추출
    material_info = "물성치 정보 없음"
    try:
        # 이미 파싱된 INP 파일 내용에서 물성치 정보 추출
        elastic_modulus = None
        poisson_ratio = None
        density = None
        thermal_expansion = None
        
        material_section = False
        elastic_section = False
        density_section = False
        expansion_section = False
        
        for line in lines:
            line = line.strip()
            
            # 섹션 시작 감지
            if line.startswith('*MATERIAL'):
                material_section = True
                continue
            elif line.startswith('*ELASTIC'):
                elastic_section = True
                continue
            elif line.startswith('*DENSITY'):
                density_section = True
                continue
            elif line.startswith('*EXPANSION'):
                expansion_section = True
                continue
            elif line.startswith('*'):
                # 다른 섹션 시작시 모든 플래그 리셋
                material_section = False
                elastic_section = False
                density_section = False
                expansion_section = False
                continue
            
            # 물성치 데이터 파싱
            if elastic_section and ',' in line and not line.startswith('*'):
                parts = line.split(',')
                if len(parts) >= 2:
                    try:
                        elastic_modulus = float(parts[0])  # MPa 또는 Pa
                        poisson_ratio = float(parts[1])
                        # 탄성계수가 Pa 단위로 저장된 경우 MPa로 변환
                        if elastic_modulus > 1000000:
                            elastic_modulus = elastic_modulus / 1000000  # Pa to MPa
                    except:
                        pass
            
            if density_section and line and not line.startswith('*'):
                try:
                    # 밀도는 쉼표가 있을 수도 없을 수도 있음 (예: "2500" 또는 "2500,")
                    if ',' in line:
                        density = float(line.split(',')[0])  # kg/m³
                    else:
                        density = float(line.strip())  # kg/m³
                except:
                    pass
            
            if expansion_section and line and not line.startswith('*'):
                try:
                    # 열팽창계수도 쉼표가 있을 수도 없을 수도 있음 (예: "5.00e-01" 또는 "5.00e-01,")
                    if ',' in line:
                        thermal_expansion = float(line.split(',')[0])  # /°C
                    else:
                        thermal_expansion = float(line.strip())  # /°C
                except:
                    pass
        
        # 물성치 정보 문자열 생성
        material_parts = []
        if elastic_modulus is not None:
            material_parts.append(f"탄성계수: {elastic_modulus:.0f}MPa")
        if poisson_ratio is not None:
            material_parts.append(f"포아송비: {poisson_ratio:.3f}")
        if density is not None:
            material_parts.append(f"밀도: {density:.0f}kg/m³")
        if thermal_expansion is not None:
            material_parts.append(f"열팽창: {thermal_expansion:.1e}/°C")
        
        if material_parts:
            material_info = ", ".join(material_parts)
        else:
            material_info = "물성치 정보 없음"
            
    except Exception as e:
        print(f"INP 파일에서 물성치 정보 추출 오류: {e}")
        material_info = "물성치 정보 없음"
    
    if current_temps:
        current_min = float(np.nanmin(current_temps))
        current_max = float(np.nanmax(current_temps))
        current_avg = float(np.nanmean(current_temps))
        current_file_title = f"{formatted_time} (최저: {current_min:.1f}°C, 최고: {current_max:.1f}°C, 평균: {current_avg:.1f}°C)\n{material_info}"
    else:
        current_file_title = f"{formatted_time}\n{material_info}"

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
        has_sensors = row["has_sensors"]
        concrete_pk = row["concrete_pk"]
        inp_dir = f"inp/{concrete_pk}"
        inp_files = glob.glob(f"{inp_dir}/*.inp")
        
        # "분석 가능" 상태이고 INP 파일이 없는 경우만 안내 메시지 표시
        if is_active and has_sensors and not inp_files:
            guide_message = "⚠️ 분석을 시작하려면 왼쪽의 '분석 시작' 버튼을 클릭하세요."
        # "센서 부족" 상태인 경우 안내 메시지 표시
        elif is_active and not has_sensors:
            guide_message = "⚠️ 센서가 부족합니다. 센서를 추가한 후 분석을 시작하세요."
        # INP 파일이 없는 경우 (분석중 상태이지만 아직 데이터가 없음)
        elif not is_active and not inp_files:
            guide_message = "⏳ 아직 수집된 데이터가 없습니다. 잠시 후 다시 확인해주세요."
    elif tbl_data is not None and len(tbl_data) == 0:
        guide_message = "분석할 콘크리트를 추가하세요."
    if guide_message:
        return html.Div([
            # 안내 메시지 (노션 스타일)
            html.Div([
                html.Div([
                    html.I(className="fas fa-info-circle fa-2x", style={"color": "#64748b", "marginBottom": "16px"}),
                    html.H5(guide_message, style={
                        "color": "#475569",
                        "fontWeight": "500",
                        "lineHeight": "1.6",
                        "margin": "0"
                    })
                ], style={
                    "textAlign": "center",
                    "padding": "60px 40px",
                    "backgroundColor": "#f8fafc",
                    "borderRadius": "12px",
                    "border": "1px solid #e2e8f0",
                    "marginTop": "60px"
                })
            ])
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
            # 시간 컨트롤 섹션 (노션 스타일)
            html.Div([
                html.Div([
                    html.H6("⏰ 시간 설정", style={
                        "fontWeight": "600",
                        "color": "#374151",
                        "marginBottom": "12px",
                        "fontSize": "14px"
                    }),
                    dcc.Slider(
                        id="time-slider-display",
                        min=slider_min,
                        max=slider_max,
                        step=1,
                        value=slider_value,
                        marks=slider_marks,
                        tooltip={"placement": "bottom", "always_visible": True},
                    ),
                ], style={
                    "padding": "16px 20px",
                    "backgroundColor": "#f9fafb",
                    "borderRadius": "8px",
                    "border": "1px solid #e5e7eb",
                    "marginBottom": "16px"
                })
            ]),
            
            # 현재 시간 정보 (노션 스타일 카드)
            html.Div([
                html.Div([
                    html.I(className="fas fa-clock me-2", style={"color": "#6366f1"}),
                    html.Div([
                        html.Div(line, style={"margin": "0"}) 
                        for line in (display_title or "시간 정보 없음").split('\n')
                    ], style={
                        "fontWeight": "500",
                        "color": "#374151",
                        "lineHeight": "1.4"
                    })
                ], style={
                    "padding": "12px 16px",
                    "backgroundColor": "white",
                    "borderRadius": "8px",
                    "border": "1px solid #e5e7eb",
                    "boxShadow": "0 1px 2px rgba(0,0,0,0.05)",
                    "marginBottom": "20px",
                    "fontSize": "14px",
                    "display": "flex",
                    "alignItems": "flex-start",
                    "gap": "8px"
                })
            ]),
            
            # 3D 뷰어 (노션 스타일)
            html.Div([
                html.Div([
                    html.H6("🎯 3D 히트맵 뷰어", style={
                        "fontWeight": "600",
                        "color": "#374151",
                        "marginBottom": "16px",
                        "fontSize": "16px"
                    }),
                    dcc.Graph(
                        id="viewer-3d-display",
                        style={
                            "height": "65vh", 
                            "borderRadius": "8px",
                            "overflow": "hidden"
                        },
                        config={"scrollZoom": True},
                        figure=fig_3d,
                    ),
                ], style={
                    "padding": "20px",
                    "backgroundColor": "white",
                    "borderRadius": "12px",
                    "border": "1px solid #e5e7eb",
                    "boxShadow": "0 1px 3px rgba(0,0,0,0.1)"
                })
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
                    
                    # INP 파일에서 물성치 정보 추출
                    material_info = "물성치 정보 없음"
                    try:
                        # 이미 파싱된 INP 파일 내용에서 물성치 정보 추출
                        elastic_modulus = None
                        poisson_ratio = None
                        density = None
                        thermal_expansion = None
                        
                        material_section = False
                        elastic_section = False
                        density_section = False
                        expansion_section = False
                        
                        for line in lines:
                            line = line.strip()
                            
                            # 섹션 시작 감지
                            if line.startswith('*MATERIAL'):
                                material_section = True
                                continue
                            elif line.startswith('*ELASTIC'):
                                elastic_section = True
                                continue
                            elif line.startswith('*DENSITY'):
                                density_section = True
                                continue
                            elif line.startswith('*EXPANSION'):
                                expansion_section = True
                                continue
                            elif line.startswith('*'):
                                # 다른 섹션 시작시 모든 플래그 리셋
                                material_section = False
                                elastic_section = False
                                density_section = False
                                expansion_section = False
                                continue
                            
                            # 물성치 데이터 파싱
                            if elastic_section and ',' in line and not line.startswith('*'):
                                parts = line.split(',')
                                if len(parts) >= 2:
                                    try:
                                        elastic_modulus = float(parts[0])  # MPa 또는 Pa
                                        poisson_ratio = float(parts[1])
                                        # 탄성계수가 Pa 단위로 저장된 경우 MPa로 변환
                                        if elastic_modulus > 1000000:
                                            elastic_modulus = elastic_modulus / 1000000  # Pa to MPa
                                    except:
                                        pass
                            
                            if density_section and line and not line.startswith('*'):
                                try:
                                    density = float(line.split(',')[0])  # kg/m³
                                except:
                                    pass
                            
                            if expansion_section and line and not line.startswith('*'):
                                try:
                                    thermal_expansion = float(line.split(',')[0])  # /°C
                                except:
                                    pass
                        
                        # 물성치 정보 문자열 생성
                        material_parts = []
                        if elastic_modulus is not None:
                            material_parts.append(f"탄성계수: {elastic_modulus:.0f}MPa")
                        if poisson_ratio is not None:
                            material_parts.append(f"포아송비: {poisson_ratio:.3f}")
                        if density is not None:
                            material_parts.append(f"밀도: {density:.0f}kg/m³")
                        if thermal_expansion is not None:
                            material_parts.append(f"열팽창: {thermal_expansion:.1e}/°C")
                        
                        if material_parts:
                            material_info = ", ".join(material_parts)
                        else:
                            material_info = "물성치 정보 없음"
                            
                    except Exception as e:
                        print(f"INP 파일에서 물성치 정보 추출 오류: {e}")
                        material_info = "물성치 정보 없음"
                    
                    if current_temps:
                        current_min = float(np.nanmin(current_temps))
                        current_max = float(np.nanmax(current_temps))
                        current_avg = float(np.nanmean(current_temps))
                        section_display_title = f"{formatted_time} (최저: {current_min:.1f}°C, 최고: {current_max:.1f}°C, 평균: {current_avg:.1f}°C)\n{material_info}"
                    else:
                        section_display_title = f"{formatted_time}\n{material_info}"
            except Exception as e:
                print(f"단면도 제목 계산 오류: {e}")
                # 계산 실패 시 기존 값 또는 viewer_data 사용
                if not section_display_title and viewer_data and 'current_file_title' in viewer_data:
                    section_display_title = viewer_data['current_file_title']
        
        # 콘크리트가 선택되지 않은 경우 viewer_data에서 가져오기 시도
        elif not section_display_title and viewer_data and 'current_file_title' in viewer_data:
            section_display_title = viewer_data['current_file_title']
        
        return html.Div([
            # 시간 컨트롤 섹션 (노션 스타일)
            html.Div([
                html.Div([
                    html.H6("⏰ 시간 설정", style={
                        "fontWeight": "600",
                        "color": "#374151",
                        "marginBottom": "12px",
                        "fontSize": "14px"
                    }),
                    dcc.Slider(
                        id="time-slider-section",
                        min=slider_min,
                        max=slider_max,
                        step=1,
                        value=slider_value,
                        marks=slider_marks,
                        tooltip={"placement": "bottom", "always_visible": True},
                    ),
                ], style={
                    "padding": "16px 20px",
                    "backgroundColor": "#f9fafb",
                    "borderRadius": "8px",
                    "border": "1px solid #e5e7eb",
                    "marginBottom": "16px"
                })
            ]),
            
            # 현재 시간 정보 (노션 스타일 카드)
            html.Div([
                html.Div([
                    html.I(className="fas fa-clock me-2", style={"color": "#6366f1"}),
                    html.Div([
                        html.Div(line, style={"margin": "0"}) 
                        for line in (section_display_title or "시간 정보 없음").split('\n')
                    ], style={
                        "fontWeight": "500",
                        "color": "#374151",
                        "lineHeight": "1.4"
                    })
                ], style={
                    "padding": "12px 16px",
                    "backgroundColor": "white",
                    "borderRadius": "8px",
                    "border": "1px solid #e5e7eb",
                    "boxShadow": "0 1px 2px rgba(0,0,0,0.05)",
                    "marginBottom": "20px",
                    "fontSize": "14px",
                    "display": "flex",
                    "alignItems": "flex-start",
                    "gap": "8px"
                })
            ]),
            
            # 단면 위치 설정 섹션 (노션 스타일)
            html.Div([
                html.Div([
                    html.H6("📍 단면 위치 설정", style={
                        "fontWeight": "600",
                        "color": "#374151",
                        "marginBottom": "16px",
                        "fontSize": "14px"
                    }),
                    html.Div([
                        dbc.InputGroup([
                            html.Span("●", style={
                                "color": "#ef4444", 
                                "fontSize": "20px", 
                                "marginRight": "8px", 
                                "lineHeight": "1"
                            }),
                            dbc.InputGroupText("X", style={"fontWeight": "500"}),
                            dbc.Input(
                                id="section-x-input", 
                                type="number", 
                                step=0.1, 
                                value=None,
                                style={"width": "100px"}
                            ),
                        ], className="me-3", style={"width": "auto"}),
                        dbc.InputGroup([
                            html.Span("●", style={
                                "color": "#3b82f6", 
                                "fontSize": "20px", 
                                "marginRight": "8px", 
                                "lineHeight": "1"
                            }),
                            dbc.InputGroupText("Y", style={"fontWeight": "500"}),
                            dbc.Input(
                                id="section-y-input", 
                                type="number", 
                                step=0.1, 
                                value=None,
                                style={"width": "100px"}
                            ),
                        ], className="me-3", style={"width": "auto"}),
                        dbc.InputGroup([
                            html.Span("●", style={
                                "color": "#22c55e", 
                                "fontSize": "20px", 
                                "marginRight": "8px", 
                                "lineHeight": "1"
                            }),
                            dbc.InputGroupText("Z", style={"fontWeight": "500"}),
                            dbc.Input(
                                id="section-z-input", 
                                type="number", 
                                step=0.1, 
                                value=None,
                                style={"width": "100px"}
                            ),
                        ], style={"width": "auto"}),
                    ], style={"display": "flex", "alignItems": "center", "flexWrap": "wrap", "gap": "12px"}),
                ], style={
                    "padding": "16px 20px",
                    "backgroundColor": "#f9fafb",
                    "borderRadius": "8px",
                    "border": "1px solid #e5e7eb",
                    "marginBottom": "20px"
                })
            ]),
            
            # 단면도 뷰어 그리드 (노션 스타일)
            html.Div([
                html.H6("📊 단면도 뷰어", style={
                    "fontWeight": "600",
                    "color": "#374151",
                    "marginBottom": "16px",
                    "fontSize": "16px"
                }),
                dbc.Row([
                    dbc.Col([
                        html.Div([
                            html.P("3D 뷰", style={
                                "fontSize": "12px", 
                                "fontWeight": "600", 
                                "color": "#6b7280", 
                                "marginBottom": "8px",
                                "textAlign": "center"
                            }),
                            dcc.Graph(
                                id="viewer-3d-section", 
                                style={"height": "30vh", "borderRadius": "6px"}, 
                                config={"scrollZoom": True}
                            ),
                        ], style={
                            "backgroundColor": "white",
                            "padding": "12px",
                            "borderRadius": "8px",
                            "border": "1px solid #e5e7eb",
                            "boxShadow": "0 1px 2px rgba(0,0,0,0.05)"
                        })
                    ], md=6),
                    dbc.Col([
                        html.Div([
                            html.P("X 단면도", style={
                                "fontSize": "12px", 
                                "fontWeight": "600", 
                                "color": "#ef4444", 
                                "marginBottom": "8px",
                                "textAlign": "center"
                            }),
                            dcc.Graph(id="viewer-section-x", style={"height": "30vh"}),
                        ], style={
                            "backgroundColor": "white",
                            "padding": "12px",
                            "borderRadius": "8px",
                            "border": "1px solid #e5e7eb",
                            "boxShadow": "0 1px 2px rgba(0,0,0,0.05)"
                        })
                    ], md=6),
                ], className="mb-3"),
                dbc.Row([
                    dbc.Col([
                        html.Div([
                            html.P("Y 단면도", style={
                                "fontSize": "12px", 
                                "fontWeight": "600", 
                                "color": "#3b82f6", 
                                "marginBottom": "8px",
                                "textAlign": "center"
                            }),
                            dcc.Graph(id="viewer-section-y", style={"height": "30vh"}),
                        ], style={
                            "backgroundColor": "white",
                            "padding": "12px",
                            "borderRadius": "8px",
                            "border": "1px solid #e5e7eb",
                            "boxShadow": "0 1px 2px rgba(0,0,0,0.05)"
                        })
                    ], md=6),
                    dbc.Col([
                        html.Div([
                            html.P("Z 단면도", style={
                                "fontSize": "12px", 
                                "fontWeight": "600", 
                                "color": "#22c55e", 
                                "marginBottom": "8px",
                                "textAlign": "center"
                            }),
                            dcc.Graph(id="viewer-section-z", style={"height": "30vh"}),
                        ], style={
                            "backgroundColor": "white",
                            "padding": "12px",
                            "borderRadius": "8px",
                            "border": "1px solid #e5e7eb",
                            "boxShadow": "0 1px 2px rgba(0,0,0,0.05)"
                        })
                    ], md=6),
                ]),
            ])
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
            
            # 위치 설정 섹션 (노션 스타일)
            html.Div([
                html.Div([
                    html.H6("📍 측정 위치 설정", style={
                        "fontWeight": "600",
                        "color": "#374151",
                        "marginBottom": "16px",
                        "fontSize": "14px"
                    }),
                    html.Div([
                        dbc.InputGroup([
                            dbc.InputGroupText("X", style={"fontWeight": "500"}),
                            dbc.Input(
                                id="temp-x-input", 
                                type="number", 
                                step=0.1, 
                                value=round(x_mid,1), 
                                min=round(x_min,2), 
                                max=round(x_max,2), 
                                style={"width": "100px"}
                            ),
                        ], className="me-3", style={"width": "auto"}),
                        dbc.InputGroup([
                            dbc.InputGroupText("Y", style={"fontWeight": "500"}),
                            dbc.Input(
                                id="temp-y-input", 
                                type="number", 
                                step=0.1, 
                                value=round(y_mid,1), 
                                min=round(y_min,2), 
                                max=round(y_max,2), 
                                style={"width": "100px"}
                            ),
                        ], className="me-3", style={"width": "auto"}),
                        dbc.InputGroup([
                            dbc.InputGroupText("Z", style={"fontWeight": "500"}),
                            dbc.Input(
                                id="temp-z-input", 
                                type="number", 
                                step=0.1, 
                                value=round(z_mid,1), 
                                min=round(z_min,2), 
                                max=round(z_max,2), 
                                style={"width": "100px"}
                            ),
                        ], style={"width": "auto"}),
                    ], style={"display": "flex", "alignItems": "center", "flexWrap": "wrap", "gap": "12px"}),
                ], style={
                    "padding": "16px 20px",
                    "backgroundColor": "#f9fafb",
                    "borderRadius": "8px",
                    "border": "1px solid #e5e7eb",
                    "marginBottom": "20px"
                })
            ]),
            
            # 분석 결과 (좌우 배치, 노션 스타일)
            dbc.Row([
                dbc.Col([
                    html.Div([
                        html.H6("🏗️ 콘크리트 구조", style={
                            "fontWeight": "600",
                            "color": "#374151",
                            "marginBottom": "12px",
                            "fontSize": "14px"
                        }),
                        dcc.Graph(
                            id="temp-viewer-3d", 
                            style={"height": "45vh", "borderRadius": "6px"}, 
                            config={"scrollZoom": True}
                        ),
                    ], style={
                        "backgroundColor": "white",
                        "padding": "16px",
                        "borderRadius": "12px",
                        "border": "1px solid #e5e7eb",
                        "boxShadow": "0 1px 3px rgba(0,0,0,0.1)"
                    })
                ], md=6),
                dbc.Col([
                    html.Div([
                        html.H6("📈 온도 변화 추이", style={
                            "fontWeight": "600",
                            "color": "#374151",
                            "marginBottom": "12px",
                            "fontSize": "14px"
                        }),
                        dcc.Graph(id="temp-time-graph", style={"height": "45vh"}),
                    ], style={
                        "backgroundColor": "white",
                        "padding": "16px",
                        "borderRadius": "12px",
                        "border": "1px solid #e5e7eb",
                        "boxShadow": "0 1px 3px rgba(0,0,0,0.1)"
                    })
                ], md=6),
            ], className="g-3"),
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
            
            from vtk.util import numpy_support as nps
            comp_labels = ['X', 'Y', 'Z', 'C4', 'C5', 'C6']  # 최대 6개까지 명칭
            for name in field_names:
                arr_obj = point_data.GetArray(name)
                ncomp = arr_obj.GetNumberOfComponents() if arr_obj else 1
                display_name = field_mapping.get(name, f"{name}")
                if ncomp == 1:
                    field_options.append({"label": display_name, "value": name})
                else:
                    # 전체 크기(magnitude)
                    field_options.append({"label": f"{display_name} (Mag)", "value": name})
                    # 각 컴포넌트
                    for ci in range(ncomp):
                        c_label = comp_labels[ci] if ci < len(comp_labels) else f"C{ci}"
                        field_options.append({"label": f"{display_name} – {c_label}", "value": f"{name}:{ci}"})
            
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
            # 컨트롤 패널 (노션 스타일)
            html.Div([
                html.Div([
                    html.H6("🎛️ 분석 설정", style={
                        "fontWeight": "600",
                        "color": "#374151",
                        "marginBottom": "16px",
                        "fontSize": "14px"
                    }),
                    dbc.Row([
                        dbc.Col([
                            html.Label("컬러맵 필드", style={
                                "fontSize": "12px", 
                                "fontWeight": "500", 
                                "color": "#6b7280",
                                "marginBottom": "4px"
                            }),
                            dcc.Dropdown(
                                id="analysis-field-dropdown",
                                options=field_options,
                                value=field_options[0]["value"] if field_options else None,
                                placeholder="필드 선택",
                                style={"fontSize": "13px"}
                            )
                        ], md=4),
                        dbc.Col([
                            html.Label("컬러맵 프리셋", style={
                                "fontSize": "12px", 
                                "fontWeight": "500", 
                                "color": "#6b7280",
                                "marginBottom": "4px"
                            }),
                            dcc.Dropdown(
                                id="analysis-preset-dropdown", 
                                options=preset_options,
                                value="rainbow",
                                placeholder="프리셋 선택",
                                style={"fontSize": "13px"}
                            )
                        ], md=4),
                        dbc.Col([
                            html.Label("시간", style={
                                "fontSize": "12px", 
                                "fontWeight": "500", 
                                "color": "#6b7280",
                                "marginBottom": "4px"
                            }),
                            dcc.Slider(
                                id="analysis-time-slider",
                                min=0,
                                max=max_idx,
                                step=1,
                                value=max_idx,
                                marks=time_marks,
                                tooltip={"placement": "bottom", "always_visible": True},
                            )
                        ], md=4),
                    ], className="g-3"),
                ], style={
                    "padding": "16px 20px",
                    "backgroundColor": "#f9fafb",
                    "borderRadius": "8px",
                    "border": "1px solid #e5e7eb",
                    "marginBottom": "16px"
                })
            ]),
            
            # 현재 파일 정보 (노션 스타일 카드)
            html.Div([
                html.Div([
                    html.I(className="fas fa-file-alt me-2", style={"color": "#6366f1"}),
                    html.Span(id="analysis-current-file-label", style={
                        "fontWeight": "500",
                        "color": "#374151"
                    })
                ], style={
                    "padding": "12px 16px",
                    "backgroundColor": "white",
                    "borderRadius": "8px",
                    "border": "1px solid #e5e7eb",
                    "boxShadow": "0 1px 2px rgba(0,0,0,0.05)",
                    "marginBottom": "16px",
                    "fontSize": "14px"
                })
            ]),
            
            # 단면 컨트롤 (노션 스타일)
            html.Div([
                html.Div([
                    html.H6("✂️ 단면 설정", style={
                        "fontWeight": "600",
                        "color": "#374151",
                        "marginBottom": "16px",
                        "fontSize": "14px"
                    }),
                    dbc.Row([
                        dbc.Col([
                            dbc.Checklist(
                                options=[{"label": "단면 보기 활성화", "value": "on"}],
                                value=[],
                                id="slice-enable",
                                switch=True,
                                style={"fontSize": "13px"}
                            )
                        ], md=3),
                        dbc.Col([
                            html.Label("축 선택", style={
                                "fontSize": "12px", 
                                "fontWeight": "500", 
                                "color": "#6b7280",
                                "marginBottom": "4px"
                            }),
                            dcc.Dropdown(
                                id="slice-axis",
                                options=[
                                    {"label": "X축 (좌→우)", "value": "X"},
                                    {"label": "Y축 (앞→뒤)", "value": "Y"},
                                    {"label": "Z축 (아래→위)", "value": "Z"},
                                ],
                                value="Z",
                                clearable=False,
                                style={"fontSize": "13px"}
                            )
                        ], md=3),
                        dbc.Col([
                            html.Label("절단 위치", style={
                                "fontSize": "12px", 
                                "fontWeight": "500", 
                                "color": "#6b7280",
                                "marginBottom": "4px"
                            }),
                            dcc.Slider(
                                id="slice-slider",
                                min=0, max=1, step=0.05, value=0.5,
                                marks={0: '0.0', 1: '1.0'},
                                tooltip={"placement": "bottom", "always_visible": True},
                            )
                        ], md=6),
                    ], className="g-3"),
                ], style={
                    "padding": "16px 20px",
                    "backgroundColor": "#f9fafb",
                    "borderRadius": "8px",
                    "border": "1px solid #e5e7eb",
                    "marginBottom": "20px"
                })
            ]),
            
            # 3D 뷰어 (노션 스타일)
            html.Div([
                html.Div([
                    html.H6("🔬 수치해석 3D 뷰어", style={
                        "fontWeight": "600",
                        "color": "#374151",
                        "marginBottom": "16px",
                        "fontSize": "16px"
                    }),
                    html.Div(id="analysis-3d-viewer", style={"height": "55vh"}),
                ], style={
                    "padding": "20px",
                    "backgroundColor": "white",
                    "borderRadius": "12px",
                    "border": "1px solid #e5e7eb",
                    "boxShadow": "0 1px 3px rgba(0,0,0,0.1)",
                    "marginBottom": "16px"
                })
            ]),

            # 컬러바 (조건부 표시, 노션 스타일)
            html.Div(id="analysis-colorbar-container", children=[
                html.Div([
                    dcc.Graph(id="analysis-colorbar", style={"height":"120px", "display": "none"})
                ], style={
                    "backgroundColor": "white",
                    "borderRadius": "8px",
                    "border": "1px solid #e5e7eb",
                    "overflow": "hidden"
                })
            ])
            
        ]), f"수치해석 결과 ({len(files)}개 파일)"
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
        
        # INP 파일에서 물성치 정보 추출
        material_info = "물성치 정보 없음"
        try:
            # 이미 파싱된 INP 파일 내용에서 물성치 정보 추출
            elastic_modulus = None
            poisson_ratio = None
            density = None
            thermal_expansion = None
            
            material_section = False
            elastic_section = False
            density_section = False
            expansion_section = False
            
            for line in lines:
                line = line.strip()
                
                # 섹션 시작 감지
                if line.startswith('*MATERIAL'):
                    material_section = True
                    continue
                elif line.startswith('*ELASTIC'):
                    elastic_section = True
                    continue
                elif line.startswith('*DENSITY'):
                    density_section = True
                    continue
                elif line.startswith('*EXPANSION'):
                    expansion_section = True
                    continue
                elif line.startswith('*'):
                    # 다른 섹션 시작시 모든 플래그 리셋
                    material_section = False
                    elastic_section = False
                    density_section = False
                    expansion_section = False
                    continue
                
                # 물성치 데이터 파싱
                if elastic_section and ',' in line and not line.startswith('*'):
                    parts = line.split(',')
                    if len(parts) >= 2:
                        try:
                            elastic_modulus = float(parts[0])  # MPa 또는 Pa
                            poisson_ratio = float(parts[1])
                            # 탄성계수가 Pa 단위로 저장된 경우 MPa로 변환
                            if elastic_modulus > 1000000:
                                elastic_modulus = elastic_modulus / 1000000  # Pa to MPa
                        except:
                            pass
                
                if density_section and line and not line.startswith('*'):
                    try:
                        # 밀도는 쉼표가 있을 수도 없을 수도 있음 (예: "2500" 또는 "2500,")
                        if ',' in line:
                            density = float(line.split(',')[0])  # kg/m³
                        else:
                            density = float(line.strip())  # kg/m³
                    except:
                        pass
                
                if expansion_section and line and not line.startswith('*'):
                    try:
                        # 열팽창계수도 쉼표가 있을 수도 없을 수도 있음 (예: "5.00e-01" 또는 "5.00e-01,")
                        thermal_expansion = float(line.split(',')[0])  # /°C
                    except:
                        pass
            
            # 물성치 정보 문자열 생성
            material_parts = []
            if elastic_modulus is not None:
                material_parts.append(f"탄성계수: {elastic_modulus:.0f}MPa")
            if poisson_ratio is not None:
                material_parts.append(f"포아송비: {poisson_ratio:.3f}")
            if density is not None:
                material_parts.append(f"밀도: {density:.0f}kg/m³")
            if thermal_expansion is not None:
                material_parts.append(f"열팽창: {thermal_expansion:.1e}/°C")
            
            if material_parts:
                material_info = ", ".join(material_parts)
            else:
                material_info = "물성치 정보 없음"
                
        except Exception as e:
            print(f"INP 파일에서 물성치 정보 추출 오류: {e}")
            material_info = "물성치 정보 없음"
        
        current_min = float(np.nanmin(temps))
        current_max = float(np.nanmax(temps))
        current_avg = float(np.nanmean(temps))
        current_file_title = f"{formatted_time} (최저: {current_min:.1f}°C, 최고: {current_max:.1f}°C, 평균: {current_avg:.1f}°C)\n{material_info}"
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
    Input("tabs-main", "active_tab"),  # 추가: 현재 활성 탭
    prevent_initial_call=True,
)
def sync_time_sliders_to_section(main_value, main_min, main_max, main_marks, active_tab):
    # 단면도 탭이 활성화되어 있을 때는 메인 슬라이더 변경을 섹션 슬라이더에 반영하지 않음
    if active_tab == "tab-section":
        raise PreventUpdate
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
    Input("tabs-main", "active_tab"),  # 추가: 현재 활성 탭
    prevent_initial_call=True,
)
def sync_section_slider_to_main(section_value, section_min, section_max, section_marks, active_tab):
    # 단면도 탭이 아닐 때는 섹션 슬라이더의 변경을 메인 슬라이더에 반영하지 않음
    if active_tab != "tab-section":
        raise PreventUpdate
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
        return html.Div("콘크리트를 선택하세요."), "", go.Figure(), 0.0, 1.0
    
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
        return html.Div("VTK/VTP 파일이 없습니다."), "", go.Figure(), 0.0, 1.0
    
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
        return html.Div("시간 정보가 포함된 VTK/VTP 파일이 없습니다."), "", go.Figure(), 0.0, 1.0
    
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
            ]), "", go.Figure(), 0.0, 1.0
        
        # 점의 개수 확인
        num_points = ds.GetNumberOfPoints()
        if num_points == 0:
            return html.Div([
                html.H5("빈 데이터셋", style={"color": "red"}),
                html.P(f"파일: {selected_file}"),
                html.P("점이 없는 데이터셋입니다.")
            ]), "", go.Figure(), 0.0, 1.0
        
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
        
        # 필드 데이터 검증 및 컴포넌트 분리 처리
        if field_name:
            # 컴포넌트 지정 패턴: "name:idx"
            if ':' in field_name:
                base_name, comp_idx_str = field_name.split(':', 1)
                try:
                    comp_idx = int(comp_idx_str)
                except ValueError:
                    comp_idx = None
                arr_base = ds.GetPointData().GetArray(base_name)
                if arr_base and comp_idx is not None and comp_idx < arr_base.GetNumberOfComponents():
                    from vtk.util import numpy_support as nps
                    np_data = nps.vtk_to_numpy(arr_base)
                    comp_data = np_data[:, comp_idx]
                    new_name = f"{base_name}_comp{comp_idx}"
                    # 중복 방지
                    if ds.GetPointData().HasArray(new_name):
                        arr = ds.GetPointData().GetArray(new_name)
                    else:
                        new_arr = nps.numpy_to_vtk(comp_data, deep=1, array_type=arr_base.GetDataType())
                        new_arr.SetName(new_name)
                        ds.GetPointData().AddArray(new_arr)
                        arr = new_arr
                    field_name = new_name
                else:
                    field_name = None
            else:
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
            ]), "", go.Figure(), slice_min, slice_max
        
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

                # 축 표시 위젯 추가 (X/Y/Z 라벨) - AxesActor 포함
                try:
                    orientation = dash_vtk.OrientationWidget(
                        children=[dash_vtk.AxesActor()],  # 기본 축 모델 추가
                        interactive=True  # 마우스 회전 등 기본 인터랙션 허용
                    )
                    view_children.append(orientation)
                except Exception:
                    pass  # 일부 dash_vtk 버전에서 OrientationWidget 또는 AxesActor가 없을 수 있음
            except Exception as bbox_error:
                print(f"바운딩 박스 생성 오류: {bbox_error}")
            
            # ───── 내부 XYZ 축 라인 추가 ─────
            try:
                axis_len = 0.5 * max(xmax - xmin, ymax - ymin, zmax - zmin)
                # 축을 모델 바깥에 배치하기 위해 바운딩박스 최소좌표에서 살짝 바깥쪽으로 이동
                margin = 0.05 * axis_len
                ox, oy, oz = xmin - margin, ymin - margin, zmin - margin
                axis_defs = {
                    'X': {'dir': (1, 0, 0), 'color': [1, 0, 0]},
                    'Y': {'dir': (0, 1, 0), 'color': [0, 1, 0]},
                    'Z': {'dir': (0, 0, 1), 'color': [0, 0, 1]},
                }
                for axis_info in axis_defs.values():
                    dx, dy, dz = axis_info['dir']
                    p0 = (ox, oy, oz)
                    p1 = (ox + dx * axis_len, oy + dy * axis_len, oz + dz * axis_len)

                    axis_pts = vtk.vtkPoints()
                    axis_pts.InsertNextPoint(*p0)
                    axis_pts.InsertNextPoint(*p1)

                    axis_lines = vtk.vtkCellArray()
                    axis_line = vtk.vtkLine()
                    axis_line.GetPointIds().SetId(0, 0)
                    axis_line.GetPointIds().SetId(1, 1)
                    axis_lines.InsertNextCell(axis_line)

                    axis_poly = vtk.vtkPolyData()
                    axis_poly.SetPoints(axis_pts)
                    axis_poly.SetLines(axis_lines)

                    axis_state = to_mesh_state(axis_poly)
                    axis_mesh = dash_vtk.Mesh(state=axis_state)
                    axis_rep = dash_vtk.GeometryRepresentation(
                        children=[axis_mesh],
                        property={'color': axis_info['color'], 'lineWidth': 3}
                    )
                    view_children.append(axis_rep)
            except Exception as axis_err:
                print(f"내부 축 생성 오류: {axis_err}")

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
            ]), "", go.Figure(), slice_min, slice_max
        
    except Exception as e:
        print(f"VTK 처리 전체 오류: {e}")
        return html.Div([
            html.H5("VTK/VTP 파싱 오류", style={"color": "red"}),
            html.P(f"파일: {selected_file}"),
            html.P(f"파일 타입: {file_type}"),
            html.P(f"오류: {str(e)}"),
            html.Hr(),
            html.P("다른 파일을 선택하거나 VTK 파일을 확인해주세요.", style={"color": "gray"})
        ]), "", go.Figure(), 0.0, 1.0

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

# 시간 슬라이더 동기화 콜백 (display용 슬라이더와 실제 슬라이더)
@callback(
    Output("time-slider", "value", allow_duplicate=True),
    Input("time-slider-display", "value"),
    prevent_initial_call=True,
)
def sync_display_slider_to_main(display_value):
    return display_value

@callback(
    Output("time-slider-display", "value", allow_duplicate=True),
    Output("time-slider-display", "min", allow_duplicate=True),
    Output("time-slider-display", "max", allow_duplicate=True),
    Output("time-slider-display", "marks", allow_duplicate=True),
    Input("time-slider", "value"),
    Input("time-slider", "min"),
    Input("time-slider", "max"),
    Input("time-slider", "marks"),
    prevent_initial_call=True,
)
def sync_main_slider_to_display(main_value, main_min, main_max, main_marks):
    return main_value, main_min, main_max, main_marks

# 3D 뷰어 동기화 콜백 (display용 뷰어와 실제 뷰어)
@callback(
    Output("viewer-3d-display", "figure", allow_duplicate=True),
    Input("viewer-3d", "figure"),
    prevent_initial_call=True,
)
def sync_viewer_to_display(main_figure):
    return main_figure


