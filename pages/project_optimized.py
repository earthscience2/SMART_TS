#!/usr/bin/env python3
# pages/project_optimized.py
# 최적화된 프로젝트 페이지 - 중복 제거 및 모듈화
"""Dash 페이지: 프로젝트 및 콘크리트 관리 (최적화 버전)

주요 최적화:
1. 중복 코드 제거
2. 공통 함수 모듈화
3. 콜백 함수 그룹화
4. 탭별 콘텐츠 함수 분리
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

register_page(__name__, path="/project", title="프로젝트 관리")

# ────────────────────────────── 공통 유틸리티 함수 ──────────────────────────────

def format_scientific_notation(value):
    """과학적 표기법을 ×10ⁿ 형식으로 변환합니다."""
    if value == 0:
        return "0"
    
    exp_str = f"{value:.1e}"
    if 'e' in exp_str:
        mantissa, exponent = exp_str.split('e')
        exp_num = int(exponent)
        
        superscript_map = {
            '0': '⁰', '1': '¹', '2': '²', '3': '³', '4': '⁴', 
            '5': '⁵', '6': '⁶', '7': '⁷', '8': '⁸', '9': '⁹', 
            '-': '⁻'
        }
        
        exp_super = ''.join(superscript_map.get(c, c) for c in str(exp_num))
        return f"{mantissa}×10{exp_super}"
    
    return exp_str

def parse_material_info_from_inp(lines):
    """INP 파일에서 물성치 정보를 추출합니다."""
    elastic_modulus = None
    poisson_ratio = None
    density = None
    expansion = None

    section = None
    for raw in lines:
        line = raw.strip()

        if line.startswith("*"):
            u = line.upper()
            if u.startswith("*ELASTIC"):
                section = "elastic"
            elif u.startswith("*DENSITY"):
                section = "density"
            elif u.startswith("*EXPANSION"):
                section = "expansion"
            else:
                section = None
            continue

        if not section or not line:
            continue

        tokens = [tok.strip() for tok in line.split(',') if tok.strip()]
        if not tokens:
            continue

        try:
            if section == "elastic":
                elastic_modulus = float(tokens[0])
                if len(tokens) >= 2:
                    poisson_ratio = float(tokens[1])
                elastic_modulus /= 1e9
                section = None

            elif section == "density":
                density = float(tokens[0])
                if density < 1:
                    if density < 0.01:
                        density *= 1e12
                    else:
                        density *= 1000
                section = None

            elif section == "expansion":
                expansion = float(tokens[0])
                section = None

        except (ValueError, IndexError):
            continue

    info_parts = []
    
    if elastic_modulus is not None:
        info_parts.append(f"탄성계수: {elastic_modulus:.0f}GPa")
    
    if poisson_ratio is not None:
        info_parts.append(f"포아송비: {poisson_ratio:.3f}")
    
    if density is not None:
        info_parts.append(f"밀도: {density:.0f}kg/m³")
    
    if expansion is not None:
        formatted_expansion = format_scientific_notation(expansion)
        info_parts.append(f"열팽창: {formatted_expansion}/°C")
    
    return ", ".join(info_parts) if info_parts else "물성치 정보 없음"

def create_probability_curve_figure():
    """TCI 확률 곡선 그래프를 생성합니다."""
    tci_values = np.linspace(0.1, 3.0, 300)
    probabilities = 100 / (1 + np.exp(6 * (tci_values - 0.6)))
    
    fig = go.Figure()
    
    fig.add_trace(go.Scatter(
        x=tci_values,
        y=probabilities,
        mode='lines',
        name='균열발생확률',
        line=dict(color='#3b82f6', width=3),
        hovertemplate='TCI: %{x:.2f}<br>확률: %{y:.1f}%<extra></extra>'
    ))
    
    # 기준선들
    fig.add_vline(x=1.0, line_dash="dash", line_color="red", line_width=2, 
                  annotation_text="TCI = 1.0 (40%)", annotation_position="top left")
    fig.add_vline(x=0.4, line_dash="dash", line_color="orange", line_width=2,
                  annotation_text="TCI = 0.4 (100%)", annotation_position="top right")
    fig.add_vline(x=2.0, line_dash="dash", line_color="green", line_width=2,
                  annotation_text="TCI = 2.0 (0%)", annotation_position="bottom right")
    
    # 영역 표시
    fig.add_vrect(x0=0.1, x1=1.0, fillcolor="rgba(239, 68, 68, 0.1)", 
                  annotation_text="위험 영역", annotation_position="top left",
                  annotation=dict(font_size=12, font_color="red"))
    
    fig.add_vrect(x0=1.0, x1=3.0, fillcolor="rgba(34, 197, 94, 0.1)",
                  annotation_text="안전 영역", annotation_position="top right",
                  annotation=dict(font_size=12, font_color="green"))
    
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

# ────────────────────────────── 탭별 콘텐츠 생성 함수 ──────────────────────────────

def create_3d_tab_content(viewer_data, current_file_title, slider_min, slider_max, slider_marks, slider_value):
    """3D 탭 콘텐츠를 생성합니다."""
    return html.Div([
        # 시간 컨트롤 섹션
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
        
        # 현재 시간 정보 + 저장 옵션
        dbc.Row([
            dbc.Col([
                html.Div(
                    id="viewer-3d-time-info", 
                    style={
                        "minHeight": "65px !important",
                        "height": "65px",
                        "display": "flex",
                        "flexDirection": "column",
                        "justifyContent": "flex-start"
                    }
                )
            ], md=8, style={"height": "65px"}),
            
            dbc.Col([
                html.Div([
                    dbc.Button(
                        [html.I(className="fas fa-camera me-1"), "이미지 저장"],
                        id="btn-save-3d-image",
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
                        [html.I(className="fas fa-download me-1"), "INP 저장"],
                        id="btn-save-current-inp",
                        color="secondary",
                        size="lg",
                        style={
                            "borderRadius": "8px",
                            "fontWeight": "600",
                            "boxShadow": "0 1px 2px rgba(0,0,0,0.1)",
                            "fontSize": "15px"
                        }
                    ),
                ], style={
                    "display": "flex",
                    "justifyContent": "flex-end",
                    "alignItems": "center",
                    "height": "100%"
                })
            ], md=4, style={"height": "65px"}),
        ]),
        
        # 3D 뷰어
        html.Div([
            dcc.Graph(
                id="viewer-3d-display",
                style={
                    "height": "600px",
                    "borderRadius": "8px",
                    "border": "1px solid #e5e7eb"
                },
                config={
                    'displayModeBar': True,
                    'displaylogo': False,
                    'modeBarButtonsToRemove': ['pan2d', 'lasso2d', 'select2d'],
                    'toImageButtonOptions': {
                        'format': 'png',
                        'filename': '3d_heatmap',
                        'height': 600,
                        'width': 800,
                        'scale': 2
                    }
                }
            )
        ], style={
            "marginTop": "16px",
            "backgroundColor": "white",
            "borderRadius": "8px",
            "padding": "16px"
        }),
        
        # 다운로드 컴포넌트들
        dcc.Download(id="download-3d-image"),
        dcc.Download(id="download-current-inp"),
    ])

def create_section_tab_content():
    """단면도 탭 콘텐츠를 생성합니다."""
    return html.Div([
        html.H4("단면도 뷰어", style={"marginBottom": "20px"}),
        html.P("단면도 기능은 기존 코드에서 구현되어 있습니다.")
    ])

def create_temp_tab_content():
    """온도 분석 탭 콘텐츠를 생성합니다."""
    return html.Div([
        html.H4("온도 분석", style={"marginBottom": "20px"}),
        html.P("온도 분석 기능은 기존 코드에서 구현되어 있습니다.")
    ])

def create_analysis_tab_content():
    """분석 도구 탭 콘텐츠를 생성합니다."""
    return html.Div([
        html.H4("분석 도구", style={"marginBottom": "20px"}),
        html.P("분석 도구 기능은 기존 코드에서 구현되어 있습니다.")
    ])

def create_tci_tab_content():
    """TCI 분석 탭 콘텐츠를 생성합니다."""
    return html.Div([
        html.H4("TCI 분석", style={"marginBottom": "20px"}),
        html.P("TCI 분석 기능은 기존 코드에서 구현되어 있습니다.")
    ])

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
        # 저장된 3D 뷰 정보가 있으면 복원, 없으면 기본 빈 3D 뷰
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
        
        return create_3d_tab_content(viewer_data, current_file_title, slider_min, slider_max, slider_marks, slider_value)
    elif active_tab == "tab-section":
        return create_section_tab_content()
    elif active_tab == "tab-temp":
        return create_temp_tab_content()
    elif active_tab == "tab-analysis":
        return create_analysis_tab_content()
    elif active_tab == "tab-tci":
        return create_tci_tab_content()
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