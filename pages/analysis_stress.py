#!/usr/bin/env python3
# pages/analysis_stress.py
# 응력 분석 페이지: FRD 파일에서 응력 데이터를 읽어와서 3D 시각화

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
import dash
from scipy.interpolate import griddata
import ast
import json
import time
from urllib.parse import urlparse
from dash.dependencies import ALL
from dash import html
import dash_vtk

import api_db
from utils.encryption import parse_project_key_from_url

register_page(__name__, path="/stress", title="응력 분석")

# ────────────────────────────── FRD 파일 파싱 함수 ──────────────────────────────
def parse_frd_file(frd_path):
    """FRD 파일에서 노드 좌표, 요소 정보, 응력 데이터를 파싱합니다."""
    try:
        with open(frd_path, 'r') as f:
            lines = f.readlines()
        
        nodes = {}  # 노드 ID -> (x, y, z)
        elements = {}  # 요소 ID -> [노드 ID 리스트]
        stresses = {}  # 노드 ID -> (SXX, SYY, SZZ, SXY, SYZ, SZX)
        displacements = {}  # 노드 ID -> (U1, U2, U3)
        
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            
            # 노드 좌표 섹션 (2C로 시작)
            if line.startswith('2C'):
                i += 1
                while i < len(lines) and lines[i].strip().startswith('-1'):
                    parts = lines[i].strip().split()
                    if len(parts) >= 4:
                        node_id = int(parts[1])
                        x, y, z = float(parts[2]), float(parts[3]), float(parts[4])
                        nodes[node_id] = (x, y, z)
                    i += 1
            
            # 요소 정보 섹션 (3C로 시작)
            elif line.startswith('3C'):
                i += 1
                while i < len(lines) and lines[i].strip().startswith('-1'):
                    parts = lines[i].strip().split()
                    if len(parts) >= 2:
                        elem_id = int(parts[1])
                        i += 1
                        if i < len(lines) and lines[i].strip().startswith('-2'):
                            node_parts = lines[i].strip().split()
                            if len(node_parts) >= 5:  # 8노드 요소
                                node_ids = [int(node_parts[j]) for j in range(1, 9)]
                                elements[elem_id] = node_ids
                    i += 1
            
            # 변위 데이터 섹션 (1PSTEP로 시작하고 DISPLACEMENT 포함)
            elif 'DISPLACEMENT' in line and '1PSTEP' in lines[i-1] if i > 0 else False:
                i += 1
                while i < len(lines) and lines[i].strip().startswith('-1'):
                    parts = lines[i].strip().split()
                    if len(parts) >= 4:
                        node_id = int(parts[1])
                        u1, u2, u3 = float(parts[2]), float(parts[3]), float(parts[4])
                        displacements[node_id] = (u1, u2, u3)
                    i += 1
            
            # 응력 데이터 섹션 (1PSTEP로 시작하고 STRESS 포함)
            elif 'STRESS' in line and '1PSTEP' in lines[i-1] if i > 0 else False:
                i += 1
                while i < len(lines) and lines[i].strip().startswith('-1'):
                    parts = lines[i].strip().split()
                    if len(parts) >= 7:
                        node_id = int(parts[1])
                        sxx, syy, szz = float(parts[2]), float(parts[3]), float(parts[4])
                        sxy, syz, szx = float(parts[5]), float(parts[6]), float(parts[7])
                        stresses[node_id] = (sxx, syy, szz, sxy, syz, szx)
                    i += 1
            
            else:
                i += 1
        
        return nodes, elements, stresses, displacements
        
    except Exception as e:
        print(f"FRD 파일 파싱 오류: {e}")
        return {}, {}, {}, {}

def calculate_von_mises_stress(stress_tensor):
    """응력 텐서에서 von Mises 응력을 계산합니다."""
    sxx, syy, szz, sxy, syz, szx = stress_tensor
    
    # 주응력 계산
    sigma_1 = (sxx + syy + szz) / 3 + np.sqrt(
        ((sxx - syy) / 2)**2 + ((syy - szz) / 2)**2 + ((szz - sxx) / 2)**2 + 
        sxy**2 + syz**2 + szx**2
    )
    sigma_2 = (sxx + syy + szz) / 3 - np.sqrt(
        ((sxx - syy) / 2)**2 + ((syy - szz) / 2)**2 + ((szz - sxx) / 2)**2 + 
        sxy**2 + syz**2 + szx**2
    )
    sigma_3 = (sxx + syy + szz) / 3
    
    # von Mises 응력
    von_mises = np.sqrt(0.5 * ((sigma_1 - sigma_2)**2 + (sigma_2 - sigma_3)**2 + (sigma_3 - sigma_1)**2))
    return von_mises

