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

register_page(__name__, path="/temp", title="온도 분석")



# ────────────────────────────── 유틸리티 함수 ──────────────────────────────
# INP 파일 내 물성치(탄성계수, 포아송비, 밀도, 열팽창계수)를 보다 견고하게 추출하기 위한 헬퍼
# 밀도 값이 0 으로 표시되던 문제를 단위 자동 변환(tonne/mm³, g/cm³ → kg/m³) 로 해결

def format_scientific_notation(value):
    """과학적 표기법을 ×10ⁿ 형식으로 변환합니다.
    
    예: 1.0e-05 → 1.0×10⁻⁵
    """
    if value == 0:
        return "0"
    
    # 과학적 표기법으로 변환
    exp_str = f"{value:.1e}"
    
    # e 표기법을 × 표기법으로 변환
    if 'e' in exp_str:
        mantissa, exponent = exp_str.split('e')
        exp_num = int(exponent)
        
        # 상첨자 숫자 변환
        superscript_map = {
            '0': '⁰', '1': '¹', '2': '²', '3': '³', '4': '⁴', 
            '5': '⁵', '6': '⁶', '7': '⁷', '8': '⁸', '9': '⁹', 
            '-': '⁻'
        }
        
        # 지수를 상첨자로 변환
        exp_super = ''.join(superscript_map.get(c, c) for c in str(exp_num))
        
        return f"{mantissa}×10{exp_super}"
    
    return exp_str

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

