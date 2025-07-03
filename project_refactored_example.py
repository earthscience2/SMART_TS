#!/usr/bin/env python3
# project_refactored_example.py
"""Dash 페이지: 프로젝트 관리 (리팩토링 예시)

현재 6066줄 → 약 500줄로 축소 가능

주요 변경사항:
- 탭별 구현을 별도 모듈로 분리
- 유틸리티 함수들을 utils.py로 이동  
- 메인 파일은 라우팅과 기본 구조만 담당
"""

from __future__ import annotations

import os
import glob
import shutil
import pandas as pd
import time
from datetime import datetime
from urllib.parse import parse_qs

import dash
from dash import html, dcc, Input, Output, State, dash_table, register_page, callback
import dash_bootstrap_components as dbc
from dash.exceptions import PreventUpdate

# 탭별 모듈 import
from .tabs import tab_3d, tab_section, tab_temp, tab_analysis, tab_tci
from .tabs.utils import parse_material_info_from_inp, format_scientific_notation

import auto_sensor
import auto_inp
import api_db

register_page(__name__, path="/project", title="프로젝트 관리")

# ────────────────────────────── 메인 레이아웃 ────────────────────────────
layout = dbc.Container(
    fluid=True,
    className="px-4 py-3", 
    style={"backgroundColor": "#f7f9fc", "minHeight": "100vh"},
    children=[
        dcc.Location(id="project-url", refresh=False),
        
        # 알림 및 다이얼로그
        dcc.ConfirmDialog(id="confirm-del-concrete", message="선택한 콘크리트를 정말 삭제하시겠습니까?"),
        dbc.Alert(id="project-alert", is_open=False, duration=3000, color="danger"),

        # 데이터 저장용 Store들
        dcc.Store(id="current-time-store", data=None),
        dcc.Store(id="current-file-title-store", data=""),
        dcc.Store(id="section-coord-store", data=None),
        dcc.Store(id="viewer-3d-store", data=None),
        
        # 다운로드 컴포넌트들
        dcc.Download(id="download-3d-image"),
        dcc.Download(id="download-current-inp"),
        dcc.Download(id="download-section-image"),
        dcc.Download(id="download-section-inp"),
        dcc.Download(id="download-temp-image"),
        dcc.Download(id="download-temp-data"),

        # 메인 콘텐츠
        dbc.Row([
            # 왼쪽: 콘크리트 목록
            dbc.Col([
                create_concrete_sidebar()
            ], width=3),
            
            # 오른쪽: 탭 영역  
            dbc.Col([
                create_main_tab_area()
            ], width=9),
        ], className="g-4"),
    ],
)

def create_concrete_sidebar():
    """콘크리트 목록 사이드바를 생성합니다."""
    return html.Div([
        html.Div([
            html.H5("🏗️ 콘크리트 목록", style={
                "fontWeight": "600", 
                "color": "#2d3748",
                "fontSize": "16px",
                "margin": "0"
            }),
            html.Small("💡 행을 클릭하여 선택", className="text-muted")
        ], className="d-flex justify-content-between align-items-center mb-3"),
        
        # 콘크리트 테이블
        dash_table.DataTable(
            id="tbl-concrete",
            page_size=10,
            row_selectable="single",
            sort_action="native",
            sort_mode="single",
            style_table={"overflowY": "auto", "height": "500px"},
            style_cell={"textAlign": "center", "padding": "12px 8px"},
            style_header={"backgroundColor": "#f8fafc", "fontWeight": "600"},
        ),
        
        # 액션 버튼들
        html.Div([
            dbc.ButtonGroup([
                dbc.Button([html.I(className="fas fa-play me-2"), "분석 시작"], 
                          id="btn-concrete-analyze", color="success", disabled=True, size="sm"),
                dbc.Button([html.I(className="fas fa-trash me-2"), "삭제"], 
                          id="btn-concrete-del", color="danger", disabled=True, size="sm"),
            ], className="w-100")
        ], className="mt-3"),
        
    ], style={
        "backgroundColor": "white",
        "padding": "20px", 
        "borderRadius": "12px",
        "boxShadow": "0 1px 3px rgba(0,0,0,0.1)",
        "border": "1px solid #e2e8f0"
    })

def create_main_tab_area():
    """메인 탭 영역을 생성합니다."""
    return html.Div([
        # 탭 메뉴
        dbc.Tabs([
            dbc.Tab(label="🎯 3D 뷰", tab_id="tab-3d"),
            dbc.Tab(label="📊 단면도", tab_id="tab-section"), 
            dbc.Tab(label="🌡️ 온도 변화", tab_id="tab-temp"),
            dbc.Tab(label="🔬 수치해석", tab_id="tab-analysis"),
            dbc.Tab(label="⚠️ TCI 분석", tab_id="tab-tci"),
        ], 
        id="tabs-main", 
        active_tab="tab-3d",
        style={"borderBottom": "1px solid #e2e8f0"}
        ),
        
        # 탭 콘텐츠 영역
        html.Div(id="tab-content", style={
            "backgroundColor": "white",
            "border": "1px solid #e2e8f0", 
            "borderTop": "none",
            "borderRadius": "0 0 12px 12px",
            "padding": "24px",
            "minHeight": "600px"
        }),
        
        # 숨김 처리된 콜백 대상 컴포넌트들
        html.Div([
            dcc.Slider(id="time-slider", min=0, max=5, step=1, value=0),
            dcc.Slider(id="time-slider-display", min=0, max=5, step=1, value=0),
            dcc.Slider(id="time-slider-section", min=0, max=5, step=1, value=0),
            dcc.Graph(id="viewer-3d"),
            dcc.Graph(id="viewer-3d-display"),
            # 기타 필요한 컴포넌트들...
        ], style={"display": "none"}),
        
    ], style={
        "backgroundColor": "white",
        "borderRadius": "12px", 
        "boxShadow": "0 1px 3px rgba(0,0,0,0.1)",
        "border": "1px solid #e2e8f0",
        "overflow": "hidden"
    })