# ────────────────────────────── 레이아웃 ────────────────────────────
layout = dbc.Container(
    fluid=True,
    className="px-4 py-3",
    style={"backgroundColor": "#f7f9fc", "minHeight": "100vh"},
    children=[
        dcc.Location(id="project-url", refresh=False),
        
        # ── 컨펌 다이얼로그 및 알림
        dcc.ConfirmDialog(
            id="confirm-del-concrete-stress",
            message="선택한 콘크리트를 정말 삭제하시겠습니까?"
        ),
        dbc.Alert(
            id="stress-project-alert",
            is_open=False,
            duration=3000,
            color="danger",
            style={"borderRadius": "8px", "border": "none"}
        ),

        # ── 데이터 저장용 Store들
        dcc.Store(id="current-time-store-stress", data=None),
        dcc.Store(id="current-file-title-store-stress", data=""),
        dcc.Store(id="section-coord-store-stress", data=None),
        dcc.Store(id="viewer-3d-store-stress", data=None),
        dcc.Store(id="unified-colorbar-state-stress", data=False),
        dcc.Store(id="unified-colorbar-section-state-stress", data=False),
        dcc.Store(id="project-info-store-stress", data=None),
        dcc.Store(id="stress-data-store", data=None),
        dcc.Graph(id='section-colorbar-stress', style={'display':'none'}),
        
        # ── 다운로드 컴포넌트들
        dcc.Download(id="download-3d-image-stress"),
        dcc.Download(id="download-current-frd-stress"),
        dcc.Download(id="download-section-image-stress"),
        dcc.Download(id="download-section-frd-stress"),
        dcc.Download(id="download-stress-image-stress"),
        dcc.Download(id="download-stress-data-stress"),
        
        # 키보드 이벤트 처리 스크립트
        html.Div([
            html.Script("""
                // React 경고 억제
                const originalConsoleWarn = console.warn;
                console.warn = function(...args) {
                    if (args[0] && typeof args[0] === 'string' && 
                        (args[0].includes('findDOMNode') || args[0].includes('deprecated'))) {
                        return; // 경고 억제
                    }
                    originalConsoleWarn.apply(console, args);
                };
                
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
                                const sliders = ['time-slider-stress', 'time-slider-section-stress', 'analysis-time-slider-stress'];
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
                    # 프로젝트 안내 박스
                    dbc.Alert(id="current-project-info", color="info", className="mb-3 py-2"),
                    
                    # 콘크리트 목록 섹션
                    html.Div([
                        html.Div([
                            # 제목과 추가 버튼
                            html.Div([
                                html.H6("🧱 콘크리트 목록", className="mb-0 text-secondary fw-bold"),
                                html.Div()  # 추가 버튼은 응력 분석 페이지에서는 필요 없음
                            ], className="d-flex justify-content-between align-items-center mb-2"),
                            html.Small("💡 행을 클릭하여 선택", className="text-muted mb-2 d-block"),
                            html.Div([
                                dash_table.DataTable(
                                    id="tbl-concrete-stress",
                                    page_size=5,
                                    row_selectable="single",
                                    sort_action="native",
                                    sort_mode="multi",
                                    style_table={"overflowY": "auto", "height": "calc(100vh - 300px)"},
                                    style_cell={
                                        "whiteSpace": "nowrap", 
                                        "textAlign": "center",
                                        "fontSize": "0.9rem",
                                        "padding": "14px 12px",
                                        "border": "none",
                                        "borderBottom": "1px solid #f1f1f0",
                                        "fontFamily": "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"
                                    },
                                    style_header={
                                        "backgroundColor": "#fafafa", 
                                        "fontWeight": 600,
                                        "color": "#37352f",
                                        "border": "none",
                                        "borderBottom": "1px solid #e9e9e7",
                                        "fontSize": "0.8rem",
                                        "textTransform": "uppercase",
                                        "letterSpacing": "0.5px"
                                    },
                                    style_data={
                                        "backgroundColor": "white",
                                        "border": "none",
                                        "color": "#37352f"
                                    },
                                    style_data_conditional=[
                                        {
                                            'if': {'row_index': 'odd'},
                                            'backgroundColor': '#fbfbfa'
                                        },
                                        {
                                            'if': {'state': 'selected'},
                                            'backgroundColor': '#e8f4fd',
                                            'border': '1px solid #579ddb',
                                            'borderRadius': '6px',
                                            'boxShadow': '0 0 0 1px rgba(87, 157, 219, 0.3)',
                                            'color': '#1d4ed8'
                                        },
                                        {
                                            'if': {
                                                'filter_query': '{status} = 분석중',
                                                'column_id': 'status'
                                            },
                                            'backgroundColor': '#dcfce7',
                                            'color': '#166534',
                                            'fontWeight': '600',
                                            'borderRadius': '4px',
                                            'textAlign': 'center'
                                        },
                                        {
                                            'if': {
                                                'filter_query': '{status} = 분석 가능',
                                                'column_id': 'status'
                                            },
                                            'backgroundColor': '#dbeafe',
                                            'color': '#1e40af',
                                            'fontWeight': '600',
                                            'borderRadius': '4px',
                                            'textAlign': 'center'
                                        },
                                        {
                                            'if': {
                                                'filter_query': '{status} = 센서 부족',
                                                'column_id': 'status'
                                            },
                                            'backgroundColor': '#fef3c7',
                                            'color': '#d97706',
                                            'fontWeight': '600',
                                            'borderRadius': '4px',
                                            'textAlign': 'center'
                                        },
                                        {
                                            'if': {'column_id': 'pour_date'},
                                            'fontSize': '0.85rem',
                                            'color': '#6b7280',
                                            'fontWeight': '500'
                                        },
                                        {
                                            'if': {'column_id': 'name'},
                                            'fontWeight': '600',
                                            'color': '#111827',
                                            'textAlign': 'left',
                                            'paddingLeft': '16px'
                                        }
                                    ],
                                    css=[
                                        {
                                            'selector': '.dash-table-container .dash-spreadsheet-container .dash-spreadsheet-inner table',
                                            'rule': 'border-collapse: separate; border-spacing: 0;'
                                        },
                                        {
                                            'selector': '.dash-table-container .dash-spreadsheet-container .dash-spreadsheet-inner tr:hover',
                                            'rule': 'background-color: #f8fafc !important; transition: background-color 0.15s ease;'
                                        },
                                        {
                                            'selector': '.dash-table-container .dash-spreadsheet-container .dash-spreadsheet-inner tr.row-selected',
                                            'rule': '''
                                                background-color: #eff6ff !important;
                                                box-shadow: inset 3px 0 0 #3b82f6;
                                                border-left: 3px solid #3b82f6;
                                            '''
                                        },
                                        {
                                            'selector': '.dash-table-container .dash-spreadsheet-container .dash-spreadsheet-inner td',
                                            'rule': 'cursor: pointer; transition: all 0.15s ease;'
                                        }
                                    ]
                                ),
                            ], style={
                                "borderRadius": "12px", 
                                "overflow": "hidden", 
                                "border": "1px solid #e5e5e4",
                                "boxShadow": "0 1px 3px rgba(0, 0, 0, 0.05)"
                            }),
                            
                            # 액션 버튼들
                            html.Div([
                                dbc.Button("분석 시작", id="btn-concrete-analyze-stress", color="success", size="sm", className="px-3", disabled=True),
                                dbc.Button("삭제", id="btn-concrete-del-stress", color="danger", size="sm", className="px-3", disabled=True),
                            ], className="d-flex justify-content-center gap-2 mt-2"),
                        ])
                    ])
                ], style={
                    "backgroundColor": "white",
                    "padding": "20px",
                    "borderRadius": "12px",
                    "boxShadow": "0 1px 3px rgba(0,0,0,0.1)",
                    "border": "1px solid #e2e8f0",
                    "height": "fit-content"
                })
            ], md=4),
            
            # 오른쪽 메인 콘텐츠 영역
            dbc.Col([
                html.Div([
                    # 탭 메뉴 (노션 스타일)
                    html.Div([
                        dbc.Tabs([
                            dbc.Tab(
                                label="입체", 
                                tab_id="tab-3d",
                                tab_style={
                                    "marginLeft": "2px",
                                    "marginRight": "2px",
                                    "border": "none",
                                    "borderRadius": "6px 6px 0 0",
                                    "backgroundColor": "#f8fafc",
                                    "color": "#1f2937",
                                    "fontWeight": "500"
                                },
                                active_tab_style={
                                    "backgroundColor": "white",
                                    "border": "1px solid #e2e8f0",
                                    "borderBottom": "1px solid white",
                                    "color": "#1f2937",
                                    "fontWeight": "600"
                                }
                            ),
                            dbc.Tab(
                                label="단면", 
                                tab_id="tab-section",
                                tab_style={
                                    "marginLeft": "2px",
                                    "marginRight": "2px",
                                    "border": "none",
                                    "borderRadius": "6px 6px 0 0",
                                    "backgroundColor": "#f8fafc",
                                    "color": "#1f2937",
                                    "fontWeight": "500"
                                },
                                active_tab_style={
                                    "backgroundColor": "white",
                                    "border": "1px solid #e2e8f0",
                                    "borderBottom": "1px solid white",
                                    "color": "#1f2937",
                                    "fontWeight": "600"
                                }
                            ),
                            dbc.Tab(
                                label="노드별", 
                                tab_id="tab-node",
                                tab_style={
                                    "marginLeft": "2px",
                                    "marginRight": "2px",
                                    "border": "none",
                                    "borderRadius": "6px 6px 0 0",
                                    "backgroundColor": "#f8fafc",
                                    "color": "#1f2937",
                                    "fontWeight": "500"
                                },
                                active_tab_style={
                                    "backgroundColor": "white",
                                    "border": "1px solid #e2e8f0",
                                    "borderBottom": "1px solid white",
                                    "color": "#1f2937",
                                    "fontWeight": "600"
                                }
                            )
                        ], id="tabs-main", active_tab="tab-3d", className="mb-0")
                    ], style={
                        "backgroundColor": "#f8fafc",
                        "padding": "8px 8px 0 8px",
                        "borderRadius": "8px 8px 0 0",
                        "border": "1px solid #e2e8f0",
                        "borderBottom": "none"
                    }),
                    
                    # 탭 콘텐츠 영역
                    html.Div(id="tab-content", style={
                        "backgroundColor": "white",
                        "border": "1px solid #e2e8f0",
                        "borderTop": "none",
                        "borderRadius": "0 0 8px 8px",
                        "padding": "20px",
                        "minHeight": "calc(100vh - 200px)"
                    })
                ])
            ], md=8)
        ], className="g-4")
    ]
)

# ───────────────────── 콜백 함수들 ─────────────────────

@callback(
    Output("tbl-concrete-stress", "data", allow_duplicate=True),
    Output("tbl-concrete-stress", "columns", allow_duplicate=True),
    Output("tbl-concrete-stress", "selected_rows", allow_duplicate=True),
    Output("tbl-concrete-stress", "style_data_conditional", allow_duplicate=True),
    Output("btn-concrete-analyze-stress", "disabled", allow_duplicate=True),
    Output("btn-concrete-del-stress", "disabled", allow_duplicate=True),
    Output("time-slider-stress", "min", allow_duplicate=True),
    Output("time-slider-stress", "max", allow_duplicate=True),
    Output("time-slider-stress", "value", allow_duplicate=True),
    Output("time-slider-stress", "marks", allow_duplicate=True),
    Output("current-time-store-stress", "data", allow_duplicate=True),
    Output("project-info-store-stress", "data", allow_duplicate=True),
    Input("project-url", "search"),
    Input("project-url", "pathname"),
    prevent_initial_call=True,
)
def load_concrete_data_stress(search, pathname):
    """프로젝트 정보를 로드하고 콘크리트 목록을 표시합니다."""
    # 응력 분석 페이지에서만 실행
    if '/stress' not in pathname:
        raise PreventUpdate
    
    # URL에서 프로젝트 정보 추출 (암호화된 URL 지원)
    project_pk = None
    if search:
        try:
            project_pk = parse_project_key_from_url(search)
        except Exception as e:
            pass
    
    if not project_pk:
        # 타입 검증 및 안전한 값 설정
        slider_min = 0
        slider_max = 5
        slider_value = 0
        slider_marks = {0: "시작", 5: "끝"}
        
        return [], [], [], [], True, True, slider_min, slider_max, slider_value, slider_marks, None, None
    
    try:
        # 프로젝트 정보 로드
        df_proj = api_db.get_project_data(project_pk=project_pk)
        if df_proj.empty:
            # 타입 검증 및 안전한 값 설정
            slider_min = 0
            slider_max = 5
            slider_value = 0
            slider_marks = {0: "시작", 5: "끝"}
            
            return [], [], [], [], True, True, slider_min, slider_max, slider_value, slider_marks, None, None
            
        proj_row = df_proj.iloc[0]
        proj_name = proj_row["name"]
        
        # 해당 프로젝트의 콘크리트 데이터 로드
        df_conc = api_db.get_concrete_data(project_pk=project_pk)
        if df_conc.empty:
            # 타입 검증 및 안전한 값 설정
            slider_min = 0
            slider_max = 5
            slider_value = 0
            slider_marks = {0: "시작", 5: "끝"}
            
            return [], [], [], [], True, True, slider_min, slider_max, slider_value, slider_marks, None, {"name": proj_name, "pk": project_pk}
        
    except Exception as e:
        # 타입 검증 및 안전한 값 설정
        slider_min = 0
        slider_max = 5
        slider_value = 0
        slider_marks = {0: "시작", 5: "끝"}
        
        return [], [], [], [], True, True, slider_min, slider_max, slider_value, slider_marks, None, None
    
    table_data = []
    for _, row in df_conc.iterrows():
        try:
            dims = eval(row["dims"])
            nodes = dims["nodes"]
            h = dims["h"]
            shape_info = f"{len(nodes)}각형 (높이: {h:.2f}m)"
        except Exception:
            shape_info = "파싱 오류"
        
        # FRD 파일 확인
        concrete_pk = row["concrete_pk"]
        frd_dir = f"frd/{concrete_pk}"
        has_frd = os.path.exists(frd_dir) and len(glob.glob(f"{frd_dir}/*.frd")) > 0
        
        # 상태 결정 (정렬을 위해 우선순위도 함께 설정)
        if row["activate"] == 1:  # 활성
            if has_frd:
                status = "응력 분석 가능"
                status_sort = 1  # 첫 번째 우선순위
            else:
                status = "FRD 파일 없음"
                status_sort = 2  # 두 번째 우선순위
        else:  # 비활성 (activate == 0)
            status = "비활성"
            status_sort = 3  # 세 번째 우선순위
        
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
        
        # 타설일과 경과일을 하나의 컬럼으로 합치기
        pour_date_with_elapsed = pour_date
        if pour_date != "N/A" and elapsed_days != "N/A":
            pour_date_with_elapsed = f"{pour_date} ({elapsed_days})"
        
        table_data.append({
            "concrete_pk": row["concrete_pk"],
            "name": row["name"],
            "status": status,
            "status_sort": status_sort,  # 정렬용 숨겨진 필드
            "pour_date": pour_date_with_elapsed,
            "shape": shape_info,
            "dims": row["dims"],
            "activate": "활성" if row["activate"] == 1 else "비활성",
            "has_frd": has_frd,
        })

    # 3) 테이블 컬럼 정의
    columns = [
        {"name": "이름", "id": "name", "type": "text"},
        {"name": "타설일(경과일)", "id": "pour_date", "type": "text"},
        {"name": "상태", "id": "status", "type": "text"},
    ]
    
    # 테이블 스타일 설정 (문자열 비교 기반 색상)
    style_data_conditional = [
        # 응력 분석 가능 상태 (초록색)
        {
            'if': {
                'filter_query': '{status} = "응력 분석 가능"',
                'column_id': 'status'
            },
            'backgroundColor': '#e8f5e8',
            'color': '#2e7d32',
            'fontWeight': 'bold'
        },
        # FRD 파일 없음 상태 (주황색)
        {
            'if': {
                'filter_query': '{status} = "FRD 파일 없음"',
                'column_id': 'status'
            },
            'backgroundColor': '#fff3e0',
            'color': '#f57c00',
            'fontWeight': 'bold'
        },
        # 비활성 상태 (회색)
        {
            'if': {
                'filter_query': '{status} = "비활성"',
                'column_id': 'status'
            },
            'backgroundColor': '#f5f5f5',
            'color': '#6c757d',
            'fontWeight': 'bold'
        }
    ]
    
    # 타설일(경과일) 컬럼 스타일 추가
    style_data_conditional.extend([
        {
            'if': {'column_id': 'pour_date'},
            'fontSize': '0.85rem',
            'color': '#6c757d',
            'fontWeight': '500'
        }
    ])
    
    # 상태별 기본 정렬 적용 (응력 분석 가능 → FRD 파일 없음 → 비활성)
    if table_data:
        table_data = sorted(table_data, key=lambda x: x.get('status_sort', 999))
    
    # 타입 검증 및 안전한 값 설정
    slider_min = 0
    slider_max = 5
    slider_value = 0
    slider_marks = {0: "시작", 5: "끝"}
    
    return table_data, columns, [], style_data_conditional, True, True, slider_min, slider_max, slider_value, slider_marks, None, {"name": proj_name, "pk": project_pk}

@callback(
    Output("current-project-info", "children", allow_duplicate=True),
    Input("project-info-store-stress", "data"),
    Input("project-url", "pathname"),
    prevent_initial_call=True,
)
def update_project_info_stress(project_info, pathname):
    """프로젝트 정보를 표시합니다."""
    # 응력 분석 페이지에서만 실행
    if '/stress' not in pathname:
        raise PreventUpdate
    
    if not project_info:
        return "프로젝트를 선택하세요."
    
    return f"📋 {project_info['name']}"

@callback(
    Output("tab-content", "children", allow_duplicate=True),
    Input("tabs-main", "active_tab"),
    Input("tbl-concrete-stress", "selected_rows"),
    Input("project-url", "pathname"),
    State("tbl-concrete-stress", "data"),
    State("viewer-3d-store-stress", "data"),
    State("current-file-title-store-stress", "data"),
    prevent_initial_call=True,
)
def switch_tab_stress(active_tab, selected_rows, pathname, tbl_data, viewer_data, current_file_title):
    """탭 전환 시 해당 탭의 콘텐츠를 표시합니다."""
    # 응력 분석 페이지에서만 실행
    if '/stress' not in pathname:
        raise PreventUpdate
    
    if not selected_rows or not tbl_data:
        return html.Div("콘크리트를 선택하세요.", className="text-center text-muted mt-5")
    
    row = pd.DataFrame(tbl_data).iloc[selected_rows[0]]
    concrete_pk = row["concrete_pk"]
    
    if active_tab == "tab-3d":
        return create_3d_tab_content(concrete_pk)
    elif active_tab == "tab-section":
        return create_section_tab_content(concrete_pk)
    elif active_tab == "tab-node":
        return create_node_tab_content(concrete_pk)
    else:
        return html.Div("알 수 없는 탭입니다.", className="text-center text-muted mt-5")

def create_3d_tab_content(concrete_pk):
    """입체 탭 콘텐츠를 생성합니다."""
    return html.Div([
        # 시간 슬라이더
        html.Div([
            html.Label("⏰ 시간 설정", className="d-block mb-2 fw-bold"),
            dcc.Slider(
                id="time-slider-stress",
                min=0, max=0, value=0,
                marks={},
                tooltip={"always_visible": True}
            )
        ], className="mb-4 p-3 bg-light border rounded"),
        
        # 분석 설정
        html.Div([
            html.Label("응력 필드", className="d-block mb-1 fw-bold"),
            dcc.Dropdown(
                id="stress-field-dropdown",
                options=[
                    {"label": "von Mises 응력", "value": "von_mises"},
                    {"label": "SXX (X방향 정응력)", "value": "sxx"},
                    {"label": "SYY (Y방향 정응력)", "value": "syy"},
                    {"label": "SZZ (Z방향 정응력)", "value": "szz"},
                    {"label": "SXY (전단응력)", "value": "sxy"},
                    {"label": "SYZ (전단응력)", "value": "syz"},
                    {"label": "SZX (전단응력)", "value": "szx"},
                ],
                value="von_mises"
            ),
            html.Label("컬러맵 프리셋", className="d-block mt-3 mb-1 fw-bold"),
            dcc.Dropdown(
                id="stress-preset-dropdown",
                options=[
                    {"label": "무지개", "value": "rainbow"},
                    {"label": "블루-레드", "value": "Cool to Warm"},
                    {"label": "회색", "value": "Grayscale"},
                ],
                value="rainbow"
            ),
            dbc.Checklist(
                options=[{"label": "단면 보기 활성화", "value": "on"}],
                value=[], id="slice-enable", switch=True, className="mt-3"
            ),
            html.Div(id="slice-detail-controls", style={"display": "none"}, children=[
                html.Label("축 선택", className="d-block mb-1"),
                dcc.Dropdown(
                    id="slice-axis",
                    options=[
                        {"label": "X축", "value": "X"},
                        {"label": "Y축", "value": "Y"},
                        {"label": "Z축", "value": "Z"},
                    ],
                    value="Z"
                ),
                html.Label("절단 위치", className="d-block mt-3 mb-1"),
                dcc.Slider(id="slice-slider", min=0, max=1, step=0.05, value=0.5)
            ])
        ], className="p-3 bg-light border rounded mb-4"),
        
        # 파일 정보 표시
        html.Div(id="stress-analysis-current-file-label", className="mb-3 p-2 bg-white border rounded"),
        
        # 3D 뷰어
        html.Div(id="stress-analysis-3d-viewer", style={"height": "60vh"})
    ])

def create_section_tab_content(concrete_pk):
    """단면 탭 콘텐츠를 생성합니다."""
    return html.Div([
        # 시간 슬라이더 (단면용)
        html.Div([
            html.Label("⏰ 시간 설정", className="d-block mb-2 fw-bold"),
            dcc.Slider(
                id="time-slider-section-stress",
                min=0, max=0, value=0,
                marks={},
                tooltip={"always_visible": True}
            )
        ], className="mb-4 p-3 bg-light border rounded"),
        
        # 단면 설정
        html.Div([
            html.Label("단면 위치 설정", className="d-block mb-2 fw-bold"),
            dbc.Row([
                dbc.Col([
                    html.Label("X축 위치", className="d-block mb-1"),
                    dcc.Slider(id="section-x-input", min=0, max=1, step=0.01, value=0.5)
                ], width=4),
                dbc.Col([
                    html.Label("Y축 위치", className="d-block mb-1"),
                    dcc.Slider(id="section-y-input", min=0, max=1, step=0.01, value=0.5)
                ], width=4),
                dbc.Col([
                    html.Label("Z축 위치", className="d-block mb-1"),
                    dcc.Slider(id="section-z-input", min=0, max=1, step=0.01, value=0.5)
                ], width=4)
            ])
        ], className="p-3 bg-light border rounded mb-4"),
        
        # 단면 뷰어들
        dbc.Row([
            dbc.Col([
                dcc.Graph(id="viewer-3d-section", style={"height": "40vh"})
            ], width=6),
            dbc.Col([
                dcc.Graph(id="viewer-section-x", style={"height": "40vh"})
            ], width=6)
        ], className="mb-3"),
        dbc.Row([
            dbc.Col([
                dcc.Graph(id="viewer-section-y", style={"height": "40vh"})
            ], width=6),
            dbc.Col([
                dcc.Graph(id="viewer-section-z", style={"height": "40vh"})
            ], width=6)
        ])
    ])

def create_node_tab_content(concrete_pk):
    """노드별 탭 콘텐츠를 생성합니다."""
    return html.Div([
        # 노드 선택
        html.Div([
            html.Label("노드 선택", className="d-block mb-2 fw-bold"),
            dcc.Dropdown(
                id="node-selection-dropdown",
                placeholder="노드를 선택하세요...",
                className="mb-3"
            )
        ], className="p-3 bg-light border rounded mb-4"),
        
        # 노드별 응력 그래프
        html.Div([
            html.Label("노드별 응력 변화", className="d-block mb-2 fw-bold"),
            dcc.Graph(id="node-stress-graph", style={"height": "50vh"})
        ], className="mb-4"),
        
        # 노드별 변위 그래프
        html.Div([
            html.Label("노드별 변위 변화", className="d-block mb-2 fw-bold"),
            dcc.Graph(id="node-displacement-graph", style={"height": "50vh"})
        ])
    ])

@callback(
    Output("stress-analysis-3d-viewer", "children"),
    Output("stress-analysis-current-file-label", "children"),
    Output("time-slider-stress", "min", allow_duplicate=True),
    Output("time-slider-stress", "max", allow_duplicate=True),
    Output("time-slider-stress", "value", allow_duplicate=True),
    Output("time-slider-stress", "marks", allow_duplicate=True),
    Output("stress-data-store", "data"),
    Input("project-url", "pathname"),
    Input("tabs-main", "active_tab"),
    Input("time-slider-stress", "value"),
    State("tbl-concrete-stress", "selected_rows"),
    State("tbl-concrete-stress", "data"),
    prevent_initial_call=True
)
def update_stress_3d_view_stress(pathname, active_tab, time_idx, selected_rows, tbl_data):
    """3D 응력 뷰어를 업데이트합니다."""
    # 응력 분석 페이지에서만 실행
    if '/stress' not in pathname:
        raise PreventUpdate
    
    # 3D 탭이 활성화되지 않았으면 실행하지 않음
    if active_tab != "tab-3d":
        raise PreventUpdate
    
    if not selected_rows or not tbl_data:
        return html.Div("콘크리트를 선택하세요."), "", 0, 1, 0, {}, None
    
    row = pd.DataFrame(tbl_data).iloc[selected_rows[0]]
    concrete_pk = row["concrete_pk"]
    frd_dir = f"frd/{concrete_pk}"
    
    if not os.path.exists(frd_dir):
        return html.Div("FRD 파일이 없습니다."), "", 0, 1, 0, {}, None
    
    # FRD 파일 목록
    frd_files = sorted(glob.glob(f"{frd_dir}/*.frd"))
    if not frd_files:
        return html.Div("FRD 파일이 없습니다."), "", 0, 1, 0, {}, None
    
    # 시간 인덱스 처리
    max_idx = len(frd_files) - 1
    idx = min(int(time_idx) if time_idx is not None else max_idx, max_idx)
    selected_file = frd_files[idx]
    
    try:
        # FRD 파일 파싱
        nodes, elements, stresses, displacements = parse_frd_file(selected_file)
        
        if not nodes or not elements:
            return html.Div("FRD 파일 파싱에 실패했습니다."), "", 0, 1, 0, {}, None
        
        # 응력 데이터 준비 (기본값: von Mises 응력)
        field_name = "von_mises"  # 기본값
        preset = "rainbow"  # 기본값
        
        stress_data = []
        for node_id, coords in nodes.items():
            if node_id in stresses:
                stress_tensor = stresses[node_id]
                if field_name == "von_mises":
                    value = calculate_von_mises_stress(stress_tensor)
                elif field_name == "sxx":
                    value = stress_tensor[0]
                elif field_name == "syy":
                    value = stress_tensor[1]
                elif field_name == "szz":
                    value = stress_tensor[2]
                elif field_name == "sxy":
                    value = stress_tensor[3]
                elif field_name == "syz":
                    value = stress_tensor[4]
                elif field_name == "szx":
                    value = stress_tensor[5]
                else:
                    value = 0
                
                stress_data.append({
                    'node_id': node_id,
                    'x': coords[0],
                    'y': coords[1],
                    'z': coords[2],
                    'value': value
                })
        
        # 3D 산점도 생성
        if stress_data:
            df = pd.DataFrame(stress_data)
            
            fig = go.Figure(data=[
                go.Scatter3d(
                    x=df['x'],
                    y=df['y'],
                    z=df['z'],
                    mode='markers',
                    marker=dict(
                        size=3,
                        color=df['value'],
                        colorscale=preset,
                        opacity=0.8,
                        colorbar=dict(title=f"{field_name.replace('_', ' ').title()} (MPa)")
                    ),
                    text=[f"노드 {row['node_id']}<br>응력: {row['value']:.2f} MPa" for _, row in df.iterrows()],
                    hovertemplate='%{text}<extra></extra>'
                )
            ])
            
            fig.update_layout(
                title=f"3D 응력 분포 - {field_name.replace('_', ' ').title()}",
                scene=dict(
                    xaxis_title="X (m)",
                    yaxis_title="Y (m)",
                    zaxis_title="Z (m)",
                    aspectmode='data'
                ),
                height=600
            )
            
            # 파일명 표시
            file_name = os.path.basename(selected_file)
            time_str = file_name.split('.')[0]
            try:
                dt = datetime.strptime(time_str, "%Y%m%d%H")
                label = f"📅 {dt.strftime('%Y년 %m월 %d일 %H시')}"
            except:
                label = f"📄 {file_name}"
            
            # 마크 생성
            marks = {i: f"{i+1}" for i in range(len(frd_files))}
            
            # 응력 데이터 저장
            stress_store_data = {
                'nodes': nodes,
                'elements': elements,
                'stresses': stresses,
                'displacements': displacements,
                'stress_data': stress_data
            }
            
            return fig, label, 0, max_idx, idx, marks, stress_store_data
        else:
            return html.Div("응력 데이터가 없습니다."), "", 0, 1, 0, {}, None
            
    except Exception as e:
        print(f"3D 뷰어 업데이트 오류: {e}")
        return html.Div(f"오류가 발생했습니다: {e}"), "", 0, 1, 0, {}, None

# 추가 콜백들...
@callback(
    Output("stress-analysis-3d-viewer", "children", allow_duplicate=True),
    Output("stress-analysis-current-file-label", "children", allow_duplicate=True),
    Input("stress-field-dropdown", "value"),
    Input("stress-preset-dropdown", "value"),
    Input("slice-enable", "value"),
    Input("slice-axis", "value"),
    Input("slice-slider", "value"),
    Input("project-url", "pathname"),
    State("tbl-concrete-stress", "selected_rows"),
    State("tbl-concrete-stress", "data"),
    State("time-slider-stress", "value"),
    prevent_initial_call=True
)
def update_stress_3d_view_with_options_stress(field_name, preset, slice_enable, slice_axis, slice_slider, pathname, selected_rows, tbl_data, time_idx):
    """드롭다운 옵션 변경 시 3D 뷰어를 업데이트합니다."""
    # 응력 분석 페이지에서만 실행
    if '/stress' not in pathname:
        raise PreventUpdate
    
    if not selected_rows or not tbl_data:
        raise PreventUpdate
    
    row = pd.DataFrame(tbl_data).iloc[selected_rows[0]]
    concrete_pk = row["concrete_pk"]
    frd_dir = f"frd/{concrete_pk}"
    
    if not os.path.exists(frd_dir):
        raise PreventUpdate
    
    frd_files = sorted(glob.glob(f"{frd_dir}/*.frd"))
    if not frd_files:
        raise PreventUpdate
    
    # 시간 인덱스 처리
    max_idx = len(frd_files) - 1
    idx = min(int(time_idx) if time_idx is not None else max_idx, max_idx)
    selected_file = frd_files[idx]
    
    try:
        # FRD 파일 파싱
        nodes, elements, stresses, displacements = parse_frd_file(selected_file)
        
        if not nodes or not elements:
            raise PreventUpdate
        
        # 응력 데이터 준비
        stress_data = []
        for node_id, coords in nodes.items():
            if node_id in stresses:
                stress_tensor = stresses[node_id]
                if field_name == "von_mises":
                    value = calculate_von_mises_stress(stress_tensor)
                elif field_name == "sxx":
                    value = stress_tensor[0]
                elif field_name == "syy":
                    value = stress_tensor[1]
                elif field_name == "szz":
                    value = stress_tensor[2]
                elif field_name == "sxy":
                    value = stress_tensor[3]
                elif field_name == "syz":
                    value = stress_tensor[4]
                elif field_name == "szx":
                    value = stress_tensor[5]
                else:
                    value = 0
                
                stress_data.append({
                    'node_id': node_id,
                    'x': coords[0],
                    'y': coords[1],
                    'z': coords[2],
                    'value': value
                })
        
        # 3D 산점도 생성
        if stress_data:
            df = pd.DataFrame(stress_data)
            
            fig = go.Figure(data=[
                go.Scatter3d(
                    x=df['x'],
                    y=df['y'],
                    z=df['z'],
                    mode='markers',
                    marker=dict(
                        size=3,
                        color=df['value'],
                        colorscale=preset,
                        opacity=0.8,
                        colorbar=dict(title=f"{field_name.replace('_', ' ').title()} (MPa)")
                    ),
                    text=[f"노드 {row['node_id']}<br>응력: {row['value']:.2f} MPa" for _, row in df.iterrows()],
                    hovertemplate='%{text}<extra></extra>'
                )
            ])
            
            fig.update_layout(
                title=f"3D 응력 분포 - {field_name.replace('_', ' ').title()}",
                scene=dict(
                    xaxis_title="X (m)",
                    yaxis_title="Y (m)",
                    zaxis_title="Z (m)",
                    aspectmode='data'
                ),
                height=600
            )
            
            # 파일명 표시
            file_name = os.path.basename(selected_file)
            time_str = file_name.split('.')[0]
            try:
                dt = datetime.strptime(time_str, "%Y%m%d%H")
                label = f"📅 {dt.strftime('%Y년 %m월 %d일 %H시')}"
            except:
                label = f"📄 {file_name}"
            
            return fig, label
        else:
            raise PreventUpdate
            
    except Exception as e:
        print(f"3D 뷰어 업데이트 오류: {e}")
        raise PreventUpdate

@callback(
    Output("slice-detail-controls", "style"),
    Input("slice-enable", "value"),
    Input("project-url", "pathname"),
    prevent_initial_call=True
)
def toggle_slice_controls_stress(slice_enable, pathname):
    """단면 보기 컨트롤을 토글합니다."""
    # 응력 분석 페이지에서만 실행
    if '/stress' not in pathname:
        raise PreventUpdate
    
    if slice_enable and "on" in slice_enable:
        return {"display": "block"}
    else:
        return {"display": "none"}

@callback(
    Output("node-selection-dropdown", "options"),
    Output("node-selection-dropdown", "value"),
    Input("stress-data-store", "data"),
    Input("project-url", "pathname"),
    prevent_initial_call=True
)
def update_node_selection_stress(stress_data, pathname):
    """노드 선택 드롭다운을 업데이트합니다."""
    # 응력 분석 페이지에서만 실행
    if '/stress' not in pathname:
        raise PreventUpdate
    
    if not stress_data or 'nodes' not in stress_data:
        return [], None
    
    nodes = stress_data['nodes']
    options = [{"label": f"노드 {node_id}", "value": node_id} for node_id in sorted(nodes.keys())]
    return options, None

@callback(
    Output("node-stress-graph", "figure"),
    Output("node-displacement-graph", "figure"),
    Input("node-selection-dropdown", "value"),
    Input("project-url", "pathname"),
    State("stress-data-store", "data"),
    prevent_initial_call=True
)
def update_node_graphs_stress(selected_node, pathname, stress_data):
    """노드별 응력 및 변위 그래프를 업데이트합니다."""
    # 응력 분석 페이지에서만 실행
    if '/stress' not in pathname:
        raise PreventUpdate
    
    if not selected_node or not stress_data:
        return go.Figure(), go.Figure()
    
    nodes = stress_data.get('nodes', {})
    stresses = stress_data.get('stresses', {})
    displacements = stress_data.get('displacements', {})
    
    if selected_node not in nodes:
        return go.Figure(), go.Figure()
    
    # 응력 그래프
    if selected_node in stresses:
        stress_tensor = stresses[selected_node]
        stress_fig = go.Figure(data=[
            go.Bar(
                x=['SXX', 'SYY', 'SZZ', 'SXY', 'SYZ', 'SZX'],
                y=stress_tensor,
                marker_color='lightcoral'
            )
        ])
        stress_fig.update_layout(
            title=f"노드 {selected_node} 응력 성분",
            yaxis_title="응력 (MPa)",
            showlegend=False
        )
    else:
        stress_fig = go.Figure()
    
    # 변위 그래프
    if selected_node in displacements:
        disp_vector = displacements[selected_node]
        disp_fig = go.Figure(data=[
            go.Bar(
                x=['U1', 'U2', 'U3'],
                y=disp_vector,
                marker_color='lightblue'
            )
        ])
        disp_fig.update_layout(
            title=f"노드 {selected_node} 변위 성분",
            yaxis_title="변위 (m)",
            showlegend=False
        )
    else:
        disp_fig = go.Figure()
    
    return stress_fig, disp_fig

@callback(
    Output("viewer-3d-section", "figure", allow_duplicate=True),
    Output("viewer-section-x", "figure", allow_duplicate=True),
    Output("viewer-section-y", "figure", allow_duplicate=True),
    Output("viewer-section-z", "figure", allow_duplicate=True),
    Output("section-x-input", "min", allow_duplicate=True), Output("section-x-input", "max", allow_duplicate=True), Output("section-x-input", "value", allow_duplicate=True),
    Output("section-y-input", "min", allow_duplicate=True), Output("section-y-input", "max", allow_duplicate=True), Output("section-y-input", "value", allow_duplicate=True),
    Output("section-z-input", "min", allow_duplicate=True), Output("section-z-input", "max", allow_duplicate=True), Output("section-z-input", "value", allow_duplicate=True),
    Output("current-file-title-store-stress", "data", allow_duplicate=True),
    Input("project-url", "pathname"),
    Input("tabs-main", "active_tab"),
    Input("time-slider-section-stress", "value"),
    Input("section-x-input", "value"),
    Input("section-y-input", "value"),
    Input("section-z-input", "value"),
    Input("unified-colorbar-section-state-stress", "data"),
    State("tbl-concrete-stress", "selected_rows"),
    State("tbl-concrete-stress", "data"),
    prevent_initial_call=True,
)
def update_section_views_stress(pathname, active_tab, time_idx, x_val, y_val, z_val, unified_colorbar, selected_rows, tbl_data):
    """단면 뷰어들을 업데이트합니다."""
    # 응력 분석 페이지에서만 실행
    if '/stress' not in pathname:
        raise PreventUpdate
    
    # 단면 탭이 활성화되지 않았으면 실행하지 않음
    if active_tab != "tab-section":
        raise PreventUpdate
    
    if not selected_rows or not tbl_data:
        return go.Figure(), go.Figure(), go.Figure(), go.Figure(), 0, 1, 0.5, 0, 1, 0.5, 0, 1, 0.5, ""
    
    row = pd.DataFrame(tbl_data).iloc[selected_rows[0]]
    concrete_pk = row["concrete_pk"]
    frd_dir = f"frd/{concrete_pk}"
    
    if not os.path.exists(frd_dir):
        return go.Figure(), go.Figure(), go.Figure(), go.Figure(), 0, 1, 0.5, 0, 1, 0.5, 0, 1, 0.5, ""
    
    frd_files = sorted(glob.glob(f"{frd_dir}/*.frd"))
    if not frd_files:
        return go.Figure(), go.Figure(), go.Figure(), go.Figure(), 0, 1, 0.5, 0, 1, 0.5, 0, 1, 0.5, ""
    
    max_idx = len(frd_files) - 1
    idx = min(int(time_idx) if time_idx is not None else max_idx, max_idx)
    selected_file = frd_files[idx]
    
    try:
        nodes, elements, stresses, displacements = parse_frd_file(selected_file)
        
        if not nodes:
            return go.Figure(), go.Figure(), go.Figure(), go.Figure(), 0, 1, 0.5, 0, 1, 0.5, 0, 1, 0.5, ""
        
        # 좌표 범위 계산
        coords = list(nodes.values())
        x_coords = [c[0] for c in coords]
        y_coords = [c[1] for c in coords]
        z_coords = [c[2] for c in coords]
        
        x_min, x_max = min(x_coords), max(x_coords)
        y_min, y_max = min(y_coords), max(y_coords)
        z_min, z_max = min(z_coords), max(z_coords)
        
        # 응력 데이터 준비
        stress_data = []
        for node_id, coords in nodes.items():
            if node_id in stresses:
                stress_tensor = stresses[node_id]
                von_mises = calculate_von_mises_stress(stress_tensor)
                stress_data.append({
                    'node_id': node_id,
                    'x': coords[0],
                    'y': coords[1],
                    'z': coords[2],
                    'value': von_mises
                })
        
        if not stress_data:
            return go.Figure(), go.Figure(), go.Figure(), go.Figure(), x_min, x_max, x_val, y_min, y_max, y_val, z_min, z_max, z_val, ""
        
        df = pd.DataFrame(stress_data)
        
        # 3D 단면도
        fig_3d = go.Figure(data=[
            go.Scatter3d(
                x=df['x'],
                y=df['y'],
                z=df['z'],
                mode='markers',
                marker=dict(
                    size=3,
                    color=df['value'],
                    colorscale='rainbow',
                    opacity=0.8,
                    colorbar=dict(title="von Mises 응력 (MPa)")
                ),
                text=[f"노드 {row['node_id']}<br>응력: {row['value']:.2f} MPa" for _, row in df.iterrows()],
                hovertemplate='%{text}<extra></extra>'
            )
        ])
        
        fig_3d.update_layout(
            title="3D 응력 분포 (단면)",
            scene=dict(
                xaxis_title="X (m)",
                yaxis_title="Y (m)",
                zaxis_title="Z (m)",
                aspectmode='data'
            ),
            height=400
        )
        
        # X축 단면도
        x_filtered = df[abs(df['x'] - x_val * (x_max - x_min) - x_min) < 0.01]
        fig_x = go.Figure(data=[
            go.Scatter(
                x=x_filtered['y'],
                y=x_filtered['z'],
                mode='markers',
                marker=dict(
                    size=5,
                    color=x_filtered['value'],
                    colorscale='rainbow',
                    opacity=0.8,
                    colorbar=dict(title="von Mises 응력 (MPa)")
                ),
                text=[f"노드 {row['node_id']}<br>응력: {row['value']:.2f} MPa" for _, row in x_filtered.iterrows()],
                hovertemplate='%{text}<extra></extra>'
            )
        ])
        
        fig_x.update_layout(
            title=f"X = {x_val:.2f} 단면",
            xaxis_title="Y (m)",
            yaxis_title="Z (m)",
            height=400
        )
        
        # Y축 단면도
        y_filtered = df[abs(df['y'] - y_val * (y_max - y_min) - y_min) < 0.01]
        fig_y = go.Figure(data=[
            go.Scatter(
                x=y_filtered['x'],
                y=y_filtered['z'],
                mode='markers',
                marker=dict(
                    size=5,
                    color=y_filtered['value'],
                    colorscale='rainbow',
                    opacity=0.8,
                    colorbar=dict(title="von Mises 응력 (MPa)")
                ),
                text=[f"노드 {row['node_id']}<br>응력: {row['value']:.2f} MPa" for _, row in y_filtered.iterrows()],
                hovertemplate='%{text}<extra></extra>'
            )
        ])
        
        fig_y.update_layout(
            title=f"Y = {y_val:.2f} 단면",
            xaxis_title="X (m)",
            yaxis_title="Z (m)",
            height=400
        )
        
        # Z축 단면도
        z_filtered = df[abs(df['z'] - z_val * (z_max - z_min) - z_min) < 0.01]
        fig_z = go.Figure(data=[
            go.Scatter(
                x=z_filtered['x'],
                y=z_filtered['y'],
                mode='markers',
                marker=dict(
                    size=5,
                    color=z_filtered['value'],
                    colorscale='rainbow',
                    opacity=0.8,
                    colorbar=dict(title="von Mises 응력 (MPa)")
                ),
                text=[f"노드 {row['node_id']}<br>응력: {row['value']:.2f} MPa" for _, row in z_filtered.iterrows()],
                hovertemplate='%{text}<extra></extra>'
            )
        ])
        
        fig_z.update_layout(
            title=f"Z = {z_val:.2f} 단면",
            xaxis_title="X (m)",
            yaxis_title="Y (m)",
            height=400
        )
        
        # 파일명 표시
        file_name = os.path.basename(selected_file)
        time_str = file_name.split('.')[0]
        try:
            dt = datetime.strptime(time_str, "%Y%m%d%H")
            label = f"📅 {dt.strftime('%Y년 %m월 %d일 %H시')}"
        except:
            label = f"📄 {file_name}"
        
        return fig_3d, fig_x, fig_y, fig_z, x_min, x_max, x_val, y_min, y_max, y_val, z_min, z_max, z_val, label
        
    except Exception as e:
        print(f"단면 뷰어 업데이트 오류: {e}")
        return go.Figure(), go.Figure(), go.Figure(), go.Figure(), 0, 1, 0.5, 0, 1, 0.5, 0, 1, 0.5, ""

@callback(
    Output("time-slider-section-stress", "min", allow_duplicate=True),
    Output("time-slider-section-stress", "max", allow_duplicate=True), 
    Output("time-slider-section-stress", "value", allow_duplicate=True),
    Output("time-slider-section-stress", "marks", allow_duplicate=True),
    Input("project-url", "pathname"),
    Input("tabs-main", "active_tab"),
    Input("tbl-concrete-stress", "selected_rows"),
    State("tbl-concrete-stress", "data"),
    prevent_initial_call=True,
)
def init_section_slider_independent_stress(pathname, active_tab, selected_rows, tbl_data):
    """단면 탭용 독립 슬라이더를 초기화합니다."""
    # 응력 분석 페이지에서만 실행
    if '/stress' not in pathname:
        raise PreventUpdate
    
    if active_tab != "tab-section" or not selected_rows or not tbl_data:
        return 0, 1, 0, {}
    
    row = pd.DataFrame(tbl_data).iloc[selected_rows[0]]
    concrete_pk = row["concrete_pk"]
    frd_dir = f"frd/{concrete_pk}"
    
    if not os.path.exists(frd_dir):
        return 0, 1, 0, {}
    
    frd_files = sorted(glob.glob(f"{frd_dir}/*.frd"))
    if not frd_files:
        return 0, 1, 0, {}
    
    max_idx = len(frd_files) - 1
    marks = {i: f"{i+1}" for i in range(len(frd_files))}
    
    return 0, max_idx, max_idx, marks

@callback(
    Output("btn-concrete-analyze-stress", "disabled", allow_duplicate=True),
    Output("btn-concrete-del-stress", "disabled", allow_duplicate=True),
    Output("current-file-title-store-stress", "data", allow_duplicate=True),
    Output("time-slider-stress", "min", allow_duplicate=True),
    Output("time-slider-stress", "max", allow_duplicate=True),
    Output("time-slider-stress", "value", allow_duplicate=True),
    Output("time-slider-stress", "marks", allow_duplicate=True),
    Input("project-url", "pathname"),
    Input("tbl-concrete-stress", "selected_rows"),
    State("tbl-concrete-stress", "data"),
    prevent_initial_call=True,
)
def on_concrete_select_stress(pathname, selected_rows, tbl_data):
    """콘크리트 선택 시 슬라이더를 초기화합니다."""
    # 응력 분석 페이지에서만 실행
    if '/stress' not in pathname:
        raise PreventUpdate
    
    if not selected_rows or not tbl_data:
        return False, False, "", 0, 1, 0, {}
    
    row = pd.DataFrame(tbl_data).iloc[selected_rows[0]]
    concrete_pk = row["concrete_pk"]
    frd_dir = f"frd/{concrete_pk}"
    
    if not os.path.exists(frd_dir):
        return False, False, "", 0, 1, 0, {}
    
    frd_files = sorted(glob.glob(f"{frd_dir}/*.frd"))
    if not frd_files:
        return False, False, "", 0, 1, 0, {}
    
    max_idx = len(frd_files) - 1
    marks = {i: f"{i+1}" for i in range(len(frd_files))}
    
    return False, False, "", 0, max_idx, max_idx, marks

@callback(
    Output("stress-project-alert", "children", allow_duplicate=True),
    Output("stress-project-alert", "color", allow_duplicate=True),
    Output("stress-project-alert", "is_open", allow_duplicate=True),
    Output("tbl-concrete-stress", "data", allow_duplicate=True),
    Input("project-url", "pathname"),
    Input("btn-concrete-analyze-stress", "n_clicks"),
    State("tbl-concrete-stress", "selected_rows"),
    State("tbl-concrete-stress", "data"),
    prevent_initial_call=True,
)
def start_analysis_stress(pathname, n_clicks, selected_rows, tbl_data):
    """응력 분석을 시작합니다."""
    # 응력 분석 페이지에서만 실행
    if '/stress' not in pathname:
        raise PreventUpdate
    
    if not n_clicks or not selected_rows or not tbl_data:
        raise PreventUpdate
    
    row = pd.DataFrame(tbl_data).iloc[selected_rows[0]]
    concrete_pk = row["concrete_pk"]
    
    try:
        # FRD 파일이 있는지 확인
        frd_dir = f"frd/{concrete_pk}"
        if not os.path.exists(frd_dir):
            return "FRD 파일이 없습니다.", "warning", True, tbl_data
        
        frd_files = glob.glob(f"{frd_dir}/*.frd")
        if not frd_files:
            return "FRD 파일이 없습니다.", "warning", True, tbl_data
        
        # 상태 업데이트
        updated_data = tbl_data.copy()
        updated_data[selected_rows[0]]["status"] = "응력 분석 완료"
        
        return f"응력 분석이 완료되었습니다. ({len(frd_files)}개 파일)", "success", True, updated_data
        
    except Exception as e:
        return f"응력 분석 중 오류가 발생했습니다: {e}", "danger", True, tbl_data

@callback(
    Output("confirm-del-concrete-stress", "displayed", allow_duplicate=True),
    Input("btn-concrete-del-stress", "n_clicks"),
    Input("project-url", "pathname"),
    State("tbl-concrete-stress", "selected_rows"),
    prevent_initial_call=True
)
def ask_delete_concrete_stress(n, pathname, sel):
    """콘크리트 삭제 확인 다이얼로그를 표시합니다."""
    # 응력 분석 페이지에서만 실행
    if '/stress' not in pathname:
        raise PreventUpdate
    
    if n and sel:
        return True
    return False

@callback(
    Output("stress-project-alert", "children", allow_duplicate=True),
    Output("stress-project-alert", "color", allow_duplicate=True),
    Output("stress-project-alert", "is_open", allow_duplicate=True),
    Output("tbl-concrete-stress", "data", allow_duplicate=True),
    Input("confirm-del-concrete-stress", "submit_n_clicks"),
    Input("project-url", "pathname"),
    State("tbl-concrete-stress", "selected_rows"),
    State("tbl-concrete-stress", "data"),
    prevent_initial_call=True,
)
def delete_concrete_confirm_stress(_click, pathname, sel, tbl_data):
    """콘크리트 삭제를 확인합니다."""
    # 응력 분석 페이지에서만 실행
    if '/stress' not in pathname:
        raise PreventUpdate
    
    if not _click or not sel or not tbl_data:
        raise PreventUpdate
    
    try:
        # 선택된 콘크리트 정보
        row = pd.DataFrame(tbl_data).iloc[sel[0]]
        concrete_pk = row["concrete_pk"]
        
        # FRD 파일 삭제
        frd_dir = f"frd/{concrete_pk}"
        if os.path.exists(frd_dir):
            shutil.rmtree(frd_dir)
        
        # 목록에서 제거
        updated_data = [item for i, item in enumerate(tbl_data) if i not in sel]
        
        return f"콘크리트 '{row['name']}'이(가) 삭제되었습니다.", "success", True, updated_data
        
    except Exception as e:
        return f"삭제 중 오류가 발생했습니다: {e}", "danger", True, tbl_data
