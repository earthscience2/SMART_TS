#!/usr/bin/env python3
# pages/project_refactored.py
# 리팩토링된 프로젝트 페이지 - 탭 모듈화 버전
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

# 탭 모듈 import
from .tabs.tab_3d import create_3d_tab_layout
from .tabs.utils import format_scientific_notation, parse_material_info_from_inp

register_page(__name__, path="/project", title="프로젝트 관리")

# ────────────────────────────── 유틸리티 함수 ──────────────────────────────

def create_probability_curve_figure():
    """로지스틱 근사식을 이용한 균열발생확률 곡선 그래프를 생성합니다."""
    import numpy as np
    import plotly.graph_objects as go
    
    # TCI 값 범위 (0.1 ~ 3.0)
    tci_values = np.linspace(0.1, 3.0, 300)
    
    # 수정된 로지스틱 근사식: 0.4에서 100%, 1.0에서 40%, 2.0에서 0%
    # P(x) = 100 / (1 + e^(6(x-0.6)))
    probabilities = 100 / (1 + np.exp(6 * (tci_values - 0.6)))
    
    fig = go.Figure()
    
    # 메인 곡선
    fig.add_trace(go.Scatter(
        x=tci_values,
        y=probabilities,
        mode='lines',
        name='균열발생확률',
        line=dict(color='#3b82f6', width=3),
        hovertemplate='TCI: %{x:.2f}<br>확률: %{y:.1f}%<extra></extra>'
    ))
    
    # 중요한 기준선들 추가
    # TCI = 1.0 기준선 (40% 확률)
    fig.add_vline(x=1.0, line_dash="dash", line_color="red", line_width=2, 
                  annotation_text="TCI = 1.0 (40%)", annotation_position="top left")
    
    # TCI = 0.4 기준선 (100% 확률)
    fig.add_vline(x=0.4, line_dash="dash", line_color="orange", line_width=2,
                  annotation_text="TCI = 0.4 (100%)", annotation_position="top right")
    
    # TCI = 2.0 기준선 (0% 확률)  
    fig.add_vline(x=2.0, line_dash="dash", line_color="green", line_width=2,
                  annotation_text="TCI = 2.0 (0%)", annotation_position="bottom right")
    
    # 안전/위험 영역 표시
    fig.add_vrect(x0=0.1, x1=1.0, fillcolor="rgba(239, 68, 68, 0.1)", 
                  annotation_text="위험 영역", annotation_position="top left",
                  annotation=dict(font_size=12, font_color="red"))
    
    fig.add_vrect(x0=1.0, x1=3.0, fillcolor="rgba(34, 197, 94, 0.1)",
                  annotation_text="안전 영역", annotation_position="top right",
                  annotation=dict(font_size=12, font_color="green"))
    
    # 그래프 스타일링
    fig.update_layout(
        title={
            'text': "온도균열지수(TCI)와 균열발생확률의 관계",
            'x': 0.5,
            'font': {'size': 18, 'color': '#1f2937'}
        },
        xaxis=dict(
            title="온도균열지수 (TCI)",
            gridcolor='#f3f4f6',
            showgrid=True,
            range=[0.1, 3.0],
            dtick=0.2
        ),
        yaxis=dict(
            title="균열발생확률 (%)",
            gridcolor='#f3f4f6',
            showgrid=True,
            range=[0, 100],
            dtick=10
        ),
        plot_bgcolor='white',
        paper_bgcolor='white',
        showlegend=False,
        margin=dict(l=60, r=60, t=80, b=60),
        font=dict(family="Arial, sans-serif", size=12, color="#374151")
    )
    
    return fig

# ────────────────────────────── 레이아웃 ──────────────────────────────