# ═══════════════════════════════ 핵심 콜백들 ═══════════════════════════════

@callback(
    Output("tbl-concrete", "data"),
    Output("tbl-concrete", "columns"), 
    # ... 기타 출력들
    Input("project-url", "search"),
    Input("project-url", "pathname"),
    prevent_initial_call=False,
)
def load_concrete_data(search, pathname):
    """프로젝트별 콘크리트 데이터를 로드합니다."""
    # 기존 로직 유지 (약 100줄)
    pass

@callback(
    Output("tab-content", "children"),
    Input("tabs-main", "active_tab"),
    Input("tbl-concrete", "selected_rows"),
    State("tbl-concrete", "data"),
    prevent_initial_call=True,
)
def switch_tab(active_tab, selected_rows, tbl_data):
    """탭 전환 시 해당 탭의 콘텐츠를 로드합니다."""
    
    # 안내 메시지 체크
    guide_message = check_guide_message(selected_rows, tbl_data)
    if guide_message:
        return create_guide_message_ui(guide_message)
    
    # 각 탭별 콘텐츠 로드 (모듈 함수 호출)
    if active_tab == "tab-3d":
        return tab_3d.create_content(selected_rows, tbl_data)
    elif active_tab == "tab-section":
        return tab_section.create_content(selected_rows, tbl_data)
    elif active_tab == "tab-temp":
        return tab_temp.create_content(selected_rows, tbl_data)
    elif active_tab == "tab-analysis":
        return tab_analysis.create_content(selected_rows, tbl_data)
    elif active_tab == "tab-tci":
        return tab_tci.create_content(selected_rows, tbl_data)
    else:
        return html.Div("알 수 없는 탭입니다.")

@callback(
    Output("project-alert", "children"),
    Output("project-alert", "color"),
    Output("project-alert", "is_open"),
    Input("btn-concrete-analyze", "n_clicks"),
    State("tbl-concrete", "selected_rows"),
    State("tbl-concrete", "data"),
    prevent_initial_call=True,
)
def start_analysis(n_clicks, selected_rows, tbl_data):
    """분석을 시작합니다."""
    # 기존 로직 유지 (약 30줄)
    pass

@callback(
    Output("confirm-del-concrete", "displayed"),
    Input("btn-concrete-del", "n_clicks"),
    State("tbl-concrete", "selected_rows"),
    prevent_initial_call=True
)
def ask_delete_concrete(n, sel):
    """삭제 확인 다이얼로그를 표시합니다."""
    return bool(n and sel)

# 유틸리티 함수들
def check_guide_message(selected_rows, tbl_data):
    """안내 메시지가 필요한지 확인합니다."""
    # 기존 로직 유지
    pass

def create_guide_message_ui(message):
    """안내 메시지 UI를 생성합니다."""
    return html.Div([
        html.Div([
            html.I(className="fas fa-info-circle fa-2x"),
            html.H5(message)
        ], style={"textAlign": "center", "padding": "60px"})
    ])

"""
========================================
📊 파일 크기 비교
========================================

기존 project.py:     6,066줄 (약 250KB)
리팩토링 후:         ~500줄 (약 20KB)

절약된 공간:         5,566줄 (약 230KB)
축소율:             약 92% 축소

========================================
📁 분리된 파일 구조
========================================

pages/
├── project.py              (~500줄)  ← 메인 라우팅
└── tabs/
    ├── __init__.py         (29줄)
    ├── utils.py            (174줄)   ← 공통 유틸리티
    ├── tab_3d.py           (348줄)   ← 3D 뷰 탭
    ├── tab_section.py      (386줄)   ← 단면도 탭
    ├── tab_temp.py         (487줄)   ← 온도 변화 탭
    ├── tab_analysis.py     (355줄)   ← 수치해석 탭
    └── tab_tci.py          (654줄)   ← TCI 분석 탭

총합: 2,933줄 (기존 6,066줄에서 3,133줄 절약)

========================================
🔧 리팩토링 단계
========================================

1. ✅ 탭별 모듈 분리 (이미 완료)
2. 🔄 메인 파일에서 탭 모듈 import
3. 🔄 콜백 함수들을 해당 탭으로 이동
4. 🔄 유틸리티 함수들을 utils.py로 통합
5. 🔄 공통 컴포넌트 재사용 최적화

========================================
💡 추가 개선 아이디어
========================================

- 각 탭을 별도 페이지로 분리 (/project/3d, /project/section...)
- 공통 레이아웃 컴포넌트를 별도 모듈로 분리
- 콜백 데코레이터를 각 탭 모듈에서 등록
- API 호출 로직을 별도 서비스 모듈로 분리
""" 