def parse_material_info_from_inp(lines):
    """INP 파일 라인 리스트에서 물성치 정보를 추출하여 문자열로 반환합니다.

    반환 형식 예시: "탄성계수: 30000MPa, 포아송비: 0.200, 밀도: 2500kg/m³, 열팽창: 1.0×10⁻⁵/°C"
    해당 값이 없으면 항목을 건너뛴다. 아무 항목도 없으면 "물성치 정보 없음" 반환.
    """
    elastic_modulus = None  # MPa
    poisson_ratio = None
    density = None          # kg/m³
    expansion = None        # 1/°C

    section = None  # 현재 파싱 중인 섹션 이름
    for raw in lines:
        line = raw.strip()

        # 섹션 식별
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
                # Pa → GPa 변환
                elastic_modulus /= 1e9
                section = None  # 한 줄만 사용

            elif section == "density":
                density = float(tokens[0])
                # 단위 자동 변환
                if density < 1e-3:      # tonne/mm^3 (예: 2.40e-9)
                    density *= 1e12     # 1 tonne/mm³ = 1e12 kg/m³
                elif density < 10:      # g/cm³ (예: 2.4)
                    density *= 1000     # g/cm³ → kg/m³
                section = None

            elif section == "expansion":
                expansion = float(tokens[0])
                section = None
        except ValueError:
            # 숫자 파싱 실패 시 해당 항목 무시
            continue

    parts = []
    if elastic_modulus is not None:
        parts.append(f"탄성계수: {elastic_modulus:.1f}GPa")
    if poisson_ratio is not None:
        parts.append(f"포아송비: {poisson_ratio:.1f}")
    if density is not None:
        parts.append(f"밀도: {density:.0f}kg/m³")
    if expansion is not None:
        parts.append(f"열팽창: {expansion:.1f}×10⁻⁵/°C")

    return ", ".join(parts) if parts else "물성치 정보 없음"

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
                                id="temp-project-alert",
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
        
        # ── 다운로드 컴포넌트들
        dcc.Download(id="download-3d-image"),
        dcc.Download(id="download-current-inp"),
        dcc.Download(id="download-section-image"),
        dcc.Download(id="download-section-inp"),
        dcc.Download(id="download-temp-image"),
        dcc.Download(id="download-temp-data"),
        
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
                    
                    // 두 박스 높이 맞추기 함수
                    if (!window.boxHeightHandler) {
                        window.boxHeightHandler = true;
                        
                        function matchBoxHeights() {
                            const timeInfoBox = document.getElementById('viewer-3d-time-info');
                            const saveOptionsBox = timeInfoBox ? timeInfoBox.parentElement.nextElementSibling.querySelector('div[style*="backgroundColor"]') : null;
                            
                            if (timeInfoBox && saveOptionsBox) {
                                // 높이 초기화
                                timeInfoBox.style.minHeight = '';
                                saveOptionsBox.style.minHeight = '';
                                
                                // 실제 높이 측정
                                const timeInfoHeight = timeInfoBox.offsetHeight;
                                const saveOptionsHeight = saveOptionsBox.offsetHeight;
                                
                                // 더 높은 높이로 맞춤
                                const maxHeight = Math.max(timeInfoHeight, saveOptionsHeight);
                                timeInfoBox.style.minHeight = maxHeight + 'px';
                                saveOptionsBox.style.minHeight = maxHeight + 'px';
                            }
                        }
                        
                        // 페이지 로드 후 높이 맞춤
                        setTimeout(matchBoxHeights, 100);
                        
                        // 콘텐츠 변경 감지를 위한 MutationObserver
                        const observer = new MutationObserver(function(mutations) {
                            mutations.forEach(function(mutation) {
                                if (mutation.type === 'childList' || mutation.type === 'characterData') {
                                    setTimeout(matchBoxHeights, 50);
                                }
                            });
                        });
                        
                        // 감시 시작
                        const targetNode = document.getElementById('viewer-3d-time-info');
                        if (targetNode) {
                            observer.observe(targetNode, {
                                childList: true,
                                subtree: true,
                                characterData: true
                            });
                        }
                        
                        // 윈도우 리사이즈 시에도 높이 재조정
                        window.addEventListener('resize', function() {
                            setTimeout(matchBoxHeights, 100);
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
                        dcc.Slider(id="time-slider-section", min=0, max=5, step=1, value=0, marks={}),  # 단면도용 독립 슬라이더 복원
                        # TCI 관련 컴포넌트들 - 제거됨
                        # dcc.Slider(id="temp-tci-time-slider", min=0, max=5, step=1, value=0, marks={}),  # TCI용 시간 슬라이더
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
                        html.Div(id="section-time-info"),  # 단면도용 시간 정보 표시 컴포넌트
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
        return [], [], [], [], True, "프로젝트를 선택하세요", 0, 5, 0, {}, None
    
    try:
        # 프로젝트 정보 로드
        df_proj = api_db.get_project_data(project_pk=project_pk)
        if df_proj.empty:
            return [], [], [], [], True, "존재하지 않는 프로젝트", 0, 5, 0, {}, None
            
        proj_row = df_proj.iloc[0]
        proj_name = proj_row["name"]
        
        # 해당 프로젝트의 콘크리트 데이터 로드
        df_conc = api_db.get_concrete_data(project_pk=project_pk)
        if df_conc.empty:
            return [], [], [], [], True, f"{proj_name} · 콘크리트 목록 (0개)", 0, 5, 0, {}, None
        
    except Exception as e:
        print(f"프로젝트 로딩 오류: {e}")
        return [], [], [], [], True, "프로젝트 정보를 불러올 수 없음", 0, 5, 0, {}, None
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
    
    return table_data, columns, [], style_data_conditional, True, title, 0, 5, 0, {}, None

# ───────────────────── ③ 콘크리트 선택 콜백 ────────────────────
@callback(
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
    if not selected_rows or not tbl_data:
        return True, "", "", 0, 5, 0, {}
    
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
                    
                    # INP 파일에서 물성치 정보 추출
                    material_info = parse_material_info_from_inp(lines)
                    
                    if current_temps:
                        current_min = float(np.nanmin(current_temps))
                        current_max = float(np.nanmax(current_temps))
                        current_avg = float(np.nanmean(current_temps))
                        current_file_title = f"{formatted_time} (최저: {current_min:.1f}°C, 최고: {current_max:.1f}°C, 평균: {current_avg:.1f}°C)\n{material_info}"
                    else:
                        current_file_title = f"{formatted_time}\n{material_info}"
                        
                except Exception as e:
                    print(f"온도 데이터 파싱 오류: {e}")
                    current_file_title = f"{os.path.basename(latest_file)}"
            
    return delete_disabled, title, current_file_title, slider_min, slider_max, slider_value, slider_marks

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
    if not selected_rows or not tbl_data:
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
    material_info = parse_material_info_from_inp(lines)

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
    Input("tbl-concrete", "selected_rows"),
    State("tbl-concrete", "data"),
    State("viewer-3d-store", "data"),
    State("current-file-title-store", "data"),
    prevent_initial_call=True,
)
def switch_tab(active_tab, selected_rows, tbl_data, viewer_data, current_file_title):
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
    # 이하 기존 코드 유지
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
        # 시간 정보 계산 (콘크리트가 선택된 경우 항상 계산)
        display_title = current_file_title
        
                        # 콘크리트가 선택된 경우 시간 정보를 직접 계산하여 확실히 표시
        if selected_rows and tbl_data and len(selected_rows) > 0:
            try:
                row = pd.DataFrame(tbl_data).iloc[selected_rows[0]]
                concrete_pk = row["concrete_pk"]
                inp_dir = f"inp/{concrete_pk}"
                inp_files = sorted(glob.glob(f"{inp_dir}/*.inp"))
                
                if inp_files:
                    # 현재 슬라이더 값에 해당하는 파일 선택
                    file_idx = min(slider_value if slider_value is not None else len(inp_files)-1, len(inp_files)-1)
                    latest_file = inp_files[file_idx]
                    time_str = os.path.basename(latest_file).split(".")[0]
                    dt = dt_import.strptime(time_str, "%Y%m%d%H")
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
                    
                    # INP 파일에서 물성치 정보 추출
                    material_info = parse_material_info_from_inp(lines)
                    
                    if current_temps:
                        current_min = float(np.nanmin(current_temps))
                        current_max = float(np.nanmax(current_temps))
                        current_avg = float(np.nanmean(current_temps))
                        display_title = f"{formatted_time} (최저: {current_min:.1f}°C, 최고: {current_max:.1f}°C, 평균: {current_avg:.1f}°C)\n{material_info}"
                    else:
                        display_title = f"{formatted_time}\n{material_info}"
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
            
            # 현재 시간 정보 + 저장 옵션 (한 줄 배치)
            dbc.Row([
                # 왼쪽: 현재 시간/물성치 정보
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
                ], md=8, style={
                    "height": "65px"
                }),
                
                # 오른쪽: 저장 버튼들
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
                                "width": "120px",
                                "height": "48px",
                                "marginRight": "16px"
                            }
                        ),
                        dbc.Button(
                            [html.I(className="fas fa-file-download me-1"), "INP 파일 저장"],
                            id="btn-save-current-inp",
                            color="success",
                            size="lg",
                            style={
                                "borderRadius": "8px",
                                "fontWeight": "600",
                                "boxShadow": "0 1px 2px rgba(0,0,0,0.1)",
                                "fontSize": "15px",
                                "width": "140px",
                                "height": "48px"
                            }
                        ),
                    ], style={"display": "flex", "justifyContent": "center", "alignItems": "center", "height": "65px"})
                ], md=4, style={
                    "height": "65px"
                }),
            ], className="mb-3 align-items-stretch h-100", style={"minHeight": "65px"}),
            
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
        # 단면도 탭: 독립적인 슬라이더 설정 (기본값 먼저 설정)
        slider_min, slider_max, slider_marks, slider_value = 0, 5, {}, 0
        
        # 선택된 콘크리트가 있으면 해당 INP 파일 기반으로 슬라이더 설정
        if selected_rows and tbl_data and len(selected_rows) > 0:
            row = pd.DataFrame(tbl_data).iloc[selected_rows[0]]
            concrete_pk = row["concrete_pk"]
            inp_dir = f"inp/{concrete_pk}"
            inp_files = sorted(glob.glob(f"{inp_dir}/*.inp"))
            
            if inp_files:
                # 시간 파싱
                times = []
                for f in inp_files:
                    try:
                        time_str = os.path.basename(f).split(".")[0]
                        dt = dt_import.strptime(time_str, "%Y%m%d%H")
                        times.append(dt)
                    except:
                        continue
                
                if times:
                    max_idx = len(times) - 1
                    slider_min, slider_max = 0, max_idx
                    slider_value = max_idx  # 최신 파일로 초기화
                    
                    # 슬라이더 마크 설정
                    marks = {}
                    seen_dates = set()
                    for i, dt in enumerate(times):
                        date_str = dt.strftime("%m/%d")
                        if date_str not in seen_dates:
                            marks[i] = date_str
                            seen_dates.add(date_str)
                    slider_marks = marks
        
        return html.Div([
            # 시간 컨트롤 섹션 (노션 스타일) - 독립적인 단면도용 슬라이더
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
                        min=slider_min if slider_min is not None else 0,
                        max=slider_max if slider_max is not None and slider_max > 0 else 5,
                        step=1,
                        value=slider_value if slider_value is not None else 0,
                        marks=slider_marks if isinstance(slider_marks, dict) else {},
                        tooltip={"placement": "bottom", "always_visible": True},
                        updatemode='drag',
                    ),
                ], style={
                    "padding": "16px 20px",
                    "backgroundColor": "#f9fafb",
                    "borderRadius": "8px",
                    "border": "1px solid #e5e7eb",
                    "marginBottom": "16px"
                })
            ]),
            
            # 현재 시간 정보 + 저장 옵션 (한 줄 배치)
            dbc.Row([
                # 왼쪽: 현재 시간/물성치 정보
                dbc.Col([
                    html.Div(id="section-time-info")
                ], md=8, style={
                    "height": "65px"
                }),
                
                # 오른쪽: 저장 버튼들
                dbc.Col([
                    html.Div([
                        dbc.Button(
                            [html.I(className="fas fa-camera me-1"), "이미지 저장"],
                            id="btn-save-section-image",
                            color="primary",
                            size="lg",
                            style={
                                "borderRadius": "8px",
                                "fontWeight": "600",
                                "boxShadow": "0 1px 2px rgba(0,0,0,0.1)",
                                "fontSize": "15px",
                                "width": "120px",
                                "height": "48px",
                                "marginRight": "16px"
                            }
                        ),
                        dbc.Button(
                            [html.I(className="fas fa-file-download me-1"), "INP 파일 저장"],
                            id="btn-save-section-inp",
                            color="success",
                            size="lg",
                            style={
                                "borderRadius": "8px",
                                "fontWeight": "600",
                                "boxShadow": "0 1px 2px rgba(0,0,0,0.1)",
                                "fontSize": "15px",
                                "width": "140px",
                                "height": "48px"
                            }
                        ),
                    ], style={"display": "flex", "justifyContent": "center", "alignItems": "center", "height": "65px"})
                ], md=4, style={
                    "height": "65px"
                }),
            ], className="mb-4 align-items-stretch h-100", style={"minHeight": "65px"}),
            
            # 단면 위치 설정 섹션 (노션 스타일)
            html.Div([
                html.Div([
                    html.H6("📍 단면 위치 설정", style={
                        "fontWeight": "600",
                        "color": "#374151",
                        "marginBottom": "12px",
                        "fontSize": "14px"
                    }),
                    dbc.Row([
                        dbc.Col([
                                                            dbc.Card([
                                    dbc.CardBody([
                                        html.Div([
                                            html.I(className="fas fa-arrows-alt-h", style={
                                                "color": "#ef4444", 
                                                "fontSize": "14px", 
                                                "marginRight": "6px"
                                            }),
                                            html.Span("X축", style={
                                                "fontWeight": "600",
                                                "color": "#ef4444",
                                                "fontSize": "13px"
                                            })
                                        ], style={"marginBottom": "4px"}),
                                        dbc.Input(
                                            id="section-x-input", 
                                            type="number", 
                                            step=0.1, 
                                            value=None,
                                            placeholder="X 좌표",
                                            style={"width": "100%"}
                                        )
                                    ], style={"padding": "8px"})
                                ], style={
                                    "border": "1px solid #fecaca",
                                    "backgroundColor": "#fef2f2"
                                })
                        ], md=4),
                        dbc.Col([
                                                            dbc.Card([
                                    dbc.CardBody([
                                        html.Div([
                                            html.I(className="fas fa-arrows-alt-v", style={
                                                "color": "#3b82f6", 
                                                "fontSize": "14px", 
                                                "marginRight": "6px"
                                            }),
                                            html.Span("Y축", style={
                                                "fontWeight": "600",
                                                "color": "#3b82f6",
                                                "fontSize": "13px"
                                            })
                                        ], style={"marginBottom": "4px"}),
                                        dbc.Input(
                                            id="section-y-input", 
                                            type="number", 
                                            step=0.1, 
                                            value=None,
                                            placeholder="Y 좌표",
                                            style={"width": "100%"}
                                        )
                                    ], style={"padding": "8px"})
                                ], style={
                                    "border": "1px solid #bfdbfe",
                                    "backgroundColor": "#eff6ff"
                                })
                        ], md=4),
                        dbc.Col([
                                                            dbc.Card([
                                    dbc.CardBody([
                                        html.Div([
                                            html.I(className="fas fa-arrows-alt", style={
                                                "color": "#22c55e", 
                                                "fontSize": "14px", 
                                                "marginRight": "6px"
                                            }),
                                            html.Span("Z축", style={
                                                "fontWeight": "600",
                                                "color": "#22c55e",
                                                "fontSize": "13px"
                                            })
                                        ], style={"marginBottom": "4px"}),
                                        dbc.Input(
                                            id="section-z-input", 
                                            type="number", 
                                            step=0.1, 
                                            value=None,
                                            placeholder="Z 좌표",
                                            style={"width": "100%"}
                                        )
                                    ], style={"padding": "8px"})
                                ], style={
                                    "border": "1px solid #bbf7d0",
                                    "backgroundColor": "#f0fdf4"
                                })
                        ], md=4),
                    ], className="g-3"),
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
            
            # 위치 설정 + 저장 버튼 섹션 (한 줄 배치)
            dbc.Row([
                # 왼쪽: 측정 위치 설정
                dbc.Col([
                    html.Div([
                        html.H6("📍 측정 위치 설정", style={
                            "fontWeight": "600",
                            "color": "#374151",
                            "marginBottom": "12px",
                            "fontSize": "14px"
                        }),
                        dbc.Row([
                            dbc.Col([
                                dbc.Card([
                                    dbc.CardBody([
                                        html.Div([
                                            html.I(className="fas fa-arrows-alt-h", style={
                                                "color": "#ef4444", 
                                                "fontSize": "14px", 
                                                "marginRight": "6px"
                                            }),
                                            html.Span("X축", style={
                                                "fontWeight": "600",
                                                "color": "#ef4444",
                                                "fontSize": "13px"
                                            })
                                        ], style={"marginBottom": "4px"}),
                                        dbc.Input(
                                            id="temp-x-input", 
                                            type="number", 
                                            step=0.1, 
                                            value=round(x_mid,1), 
                                            min=round(x_min,2), 
                                            max=round(x_max,2),
                                            placeholder="X 좌표",
                                            style={"width": "100%"}
                                        )
                                    ], style={"padding": "8px"})
                                ], style={
                                    "border": "1px solid #fecaca",
                                    "backgroundColor": "#fef2f2"
                                })
                            ], md=4),
                            dbc.Col([
                                dbc.Card([
                                    dbc.CardBody([
                                        html.Div([
                                            html.I(className="fas fa-arrows-alt-v", style={
                                                "color": "#3b82f6", 
                                                "fontSize": "14px", 
                                                "marginRight": "6px"
                                            }),
                                            html.Span("Y축", style={
                                                "fontWeight": "600",
                                                "color": "#3b82f6",
                                                "fontSize": "13px"
                                            })
                                        ], style={"marginBottom": "4px"}),
                                        dbc.Input(
                                            id="temp-y-input", 
                                            type="number", 
                                            step=0.1, 
                                            value=round(y_mid,1), 
                                            min=round(y_min,2), 
                                            max=round(y_max,2),
                                            placeholder="Y 좌표",
                                            style={"width": "100%"}
                                        )
                                    ], style={"padding": "8px"})
                                ], style={
                                    "border": "1px solid #bfdbfe",
                                    "backgroundColor": "#eff6ff"
                                })
                            ], md=4),
                            dbc.Col([
                                dbc.Card([
                                    dbc.CardBody([
                                        html.Div([
                                            html.I(className="fas fa-arrows-alt", style={
                                                "color": "#22c55e", 
                                                "fontSize": "14px", 
                                                "marginRight": "6px"
                                            }),
                                            html.Span("Z축", style={
                                                "fontWeight": "600",
                                                "color": "#22c55e",
                                                "fontSize": "13px"
                                            })
                                        ], style={"marginBottom": "4px"}),
                                        dbc.Input(
                                            id="temp-z-input", 
                                            type="number", 
                                            step=0.1, 
                                            value=round(z_mid,1), 
                                            min=round(z_min,2), 
                                            max=round(z_max,2),
                                            placeholder="Z 좌표",
                                            style={"width": "100%"}
                                        )
                                    ], style={"padding": "8px"})
                                ], style={
                                    "border": "1px solid #bbf7d0",
                                    "backgroundColor": "#f0fdf4"
                                })
                            ], md=4),
                        ], className="g-3"),
                    ], style={
                        "padding": "12px 16px",
                        "backgroundColor": "#f9fafb",
                        "borderRadius": "8px",
                        "border": "1px solid #e5e7eb",
                        "height": "100%"
                    })
                ], md=8),
                
                # 오른쪽: 저장 버튼들
                dbc.Col([
                    html.Div([
                        dbc.Button(
                            [html.I(className="fas fa-camera me-1"), "이미지 저장"],
                            id="btn-save-temp-image",
                            color="primary",
                            size="lg",
                            style={
                                "borderRadius": "8px",
                                "fontWeight": "600",
                                "boxShadow": "0 1px 2px rgba(0,0,0,0.1)",
                                "fontSize": "15px",
                                "width": "120px",
                                "height": "48px",
                                "marginRight": "16px"
                            }
                        ),
                        dbc.Button(
                            [html.I(className="fas fa-file-csv me-1"), "데이터 저장"],
                            id="btn-save-temp-data",
                            color="success",
                            size="lg",
                            style={
                                "borderRadius": "8px",
                                "fontWeight": "600",
                                "boxShadow": "0 1px 2px rgba(0,0,0,0.1)",
                                "fontSize": "15px",
                                "width": "120px",
                                "height": "48px"
                            }
                        ),
                    ], style={"display": "flex", "justifyContent": "center", "alignItems": "center", "marginBottom": "16px"}),
                    
                    # 온도 범위 필터
                    html.Div([
                        html.H6("📊 온도 범위 필터", style={
                            "fontWeight": "600",
                            "color": "#374151",
                            "marginBottom": "8px",
                            "fontSize": "13px"
                        }),
                        dcc.Dropdown(
                            id="temp-range-filter",
                            options=[
                                {"label": "전체", "value": "all"},
                                {"label": "28일", "value": "28"},
                                {"label": "21일", "value": "21"},
                                {"label": "14일", "value": "14"},
                                {"label": "7일", "value": "7"}
                            ],
                            value="all",
                            clearable=False,
                            style={
                                "fontSize": "12px",
                                "borderRadius": "6px"
                            }
                        )
                    ], style={
                        "padding": "8px 12px",
                        "backgroundColor": "#f8fafc",
                        "borderRadius": "6px",
                        "border": "1px solid #e2e8f0"
                    })
                ], md=4),
            ], className="mb-4 align-items-stretch", style={"minHeight": "120px"}),
            
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
    Output("temp-project-alert", "children", allow_duplicate=True),
    Output("temp-project-alert", "color", allow_duplicate=True),
    Output("temp-project-alert", "is_open", allow_duplicate=True),
    Output("tbl-concrete", "data", allow_duplicate=True),
    Output("btn-concrete-analyze", "disabled", allow_duplicate=True),
    Input("btn-concrete-analyze", "n_clicks"),
    State("tbl-concrete", "selected_rows"),
    State("tbl-concrete", "data"),
    prevent_initial_call=True,
)
def start_analysis(n_clicks, selected_rows, tbl_data):
    if not selected_rows or not tbl_data:
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
    Output("temp-project-alert", "children", allow_duplicate=True),
    Output("temp-project-alert", "color", allow_duplicate=True),
    Output("temp-project-alert", "is_open", allow_duplicate=True),
    Output("tbl-concrete", "data", allow_duplicate=True),
    Input("confirm-del-concrete", "submit_n_clicks"),
    State("tbl-concrete", "selected_rows"),
    State("tbl-concrete", "data"),
    prevent_initial_call=True,
)
def delete_concrete_confirm(_click, sel, tbl_data):
    if not sel or not tbl_data:
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
    Input("time-slider-section", "value"),  # 단면도용 독립 슬라이더 사용
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
    """단면도 탭 전용 뷰 업데이트 (독립적)"""
    import math
    import plotly.graph_objects as go
    import numpy as np
    from scipy.interpolate import griddata
    from datetime import datetime
    
    print(f"단면도 뷰 업데이트: time_idx={time_idx}, selected_rows={selected_rows}")  # 디버깅
    
    if not selected_rows or not tbl_data:
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
        print(f"시간 인덱스가 None이거나 잘못됨, 최신 파일 사용: file_idx={file_idx}")
    else:
        file_idx = min(int(time_idx), len(inp_files)-1)
        print(f"시간 인덱스 {time_idx} → 파일 인덱스 {file_idx}")
    current_file = inp_files[file_idx]
    print(f"선택된 파일: {current_file}, 전체 파일 수: {len(inp_files)}")
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
    coords = np.array([[cx, cy, cz] for cx, cy, cz in zip(x_coords, y_coords, z_coords)])
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
        material_info = parse_material_info_from_inp(lines)
        
        current_min = float(np.nanmin(temps))
        current_max = float(np.nanmax(temps))
        current_avg = float(np.nanmean(temps))
        current_file_title = f"{formatted_time} (최저: {current_min:.1f}°C, 최고: {current_max:.1f}°C, 평균: {current_avg:.1f}°C)\n{material_info}"
    except Exception:
        current_file_title = f"{os.path.basename(current_file)}"
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
    from datetime import datetime as dt_import
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
            dt = dt_import.strptime(time_str, "%Y%m%d%H")
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
    # 온도 범위 필터링은 별도 콜백으로 처리 (현재는 전체 데이터 표시)
    
    # 그래프 생성
    fig_temp = go.Figure()
    if temp_times and temp_values:
        # x축 값: 시간별 실제 datetime 객체
        x_values = temp_times
        # x축 라벨: 날짜가 바뀌는 첫 번째만 날짜, 나머지는 빈 문자열
        x_labels = []
        prev_date = None
        for dt in temp_times:
            current_date = dt.strftime('%-m/%-d')
            if current_date != prev_date:
                x_labels.append(current_date)
                prev_date = current_date
            else:
                x_labels.append("")
        fig_temp.add_trace(go.Scatter(x=x_values, y=temp_values, mode='lines+markers', name='온도'))
        fig_temp.update_layout(
            title="시간에 따른 온도 정보",
            xaxis_title="날짜",
            yaxis_title="온도(°C)",
            xaxis=dict(
                tickmode='array',
                tickvals=x_values,
                ticktext=x_labels
            )
        )
    return fig_3d, fig_temp

# 온도 범위 필터 콜백 (온도변화 탭에서만 작동)
@callback(
    Output("temp-time-graph", "figure", allow_duplicate=True),
    Input("temp-range-filter", "value"),
    State("temp-viewer-3d", "figure"),
    State("tbl-concrete", "selected_rows"),
    State("tbl-concrete", "data"),
    prevent_initial_call=True,
)
def update_temp_range_filter(range_filter, fig_3d, selected_rows, tbl_data):
    """온도 범위 필터 변경 시 온도 변화 그래프만 업데이트"""
    if not selected_rows or not tbl_data or not range_filter:
        raise PreventUpdate
    
    import plotly.graph_objects as go
    import numpy as np
    import glob, os
    from datetime import datetime as dt_import
    
    row = pd.DataFrame(tbl_data).iloc[selected_rows[0]]
    concrete_pk = row["concrete_pk"]
    inp_dir = f"inp/{concrete_pk}"
    inp_files = sorted(glob.glob(f"{inp_dir}/*.inp"))
    
    # 온도 데이터 수집 (기존 로직과 동일)
    temp_times = []
    temp_values = []
    
    for f in inp_files:
        try:
            time_str = os.path.basename(f).split(".")[0]
            dt = dt_import.strptime(time_str, "%Y%m%d%H")
        except:
            continue
        
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
        
        # 기본 위치에서 온도 찾기 (임시로 중앙점 사용)
        if nodes:
            coords = np.array([[v['x'], v['y'], v['z']] for v in nodes.values()])
            node_ids = list(nodes.keys())
            # 중앙점 계산
            center_x = np.mean(coords[:, 0])
            center_y = np.mean(coords[:, 1])
            center_z = np.mean(coords[:, 2])
            
            dists = np.linalg.norm(coords - np.array([center_x, center_y, center_z]), axis=1)
            min_idx = np.argmin(dists)
            closest_id = node_ids[min_idx]
            temp_val = temperatures.get(closest_id, None)
            if temp_val is not None:
                temp_times.append(dt)
                temp_values.append(temp_val)
    
    # 온도 범위 필터링 적용
    if range_filter and range_filter != "all" and temp_times:
        try:
            from datetime import timedelta
            latest_time = max(temp_times)
            days_back = int(range_filter)
            cutoff_time = latest_time - timedelta(days=days_back)
            
            filtered_times = []
            filtered_values = []
            for i, dt in enumerate(temp_times):
                if dt >= cutoff_time:
                    filtered_times.append(dt)
                    filtered_values.append(temp_values[i])
            
            temp_times = filtered_times
            temp_values = filtered_values
        except Exception as e:
            print(f"온도 범위 필터링 오류: {e}")
    
    # 그래프 생성
    fig_temp = go.Figure()
    if temp_times and temp_values:
        # x축 값: 시간별 실제 datetime 객체
        x_values = temp_times
        # x축 라벨: 날짜가 바뀌는 첫 번째만 날짜, 나머지는 빈 문자열
        x_labels = []
        prev_date = None
        for dt in temp_times:
            current_date = dt.strftime('%-m/%-d')
            if current_date != prev_date:
                x_labels.append(current_date)
                prev_date = current_date
            else:
                x_labels.append("")
        fig_temp.add_trace(go.Scatter(x=x_values, y=temp_values, mode='lines+markers', name='온도'))
        fig_temp.update_layout(
            title="시간에 따른 온도 정보",
            xaxis_title="날짜",
            yaxis_title="온도(°C)",
            xaxis=dict(
                tickmode='array',
                tickvals=x_values,
                ticktext=x_labels
            )
        )
    
    return fig_temp

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

# 3D 뷰 슬라이더 동기화 콜백 (display용 슬라이더와 실제 슬라이더만, 단면도 슬라이더는 제외)
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

# 클라이언트 사이드 콜백 제거 - 충돌 방지

# 단면도 탭 시간 정보 업데이트 콜백
@callback(
    Output("section-time-info", "children"),
    Input("current-file-title-store", "data"),
    Input("tabs-main", "active_tab"),
    prevent_initial_call=True,
)
def update_section_time_info(current_file_title, active_tab):
    """단면도 탭에서 시간 정보를 업데이트"""
    
    # 단면도 탭이 아니면 빈 div 반환
    if active_tab != "tab-section":
        return html.Div()
    
    if not current_file_title:
        current_file_title = "시간 정보 없음"
    
    # 시간과 물성치 정보 분리
    lines = current_file_title.split('\n')
    time_info = lines[0] if lines else "시간 정보 없음"
    material_info = lines[1] if len(lines) > 1 else ""
    
    # HTML 컴포넌트로 반환
    return html.Div([
        # 통합 정보 카드 (노션 스타일)
        html.Div([
            # 시간 정보 섹션
            html.Div([
                html.I(className="fas fa-clock", style={"color": "#3b82f6", "fontSize": "14px"}),
                html.Span(time_info, style={
                    "fontWeight": "600",
                    "color": "#1f2937",
                    "fontSize": "14px",
                    "marginLeft": "8px"
                })
            ], style={
                "display": "flex",
                "alignItems": "center",
                "marginBottom": "1px" if material_info else "0",
                "marginTop": "12px"
            }),
            
            # 물성치 정보 섹션 (있는 경우만, 인라인 형태)
            html.Div([
                html.I(className="fas fa-cube", style={"color": "#6366f1", "fontSize": "14px"}),
                *[html.Div([
                    html.Span(f"{prop.split(':')[0]}:", style={
                        "color": "#6b7280",
                        "fontSize": "12px",
                        "marginRight": "4px"
                    }),
                    html.Span(prop.split(":", 1)[1].strip(), style={
                        "color": "#111827",
                        "fontSize": "12px",
                        "fontWeight": "500",
                        "marginRight": "12px"
                    })
                ], style={"display": "inline"})
                for prop in material_info.split(", ")]
            ], style={
                "display": "flex",
                "alignItems": "flex-start",
                "gap": "8px",
                "flexWrap": "wrap",
                "marginBottom": "12px"
            }) if material_info else html.Div()
            
        ], style={
            "padding": "8px 12px",
            "backgroundColor": "#f8fafc",
            "borderRadius": "8px",
            "border": "1px solid #e2e8f0",
            "boxShadow": "0 1px 3px rgba(0,0,0,0.05)",
            "marginBottom": "16px",
            "height": "65px",
            "display": "flex",
            "flexDirection": "column",
            "justifyContent": "center",
            "alignItems": "center"
        })
    ])

# 단면도 탭 전용 시간 슬라이더 초기화 콜백 (독립적)
@callback(
    Output("time-slider-section", "min"),
    Output("time-slider-section", "max"), 
    Output("time-slider-section", "value"),
    Output("time-slider-section", "marks"),
    Input("tabs-main", "active_tab"),
    Input("tbl-concrete", "selected_rows"),
    State("tbl-concrete", "data"),
    prevent_initial_call=True,
)
def init_section_slider_independent(active_tab, selected_rows, tbl_data):
    """단면도 탭의 슬라이더를 독립적으로 초기화"""
    from datetime import datetime as dt_import  # 명시적 import로 충돌 방지
    
    # 단면도 탭이 아니면 기본값 유지
    if active_tab != "tab-section":
        return dash.no_update, dash.no_update, dash.no_update, dash.no_update
        
    if not selected_rows or not tbl_data:
        return 0, 5, 0, {}
    
    row = pd.DataFrame(tbl_data).iloc[selected_rows[0]]
    concrete_pk = row["concrete_pk"]
    inp_dir = f"inp/{concrete_pk}"
    inp_files = sorted(glob.glob(f"{inp_dir}/*.inp"))
    
    if not inp_files:
        return 0, 5, 0, {}
    
    # 시간 파싱
    times = []
    for f in inp_files:
        try:
            time_str = os.path.basename(f).split(".")[0]
            dt = dt_import.strptime(time_str, "%Y%m%d%H")
            times.append(dt)
        except:
            continue
    
    if not times:
        return 0, 5, 0, {}
    
    max_idx = len(times) - 1
    
    # 슬라이더 마크 생성
    marks = {}
    seen_dates = set()
    for i, dt in enumerate(times):
        date_str = dt.strftime("%m/%d")
        if date_str not in seen_dates:
            marks[i] = date_str
            seen_dates.add(date_str)
    
    return 0, max_idx, max_idx, marks

# ───────────────────── 3D 이미지 저장 콜백 ─────────────────────
@callback(
    Output("download-3d-image", "data"),
    Output("btn-save-3d-image", "children"),
    Output("btn-save-3d-image", "disabled"),
    Input("btn-save-3d-image", "n_clicks"),
    State("viewer-3d-display", "figure"),
    State("tbl-concrete", "selected_rows"),
    State("tbl-concrete", "data"),
    State("time-slider-display", "value"),
    prevent_initial_call=True,
)
def save_3d_image(n_clicks, figure, selected_rows, tbl_data, time_value):
    """3D 뷰어의 현재 이미지를 PNG 파일로 저장"""
    if not n_clicks or not fig_3d:
        raise PreventUpdate
    
    try:
        # 로딩 상태로 변경
        # loading_btn = [html.I(className="fas fa-spinner fa-spin me-1"), "저장중..."]
        # 파일명 생성
        if selected_rows and tbl_data:
            row = pd.DataFrame(tbl_data).iloc[selected_rows[0]]
            concrete_pk = row["concrete_pk"]
            concrete_name = row.get("name", concrete_pk)
            # 현재 시간 정보 추가
            inp_dir = f"inp/{concrete_pk}"
            inp_files = sorted(glob.glob(f"{inp_dir}/*.inp"))
            if inp_files and time_value is not None:
                file_idx = min(int(time_value), len(inp_files)-1)
                current_file = inp_files[file_idx]
                time_str = os.path.basename(current_file).split(".")[0]
                filename = f"3D_히트맵_{concrete_name}_{time_str}.png"
            else:
                filename = f"3D_히트맵_{concrete_name}.png"
        else:
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"3D_히트맵_{timestamp}.png"
        # 이미지 저장 방법 1: plotly.io 시도
        try:
            import plotly.io as pio
            # kaleido 엔진 확인
            img_bytes = pio.to_image(figure, format="png", width=1200, height=800, scale=2, engine="kaleido")
            # 저장 후 버튼 텍스트를 항상 '이미지 저장'으로 복원
            default_btn = [html.I(className="fas fa-camera me-1"), "이미지 저장"]
            return dcc.send_bytes(img_bytes, filename=filename), default_btn, False
        except ImportError:
            print("kaleido가 설치되지 않음. 대안 방법 시도 중...")
        except Exception as pio_error:
            print(f"plotly.io 저장 실패: {pio_error}")
        # 이미지 저장 방법 2: HTML을 통한 이미지 생성 (대안)
        try:
            import json
            import base64
            fig_json = json.dumps(figure, cls=plotly.utils.PlotlyJSONEncoder)
            html_template = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <script src=\"https://cdn.plot.ly/plotly-latest.min.js\"></script>
            </head>
            <body>
                <div id=\"plotly-div\" style=\"width:1200px;height:800px;\"></div>
                <script>
                    var figureData = {fig_json};
                    Plotly.newPlot('plotly-div', figureData.data, figureData.layout, {{displayModeBar: false}});
                </script>
            </body>
            </html>
            """
            html_filename = filename.replace('.png', '.html')
            default_btn = [html.I(className="fas fa-camera me-1"), "이미지 저장"]
            return dict(content=html_template, filename=html_filename), default_btn, False
        except Exception as html_error:
            print(f"HTML 저장도 실패: {html_error}")
            error_btn = [html.I(className="fas fa-times me-1"), "실패"]
            return dash.no_update, error_btn, False
    except Exception as e:
        print(f"3D 이미지 저장 전체 오류: {e}")
        error_btn = [html.I(className="fas fa-times me-1"), "오류"]
        return dash.no_update, error_btn, False

# ───────────────────── 이미지 저장 버튼 상태 초기화 ─────────────────────
@callback(
    Output("btn-save-3d-image", "children", allow_duplicate=True),
    Output("btn-save-3d-image", "disabled", allow_duplicate=True),
    Input("tabs-main", "active_tab"),
    Input("tbl-concrete", "selected_rows"),
    prevent_initial_call=True,
)
def reset_image_save_button(active_tab, selected_rows):
    """탭 변경이나 콘크리트 선택 시 이미지 저장 버튼 상태 초기화"""
    default_btn = [html.I(className="fas fa-camera me-1"), "이미지 저장"]
    return default_btn, False

# ───────────────────── 현재 INP 파일 저장 콜백 ─────────────────────
@callback(
    Output("download-current-inp", "data"),
    Input("btn-save-current-inp", "n_clicks"),
    State("tbl-concrete", "selected_rows"),
    State("tbl-concrete", "data"),
    State("time-slider-display", "value"),
    prevent_initial_call=True,
)
def save_current_inp(n_clicks, selected_rows, tbl_data, time_value):
    """현재 선택된 시간의 INP 파일을 저장"""
    if not n_clicks or not selected_rows or not tbl_data:
        raise PreventUpdate
    
    try:
        row = pd.DataFrame(tbl_data).iloc[selected_rows[0]]
        concrete_pk = row["concrete_pk"]
        concrete_name = row.get("name", concrete_pk)
        
        # INP 파일 경로 찾기
        inp_dir = f"inp/{concrete_pk}"
        inp_files = sorted(glob.glob(f"{inp_dir}/*.inp"))
        
        if not inp_files:
            raise PreventUpdate
        
        # 현재 시간에 해당하는 파일 선택
        if time_value is not None:
            file_idx = min(int(time_value), len(inp_files)-1)
        else:
            file_idx = len(inp_files) - 1  # 최신 파일
        
        current_file = inp_files[file_idx]
        
        if not os.path.exists(current_file):
            raise PreventUpdate
        
        # 파일명 생성
        time_str = os.path.basename(current_file).split(".")[0]
        filename = f"{concrete_name}_{time_str}.inp"
        
        # 파일 읽기 및 다운로드
        with open(current_file, 'r', encoding='utf-8') as f:
            file_content = f.read()
        
        return dict(content=file_content, filename=filename)
        
    except Exception as e:
        print(f"INP 파일 저장 오류: {e}")
        raise PreventUpdate

    # 3D 뷰 탭 시간 정보 업데이트 콜백
@callback(
    Output("viewer-3d-time-info", "children"),
    Input("current-file-title-store", "data"),
    Input("tabs-main", "active_tab"),
    prevent_initial_call=True,
)
def update_viewer3d_time_info(current_file_title, active_tab):
    """3D 뷰 탭에서 시간/물성치 정보를 업데이트"""
    if active_tab != "tab-3d":
        return html.Div()
    if not current_file_title:
        current_file_title = "시간 정보 없음"
    
    # 시간과 물성치 정보 분리
    lines = current_file_title.split('\n')
    time_info = lines[0] if lines else "시간 정보 없음"
    material_info = lines[1] if len(lines) > 1 else ""
    
    return html.Div([
        # 통합 정보 카드 (노션 스타일)
        html.Div([
            # 시간 정보 섹션
            html.Div([
                html.I(className="fas fa-clock", style={"color": "#3b82f6", "fontSize": "14px"}),
                html.Span(time_info, style={
                    "fontWeight": "600",
                    "color": "#1f2937",
                    "fontSize": "14px",
                    "marginLeft": "8px"
                })
            ], style={
                "display": "flex",
                "alignItems": "center",
                "marginBottom": "1px" if material_info else "0",
                "marginTop": "12px"
            }),
            
            # 물성치 정보 섹션 (있는 경우만, 인라인 형태)
            html.Div([
                html.I(className="fas fa-cube", style={"color": "#6366f1", "fontSize": "14px"}),
                *[html.Div([
                    html.Span(f"{prop.split(':')[0]}:", style={
                        "color": "#6b7280",
                        "fontSize": "12px",
                        "marginRight": "4px"
                    }),
                    html.Span(prop.split(":", 1)[1].strip(), style={
                        "color": "#111827",
                        "fontSize": "12px",
                        "fontWeight": "500",
                        "marginRight": "12px"
                    })
                ], style={"display": "inline"})
                for prop in material_info.split(", ")]
            ], style={
                "display": "flex",
                "alignItems": "flex-start",
                "gap": "8px",
                "flexWrap": "wrap",
                "marginBottom": "12px"
            }) if material_info else html.Div()
            
        ], style={
            "padding": "8px 12px",
            "backgroundColor": "#f8fafc",
            "borderRadius": "8px",
            "border": "1px solid #e2e8f0",
            "boxShadow": "0 1px 3px rgba(0,0,0,0.05)",
            "height": "65px",
            "display": "flex",
            "flexDirection": "column",
            "justifyContent": "center",
            "alignItems": "center"
        })
    ], style={
        "height": "65px",
        "display": "flex",
        "flexDirection": "column"
    })

# ───────────────────── 단면도 이미지 저장 콜백 ─────────────────────
@callback(
    Output("download-section-image", "data"),
    Output("btn-save-section-image", "children"),
    Output("btn-save-section-image", "disabled"),
    Input("btn-save-section-image", "n_clicks"),
    State("viewer-3d-section", "figure"),
    State("viewer-section-x", "figure"),
    State("viewer-section-y", "figure"),
    State("viewer-section-z", "figure"),
    State("tbl-concrete", "selected_rows"),
    State("tbl-concrete", "data"),
    State("time-slider-section", "value"),
    prevent_initial_call=True,
)
def save_section_image(n_clicks, fig_3d, fig_x, fig_y, fig_z, selected_rows, tbl_data, time_value):
    """단면도 탭의 모든 뷰를 합쳐서 하나의 이미지로 저장"""
    if not n_clicks:
        raise PreventUpdate
    
    try:
        # 파일명 생성
        if selected_rows and tbl_data:
            row = pd.DataFrame(tbl_data).iloc[selected_rows[0]]
            concrete_pk = row["concrete_pk"]
            concrete_name = row.get("name", concrete_pk)
            
            # 현재 시간 정보 추가
            inp_dir = f"inp/{concrete_pk}"
            inp_files = sorted(glob.glob(f"{inp_dir}/*.inp"))
            if inp_files and time_value is not None:
                file_idx = min(int(time_value), len(inp_files)-1)
                current_file = inp_files[file_idx]
                time_str = os.path.basename(current_file).split(".")[0]
                filename = f"단면도_{concrete_name}_{time_str}.png"
            else:
                filename = f"단면도_{concrete_name}.png"
        else:
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"단면도_{timestamp}.png"
        
        # 4개의 그래프를 하나로 합치기
        try:
            import plotly.graph_objects as go
            from plotly.subplots import make_subplots
            
            # 서브플롯 생성 (2x2 그리드)
            fig_combined = make_subplots(
                rows=2, cols=2,
                subplot_titles=('3D 뷰', 'X 단면도', 'Y 단면도', 'Z 단면도'),
                specs=[[{"type": "scene"}, {"type": "xy"}],
                       [{"type": "xy"}, {"type": "xy"}]]
            )
            
            # 3D 뷰 추가
            if fig_3d and fig_3d.get('data'):
                for trace in fig_3d['data']:
                    fig_combined.add_trace(trace, row=1, col=1)
            
            # X 단면도 추가
            if fig_x and fig_x.get('data'):
                for trace in fig_x['data']:
                    fig_combined.add_trace(trace, row=1, col=2)
            
            # Y 단면도 추가
            if fig_y and fig_y.get('data'):
                for trace in fig_y['data']:
                    fig_combined.add_trace(trace, row=2, col=1)
            
            # Z 단면도 추가
            if fig_z and fig_z.get('data'):
                for trace in fig_z['data']:
                    fig_combined.add_trace(trace, row=2, col=2)
            
            # 레이아웃 업데이트
            fig_combined.update_layout(
                height=800,
                width=1200,
                showlegend=False,
                title_text="단면도 분석 결과",
                title_x=0.5
            )
            
            # 각 서브플롯의 축 레이블 설정
            fig_combined.update_xaxes(title_text="X (m)", row=1, col=2)
            fig_combined.update_yaxes(title_text="Z (m)", row=1, col=2)
            fig_combined.update_xaxes(title_text="X (m)", row=2, col=1)
            fig_combined.update_yaxes(title_text="Z (m)", row=2, col=1)
            fig_combined.update_xaxes(title_text="X (m)", row=2, col=2)
            fig_combined.update_yaxes(title_text="Y (m)", row=2, col=2)
            
            # 이미지 저장
            import plotly.io as pio
            img_bytes = pio.to_image(fig_combined, format="png", width=1200, height=800, scale=2, engine="kaleido")
            default_btn = [html.I(className="fas fa-camera me-1"), "이미지 저장"]
            return dcc.send_bytes(img_bytes, filename=filename), default_btn, False
            
        except ImportError:
            print("kaleido가 설치되지 않음. 대안 방법 시도 중...")
            
        except Exception as pio_error:
            print(f"plotly.io 저장 실패: {pio_error}")
        
        # 대안: HTML 파일로 저장
        try:
            import json
            fig_json = json.dumps(fig_combined, cls=plotly.utils.PlotlyJSONEncoder)
            
            html_template = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
            </head>
            <body>
                <div id="plotly-div" style="width:1200px;height:800px;"></div>
                <script>
                    var figureData = {fig_json};
                    Plotly.newPlot('plotly-div', figureData.data, figureData.layout, {{displayModeBar: false}});
                </script>
            </body>
            </html>
            """
            
            html_filename = filename.replace('.png', '.html')
            default_btn = [html.I(className="fas fa-camera me-1"), "이미지 저장"]
            return dict(content=html_template, filename=html_filename), default_btn, False
            
        except Exception as html_error:
            print(f"HTML 저장도 실패: {html_error}")
            error_btn = [html.I(className="fas fa-times me-1"), "실패"]
            return dash.no_update, error_btn, False
        
    except Exception as e:
        print(f"단면도 이미지 저장 전체 오류: {e}")
        error_btn = [html.I(className="fas fa-times me-1"), "오류"]
        return dash.no_update, error_btn, False

# ───────────────────── 단면도 INP 파일 저장 콜백 ─────────────────────
@callback(
    Output("download-section-inp", "data"),
    Input("btn-save-section-inp", "n_clicks"),
    State("tbl-concrete", "selected_rows"),
    State("tbl-concrete", "data"),
    State("time-slider-section", "value"),
    prevent_initial_call=True,
)
def save_section_inp(n_clicks, selected_rows, tbl_data, time_value):
    """단면도 탭에서 현재 선택된 시간의 INP 파일을 저장"""
    if not n_clicks or not selected_rows or not tbl_data:
        raise PreventUpdate
    
    try:
        row = pd.DataFrame(tbl_data).iloc[selected_rows[0]]
        concrete_pk = row["concrete_pk"]
        concrete_name = row.get("name", concrete_pk)
        
        # INP 파일 경로 찾기
        inp_dir = f"inp/{concrete_pk}"
        inp_files = sorted(glob.glob(f"{inp_dir}/*.inp"))
        
        if not inp_files:
            raise PreventUpdate
        
        # 현재 시간에 해당하는 파일 선택
        if time_value is not None:
            file_idx = min(int(time_value), len(inp_files)-1)
        else:
            file_idx = len(inp_files) - 1  # 최신 파일
        
        current_file = inp_files[file_idx]
        
        if not os.path.exists(current_file):
            raise PreventUpdate
        
        # 파일명 생성
        time_str = os.path.basename(current_file).split(".")[0]
        filename = f"{concrete_name}_{time_str}.inp"
        
        # 파일 읽기 및 다운로드
        with open(current_file, 'r', encoding='utf-8') as f:
            file_content = f.read()
        
        return dict(content=file_content, filename=filename)
        
    except Exception as e:
        print(f"단면도 INP 파일 저장 오류: {e}")
        raise PreventUpdate

# ───────────────────── 온도 변화 이미지 저장 콜백 ─────────────────────
@callback(
    Output("download-temp-image", "data"),
    Output("btn-save-temp-image", "children"),
    Output("btn-save-temp-image", "disabled"),
    Input("btn-save-temp-image", "n_clicks"),
    State("temp-viewer-3d", "figure"),
    State("temp-time-graph", "figure"),
    State("tbl-concrete", "selected_rows"),
    State("tbl-concrete", "data"),
    State("temp-x-input", "value"),
    State("temp-y-input", "value"),
    State("temp-z-input", "value"),
    prevent_initial_call=True,
)
def save_temp_image(n_clicks, fig_3d, fig_time, selected_rows, tbl_data, x, y, z):
    """온도 변화 탭의 콘크리트 구조 뷰를 이미지로 저장"""
    if not n_clicks or not fig_3d:
        raise PreventUpdate
    
    try:
        # 파일명 생성 (위치 정보 포함)
        if selected_rows and tbl_data:
            row = pd.DataFrame(tbl_data).iloc[selected_rows[0]]
            concrete_pk = row["concrete_pk"]
            concrete_name = row.get("name", concrete_pk)
            
            # 위치 정보를 파일명에 포함
            x_pos = round(x, 1) if x is not None else 0.0
            y_pos = round(y, 1) if y is not None else 0.0
            z_pos = round(z, 1) if z is not None else 0.0
            
            filename = f"온도분석_{concrete_name}_위치({x_pos}_{y_pos}_{z_pos}).png"
        else:
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"온도분석_{timestamp}.png"
        
        # 2개의 그래프를 하나로 합치기
        try:
            import plotly.graph_objects as go
            from plotly.subplots import make_subplots
            
            # 서브플롯 생성 (1x2 그리드)
            fig_combined = make_subplots(
                rows=1, cols=2,
                subplot_titles=('콘크리트 구조', '온도 변화 추이'),
                specs=[[{"type": "scene"}, {"type": "xy"}]]
            )
            
            # 3D 뷰 추가
            if fig_3d and fig_3d.get('data'):
                for trace in fig_3d['data']:
                    fig_combined.add_trace(trace, row=1, col=1)
            
            # 온도 변화 그래프 추가
            if fig_time and fig_time.get('data'):
                for trace in fig_time['data']:
                    fig_combined.add_trace(trace, row=1, col=2)
            
            # 레이아웃 업데이트
            fig_combined.update_layout(
                height=600,
                width=1400,
                showlegend=False,
                title_text="온도 변화 분석 결과",
                title_x=0.5
            )
            
            # 온도 변화 그래프의 축 레이블 설정
            fig_combined.update_xaxes(title_text="시간", row=1, col=2)
            fig_combined.update_yaxes(title_text="온도(°C)", row=1, col=2)
            
            # 이미지 저장
            import plotly.io as pio
            img_bytes = pio.to_image(fig_combined, format="png", width=1400, height=600, scale=2, engine="kaleido")
            default_btn = [html.I(className="fas fa-camera me-1"), "이미지 저장"]
            return dcc.send_bytes(img_bytes, filename=filename), default_btn, False
            
        except ImportError:
            print("kaleido가 설치되지 않음. 대안 방법 시도 중...")
            
        except Exception as pio_error:
            print(f"plotly.io 저장 실패: {pio_error}")
        
        # 대안: HTML 파일로 저장
        try:
            import json
            fig_json = json.dumps(fig_combined, cls=plotly.utils.PlotlyJSONEncoder)
            
            html_template = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
            </head>
            <body>
                <div id="plotly-div" style="width:1200px;height:800px;"></div>
                <script>
                    var figureData = {fig_json};
                    Plotly.newPlot('plotly-div', figureData.data, figureData.layout, {{displayModeBar: false}});
                </script>
            </body>
            </html>
            """
            
            html_filename = filename.replace('.png', '.html')
            default_btn = [html.I(className="fas fa-camera me-1"), "이미지 저장"]
            return dict(content=html_template, filename=html_filename), default_btn, False
            
        except Exception as html_error:
            print(f"HTML 저장도 실패: {html_error}")
            error_btn = [html.I(className="fas fa-times me-1"), "실패"]
            return dash.no_update, error_btn, False
        
    except Exception as e:
        print(f"온도 변화 이미지 저장 전체 오류: {e}")
        error_btn = [html.I(className="fas fa-times me-1"), "오류"]
        return dash.no_update, error_btn, False

# ───────────────────── 온도 변화 데이터 저장 콜백 ─────────────────────
@callback(
    Output("download-temp-data", "data"),
    Input("btn-save-temp-data", "n_clicks"),
    State("tbl-concrete", "selected_rows"),
    State("tbl-concrete", "data"),
    State("temp-x-input", "value"),
    State("temp-y-input", "value"),
    State("temp-z-input", "value"),
    prevent_initial_call=True,
)
def save_temp_data(n_clicks, selected_rows, tbl_data, x, y, z):
    """온도 변화 데이터를 CSV 형태로 저장"""
    import pandas as pd
    if not n_clicks or not selected_rows or not tbl_data:
        raise PreventUpdate
    
    try:
        row = pd.DataFrame(tbl_data).iloc[selected_rows[0]]
        concrete_pk = row["concrete_pk"]
        concrete_name = row.get("name", concrete_pk)
        
        # 위치 정보
        x_pos = round(x, 1) if x is not None else 0.0
        y_pos = round(y, 1) if y is not None else 0.0
        z_pos = round(z, 1) if z is not None else 0.0
        
        # INP 파일들에서 온도 데이터 수집
        inp_dir = f"inp/{concrete_pk}"
        inp_files = sorted(glob.glob(f"{inp_dir}/*.inp"))
        
        if not inp_files:
            raise PreventUpdate
        
        # 온도 데이터 수집
        temp_data = []
        from datetime import datetime as dt_import
        
        for f in inp_files:
            # 시간 파싱
            try:
                time_str = os.path.basename(f).split(".")[0]
                dt = dt_import.strptime(time_str, "%Y%m%d%H")
                formatted_time = dt.strftime("%Y-%m-%d %H:%M:%S")
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
            if nodes:
                coords = np.array([[v['x'], v['y'], v['z']] for v in nodes.values()])
                node_ids = list(nodes.keys())
                dists = np.linalg.norm(coords - np.array([x_pos, y_pos, z_pos]), axis=1)
                min_idx = np.argmin(dists)
                closest_id = node_ids[min_idx]
                temp_val = temperatures.get(closest_id, None)
                
                if temp_val is not None:
                    temp_data.append({
                        '시간': formatted_time,
                        '온도(°C)': round(temp_val, 2),
                        '측정위치_X(m)': x_pos,
                        '측정위치_Y(m)': y_pos,
                        '측정위치_Z(m)': z_pos,
                        '콘크리트명': concrete_name
                    })
        
        if not temp_data:
            raise PreventUpdate
        
        # CSV 데이터 생성
        import io
        import pandas as pd
        
        df = pd.DataFrame(temp_data)
        csv_buffer = io.StringIO()
        df.to_csv(csv_buffer, index=False, encoding='utf-8-sig')
        csv_buffer.seek(0)
        
        # 파일명 생성 (위치 정보 포함)
        filename = f"온도데이터_{concrete_name}_위치({x_pos}_{y_pos}_{z_pos}).csv"
        
        return dict(content=csv_buffer.getvalue(), filename=filename)
        
    except Exception as e:
        print(f"온도 변화 데이터 저장 오류: {e}")
        raise PreventUpdate

# ───────────── TCI 인장강도 계산식 입력창 동적 표시 콜백 ─────────────
@callback(
    Output("temp-ab-inputs-container", "children", allow_duplicate=True),
    Output("temp-fct-formula-preview", "children", allow_duplicate=True),
    Input("fct-formula-type", "value"),
    Input("fct28-input", "value"),
    prevent_initial_call=True
)
def update_formula_display(formula_type, fct28):
    from dash import dash_table
    import numpy as np
    import plotly.graph_objects as go
    
    # 기본값 설정
    if formula_type is None:
        formula_type = "ceb"
    
    # a, b 입력 필드 동적 생성
    if formula_type == "ceb":
        ab_inputs = dbc.Row([
            dbc.Col([
                dbc.Label("a (보통 1.0) [0.5~2]", style={
                    "fontWeight": "500",
                    "color": "#374151",
                    "marginBottom": "8px"
                }),
                dbc.Input(
                    id="a-input", 
                    type="number", 
                    value=1, 
                    placeholder="1.0", 
                    min=0.5, 
                    max=2,
                    style={
                        "borderRadius": "8px",
                        "border": "1px solid #d1d5db",
                        "padding": "10px 12px"
                    }
                ),
            ], md=4),
            dbc.Col([
                dbc.Label("b (보통 1.0) [0.5~2]", style={
                    "fontWeight": "500",
                    "color": "#374151",
                    "marginBottom": "8px"
                }),
                dbc.Input(
                    id="b-input", 
                    type="number", 
                    value=1, 
                    placeholder="1.0", 
                    min=0.5, 
                    max=2,
                    style={
                        "borderRadius": "8px",
                        "border": "1px solid #d1d5db",
                        "padding": "10px 12px"
                    }
                ),
            ], md=4),
        ], className="g-3")
        formula_text = "식: fct(t) = fct,28 * ( t / (a + b*t) )^0.5"
    else:
        ab_inputs = html.Div()  # 빈 div로 a, b 입력 필드 숨김
        formula_text = "식: fct(t) = fct,28 * (t/28)^0.5 (t ≤ 28)"
    
    try:
        # 미리보기 테이블 생성
        # 기본값으로 미리보기 표시
        if fct28 is None or fct28 == "":
            fct28 = 20.0  # 기본값
        else:
            try:
                fct28 = float(fct28)
            except (ValueError, TypeError):
                fct28 = 20.0  # 기본값
        
        # a, b 값은 기본값 사용 (동적 입력 필드 참조 문제 해결)
        a = 1.0
        b = 1.0
        
        # fct(t) 계산 (1~28, 0.1 간격)
        t_vals = np.arange(1, 28.01, 0.1)
        fct_vals = []
        for t in t_vals:
            try:
                if formula_type == "ceb":
                    fct = fct28 * (t / (a + b * t)) ** 0.5
                else:
                    # 경험식 (KCI/KS)
                    if t <= 28:
                        fct = fct28 * (t / 28) ** 0.5
                    else:
                        fct = fct28
            except Exception:
                fct = 0
            fct_vals.append(fct)
        
        df = pd.DataFrame({"t[일]": np.round(t_vals, 2), "fct(t) 인장강도 [GPa]": np.round(fct_vals, 4)})
        preview_table = dash_table.DataTable(
            columns=[{"name": i, "id": i} for i in df.columns],
            data=df.to_dict("records"),
            page_size=10,
            style_table={"overflowY": "auto", "height": "240px", "marginTop": "8px"},
            style_cell={"textAlign": "center"},
            style_header={"backgroundColor": "#f8fafc", "fontWeight": "600"},
        )
        
        # 그래프 생성
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=t_vals,
            y=fct_vals,
            mode='lines+markers',
            name='fct(t)',
            line=dict(color='#3b82f6', width=2),
            marker=dict(size=4, color='#3b82f6')
        ))
        
        fig.update_layout(
            title="인장강도 발달 곡선",
            xaxis_title="일령 (일)",
            yaxis_title="인장강도 (MPa)",
            height=300,
            margin=dict(l=50, r=50, t=50, b=50),
            showlegend=False,
            plot_bgcolor='white',
            paper_bgcolor='white'
        )
        
        fig.update_xaxes(gridcolor='#e5e7eb', showgrid=True)
        fig.update_yaxes(gridcolor='#e5e7eb', showgrid=True)
        
        preview_content = html.Div([
            html.Small(formula_text, style={"color": "#64748b"}),
            html.Div("↓ 1~28일 인장강도 미리보기 (0.1 간격)", style={"marginTop": "8px", "fontSize": "13px", "color": "#64748b"}),
            dbc.Row([
                dbc.Col(preview_table, md=6),
                dbc.Col(dcc.Graph(figure=fig, config={'displayModeBar': False}), md=6)
            ], className="g-2")
        ])
    except Exception:
        preview_content = html.Small(formula_text, style={"color": "#64748b"})
    
    return ab_inputs, preview_content

# ───────────── a, b 입력값 실시간 반영 콜백 ─────────────
@callback(
    Output("temp-fct-formula-preview", "children", allow_duplicate=True),
    Input("a-input", "value"),
    Input("b-input", "value"),
    State("fct-formula-type", "value"),
    State("fct28-input", "value"),
    prevent_initial_call=True
)
def update_preview_with_ab(a, b, formula_type, fct28):
    from dash import dash_table
    import numpy as np
    import plotly.graph_objects as go
    
    # 기본값 설정
    if formula_type is None:
        formula_type = "ceb"
    
    if formula_type == "ceb":
        formula_text = "식: fct(t) = fct,28 * ( t / (a + b*t) )^0.5"
    else:
        formula_text = "식: fct(t) = fct,28 * (t/28)^0.5 (t ≤ 28)"
    
    try:
        # 기본값으로 미리보기 표시
        if fct28 is None or fct28 == "":
            fct28 = 20.0  # 기본값
        else:
            try:
                fct28 = float(fct28)
            except (ValueError, TypeError):
                fct28 = 20.0  # 기본값
        
        # a, b 값 처리
        if a is None or a == "":
            a = 1.0
        else:
            try:
                a = float(a)
            except (ValueError, TypeError):
                a = 1.0
            
        if b is None or b == "":
            b = 1.0
        else:
            try:
                b = float(b)
            except (ValueError, TypeError):
                b = 1.0
        
        # fct(t) 계산 (1~28, 0.1 간격)
        t_vals = np.arange(1, 28.01, 0.1)
        fct_vals = []
        for t in t_vals:
            try:
                if formula_type == "ceb":
                    fct = fct28 * (t / (a + b * t)) ** 0.5
                else:
                    # 경험식 (KCI/KS)
                    if t <= 28:
                        fct = fct28 * (t / 28) ** 0.5
                    else:
                        fct = fct28
            except Exception:
                fct = 0
            fct_vals.append(fct)
        
        df = pd.DataFrame({"t[일]": np.round(t_vals, 2), "fct(t) 인장강도 [GPa]": np.round(fct_vals, 4)})
        preview_table = dash_table.DataTable(
            columns=[{"name": i, "id": i} for i in df.columns],
            data=df.to_dict("records"),
            page_size=10,
            style_table={"overflowY": "auto", "height": "240px", "marginTop": "8px"},
            style_cell={"textAlign": "center"},
            style_header={"backgroundColor": "#f8fafc", "fontWeight": "600"},
        )
        
        # 그래프 생성
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=t_vals,
            y=fct_vals,
            mode='lines+markers',
            name='fct(t)',
            line=dict(color='#3b82f6', width=2),
            marker=dict(size=4, color='#3b82f6')
        ))
        
        fig.update_layout(
            title="인장강도 발달 곡선",
            xaxis_title="일령 (일)",
            yaxis_title="인장강도 (MPa)",
            height=300,
            margin=dict(l=50, r=50, t=50, b=50),
            showlegend=False,
            plot_bgcolor='white',
            paper_bgcolor='white'
        )
        
        fig.update_xaxes(gridcolor='#e5e7eb', showgrid=True)
        fig.update_yaxes(gridcolor='#e5e7eb', showgrid=True)
        
        preview_content = html.Div([
            html.Small(formula_text, style={"color": "#64748b"}),
            html.Div("↓ 1~28일 인장강도 미리보기 (0.1 간격)", style={"marginTop": "8px", "fontSize": "13px", "color": "#64748b"}),
            dbc.Row([
                dbc.Col(preview_table, md=6),
                dbc.Col(dcc.Graph(figure=fig, config={'displayModeBar': False}), md=6)
            ], className="g-2")
        ])
    except Exception:
        preview_content = html.Small(formula_text, style={"color": "#64748b"})
    
    return preview_content

# ───────────── 입력값 검증 및 알림 콜백 ─────────────
@callback(
    Output("temp-project-alert", "children", allow_duplicate=True),
    Output("temp-project-alert", "color", allow_duplicate=True),
    Output("temp-project-alert", "is_open", allow_duplicate=True),
    Input("fct28-input", "value"),
    State("fct-formula-type", "value"),
    prevent_initial_call=True
)
def validate_inputs(fct28, formula_type):
    messages = []
    
    # fct28 검증
    if fct28 is not None and fct28 != "":
        try:
            fct28_val = float(fct28)
            if fct28_val < 1 or fct28_val > 100:
                messages.append(f"28일 인장강도는 1~100 GPa 범위 내에서 입력하세요. (현재: {fct28_val} GPa)")
        except ValueError:
            messages.append("28일 인장강도는 숫자로 입력하세요.")
    
    # CEB 공식일 때만 a, b 검증 (동적으로 생성된 입력 필드는 별도 콜백에서 처리)
    pass
    
    if messages:
        return "\n".join(messages), "warning", True
    
    return dash.no_update, dash.no_update, dash.no_update