layout = dbc.Container([
    # URL 저장용 dcc.Location
    dcc.Location(id="project-url", refresh=False),
    
    # 전역 상태 저장용 Store 컴포넌트들
    dcc.Store(id="current-time-store"),
    dcc.Store(id="current-file-title-store"),
    dcc.Store(id="viewer-3d-store"),
    dcc.Store(id="section-coord-store"),
    
    # 알림 메시지
    dbc.Alert(id="project-alert", is_open=False, duration=4000),
    
    # 삭제 확인 다이얼로그
    dbc.Modal([
        dbc.ModalHeader("콘크리트 삭제 확인"),
        dbc.ModalBody("선택한 콘크리트를 삭제하시겠습니까?"),
        dbc.ModalFooter([
            dbc.Button("취소", id="confirm-del-concrete-cancel", className="ms-auto"),
            dbc.Button("삭제", id="confirm-del-concrete", color="danger"),
        ]),
    ], id="confirm-del-concrete-modal", is_open=False),
    
    # 메인 콘텐츠
    dbc.Row([
        # 왼쪽 사이드바 (콘크리트 목록)
        dbc.Col([
            html.Div([
                # 제목
                html.H4("콘크리트 목록", style={
                    "fontWeight": "600",
                    "color": "#1f2937",
                    "marginBottom": "20px",
                    "paddingBottom": "12px",
                    "borderBottom": "2px solid #e5e7eb"
                }),
                
                # 콘크리트 제목 (동적)
                html.H6(id="concrete-title", style={
                    "color": "#6b7280",
                    "fontWeight": "500",
                    "marginBottom": "16px"
                }),
                
                # 콘크리트 테이블
                dash_table.DataTable(
                    id="tbl-concrete",
                    columns=[],
                    data=[],
                    selected_rows=[],
                    style_table={
                        "borderRadius": "8px",
                        "overflow": "hidden",
                        "border": "1px solid #e5e7eb"
                    },
                    style_header={
                        "backgroundColor": "#f9fafb",
                        "color": "#374151",
                        "fontWeight": "600",
                        "textAlign": "center",
                        "border": "none"
                    },
                    style_cell={
                        "textAlign": "center",
                        "padding": "12px 8px",
                        "border": "1px solid #f3f4f6",
                        "fontSize": "13px"
                    },
                    style_data_conditional=[],
                    style_data={
                        "backgroundColor": "white",
                        "color": "#374151"
                    },
                    style_selected={
                        "backgroundColor": "#dbeafe !important",
                        "color": "#1e40af !important"
                    },
                    row_selectable="single",
                    sort_action="native",
                    sort_mode="multi",
                    page_action="none",
                    style_as_list_view=True,
                    tooltip_header={
                        "status": "상태: 분석 가능/센서 부족/분석중",
                        "pour_date": "타설 날짜 (YY.MM.DD)",
                        "elapsed_days": "타설 후 경과일",
                        "shape": "콘크리트 형태 정보"
                    },
                    tooltip_delay=0,
                    tooltip_duration=None
                ),
                
                # 버튼 그룹
                html.Div([
                    dbc.Button(
                        [html.I(className="fas fa-play me-1"), "분석 시작"],
                        id="btn-concrete-analyze",
                        color="primary",
                        size="lg",
                        style={
                            "borderRadius": "8px",
                            "fontWeight": "600",
                            "boxShadow": "0 1px 2px rgba(0,0,0,0.1)",
                            "fontSize": "15px",
                            "marginRight": "8px"
                        }
                    ),
                    dbc.Button(
                        [html.I(className="fas fa-trash me-1"), "삭제"],
                        id="btn-concrete-del",
                        color="danger",
                        size="lg",
                        style={
                            "borderRadius": "8px",
                            "fontWeight": "600",
                            "boxShadow": "0 1px 2px rgba(0,0,0,0.1)",
                            "fontSize": "15px"
                        }
                    ),
                ], style={
                    "marginTop": "16px",
                    "display": "flex",
                    "justifyContent": "center"
                })
            ], style={
                "backgroundColor": "white",
                "borderRadius": "12px",
                "boxShadow": "0 1px 3px rgba(0,0,0,0.1)",
                "border": "1px solid #e2e8f0",
                "padding": "24px"
            })
        ], width=3),
        
        # 오른쪽 메인 콘텐츠
        dbc.Col([
            html.Div([
                # 탭 네비게이션
                html.Div([
                    dbc.Tabs([
                        dbc.Tab(
                            html.Div([
                                html.I(className="fas fa-cube me-2"),
                                "3D 뷰어"
                            ], style={"display": "flex", "alignItems": "center"}),
                            tab_id="tab-3d",
                            label_style={
                                "fontWeight": "500",
                                "color": "#6b7280",
                                "border": "none",
                                "padding": "12px 20px"
                            },
                            tab_style={
                                "backgroundColor": "#f9fafb",
                                "border": "1px solid #e2e8f0",
                                "borderBottom": "none",
                                "borderRadius": "8px 8px 0 0"
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
                            html.Div([
                                html.I(className="fas fa-cut me-2"),
                                "단면도"
                            ], style={"display": "flex", "alignItems": "center"}),
                            tab_id="tab-section",
                            label_style={
                                "fontWeight": "500",
                                "color": "#6b7280",
                                "border": "none",
                                "padding": "12px 20px"
                            },
                            tab_style={
                                "backgroundColor": "#f9fafb",
                                "border": "1px solid #e2e8f0",
                                "borderBottom": "none",
                                "borderRadius": "8px 8px 0 0"
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
                            html.Div([
                                html.I(className="fas fa-thermometer-half me-2"),
                                "온도 분석"
                            ], style={"display": "flex", "alignItems": "center"}),
                            tab_id="tab-temp",
                            label_style={
                                "fontWeight": "500",
                                "color": "#6b7280",
                                "border": "none",
                                "padding": "12px 20px"
                            },
                            tab_style={
                                "backgroundColor": "#f9fafb",
                                "border": "1px solid #e2e8f0",
                                "borderBottom": "none",
                                "borderRadius": "8px 8px 0 0"
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
                            html.Div([
                                html.I(className="fas fa-chart-line me-2"),
                                "분석 도구"
                            ], style={"display": "flex", "alignItems": "center"}),
                            tab_id="tab-analysis",
                            label_style={
                                "fontWeight": "500",
                                "color": "#6b7280",
                                "border": "none",
                                "padding": "12px 20px"
                            },
                            tab_style={
                                "backgroundColor": "#f9fafb",
                                "border": "1px solid #e2e8f0",
                                "borderBottom": "none",
                                "borderRadius": "8px 8px 0 0"
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
                            html.Div([
                                html.I(className="fas fa-exclamation-triangle me-2"),
                                "TCI 분석"
                            ], style={"display": "flex", "alignItems": "center"}),
                            tab_id="tab-tci",
                            label_style={
                                "fontWeight": "500",
                                "color": "#6b7280",
                                "border": "none",
                                "padding": "12px 20px"
                            },
                            tab_style={
                                "backgroundColor": "#f9fafb",
                                "border": "1px solid #e2e8f0",
                                "borderBottom": "none",
                                "borderRadius": "8px 8px 0 0"
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
                    dcc.Slider(id="tci-time-slider", min=0, max=5, step=1, value=0, marks={}),
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
                    html.Div(id="section-time-info"),
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
], fluid=True, style={"padding": "24px", "backgroundColor": "#f8fafc", "minHeight": "100vh"})

# ────────────────────────────── 콜백 함수들 ──────────────────────────────

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
    """콘크리트 데이터를 로드합니다."""
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
    
    # 테이블 데이터 구성
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
    
    # 정렬 (분석중 → 분석 가능 → 센서 부족 순)
    table_data.sort(key=lambda x: x["status_sort"])
    
    # 컬럼 정의
    columns = [
        {"name": "상태", "id": "status", "type": "text"},
        {"name": "이름", "id": "name", "type": "text"},
        {"name": "타설일", "id": "pour_date", "type": "text"},
        {"name": "경과일", "id": "elapsed_days", "type": "text"},
        {"name": "형태", "id": "shape", "type": "text"},
    ]
    
    # 스타일 조건부 설정
    style_data_conditional = [
        {
            "if": {"filter_query": "{status} = '분석 가능'"},
            "backgroundColor": "#dcfce7",
            "color": "#166534"
        },
        {
            "if": {"filter_query": "{status} = '센서 부족'"},
            "backgroundColor": "#fef3c7",
            "color": "#92400e"
        },
        {
            "if": {"filter_query": "{status} = '분석중'"},
            "backgroundColor": "#dbeafe",
            "color": "#1e40af"
        }
    ]
    
    # 시간 슬라이더 설정 (기본값)
    time_min, time_max, time_marks = 0, 5, {}
    
    return (
        table_data, columns, [], style_data_conditional,
        True, True, f"{proj_name} · 콘크리트 목록 ({len(table_data)}개)",
        time_min, time_max, 0, time_marks, None
    )

@callback(
    Output("tab-content", "children"),
    Input("tabs-main", "active_tab"),
    Input("tbl-concrete", "selected_rows"),
    State("tbl-concrete", "data"),
    State("viewer-3d-store", "data"),
    State("current-file-title-store", "data"),
    prevent_initial_call=True,
)
def switch_tab(active_tab, selected_rows, tbl_data, viewer_data, current_file_title):
    """탭 전환 시 콘텐츠를 업데이트합니다."""
    from datetime import datetime as dt_import  # 명시적 import로 충돌 방지
    
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
    elif tbl_data is None:
        guide_message = "콘크리트 데이터를 불러오는 중입니다..."
    
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
    
    # 탭별 콘텐츠 반환
    if active_tab == "tab-3d":
        return create_3d_tab_layout()
    elif active_tab == "tab-section":
        # 단면도 탭 (기존 코드 유지)
        return html.Div("단면도 탭 - 구현 예정")
    elif active_tab == "tab-temp":
        # 온도 분석 탭 (기존 코드 유지)
        return html.Div("온도 분석 탭 - 구현 예정")
    elif active_tab == "tab-analysis":
        # 분석 도구 탭 (기존 코드 유지)
        return html.Div("분석 도구 탭 - 구현 예정")
    elif active_tab == "tab-tci":
        # TCI 분석 탭 (기존 코드 유지)
        return html.Div("TCI 분석 탭 - 구현 예정")
    else:
        return html.Div("알 수 없는 탭")

# 기존 콜백 함수들은 그대로 유지 (필요한 것들만)
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
    """콘크리트 선택 시 상태를 업데이트합니다."""
    if not selected_rows or not tbl_data:
        return True, True, "콘크리트를 선택하세요", None, 0, 5, 0, {}
    
    row = pd.DataFrame(tbl_data).iloc[selected_rows[0]]
    concrete_pk = row["concrete_pk"]
    concrete_name = row["name"]
    is_active = row["activate"] == "활성"
    has_sensors = row["has_sensors"]
    
    # INP 파일 확인
    inp_dir = f"inp/{concrete_pk}"
    inp_files = sorted(glob.glob(f"{inp_dir}/*.inp"))
    
    # 분석 시작 버튼 활성화 조건
    can_analyze = is_active and has_sensors and not inp_files
    
    # 시간 슬라이더 설정
    if inp_files:
        time_max = len(inp_files) - 1
        time_marks = {i: f"T{i}" for i in range(len(inp_files))}
    else:
        time_max = 5
        time_marks = {}
    
    return (
        False,  # 삭제 버튼 활성화
        not can_analyze,  # 분석 시작 버튼 조건부 활성화
        f"선택됨: {concrete_name}",
        None,
        0, time_max, 0, time_marks
    )

# 추가 콜백 함수들은 필요에 따라 구현... 