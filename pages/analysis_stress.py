#!/usr/bin/env python3
# pages/analysis_stress.py
# 응력 분석 페이지: 간단한 콘크리트 목록 표시

from __future__ import annotations

import os
import glob
import pandas as pd
import numpy as np
from datetime import datetime
import dash
from dash import (
    html, dcc, Input, Output, State,
    dash_table, register_page, callback
)
import dash_bootstrap_components as dbc
from dash.exceptions import PreventUpdate

import api_db
from utils.encryption import parse_project_key_from_url

register_page(__name__, path="/stress", title="응력 분석")

# ────────────────────────────── 레이아웃 ────────────────────────────
layout = dbc.Container(
    fluid=True,
    className="px-4 py-3",
    style={"backgroundColor": "#f7f9fc", "minHeight": "100vh"},
    children=[
        dcc.Location(id="project-url", refresh=False),
        
        # ── 데이터 저장용 Store들
        dcc.Store(id="project-info-store-stress", data=None),
        
        # 메인 콘텐츠 영역
        dbc.Row([
            # 왼쪽 사이드바 - 콘크리트 목록
            dbc.Col([
                html.Div([
                    # 프로젝트 안내 박스
                    dbc.Alert(id="current-project-info-stress", color="info", className="mb-3 py-2"),
                    
                    # 콘크리트 목록 섹션
                    html.Div([
                        html.Div([
                            # 제목
                            html.Div([
                                html.H6("🧱 콘크리트 목록", className="mb-0 text-secondary fw-bold"),
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
                                                'filter_query': '{status} = 응력 분석 가능',
                                                'column_id': 'status'
                                            },
                                            'backgroundColor': '#e8f5e8',
                                            'color': '#2e7d32',
                                            'fontWeight': 'bold'
                                        },
                                        {
                                            'if': {
                                                'filter_query': '{status} = FRD 파일 없음',
                                                'column_id': 'status'
                                            },
                                            'backgroundColor': '#fff3e0',
                                            'color': '#f57c00',
                                            'fontWeight': 'bold'
                                        },
                                        {
                                            'if': {
                                                'filter_query': '{status} = 비활성',
                                                'column_id': 'status'
                                            },
                                            'backgroundColor': '#f5f5f5',
                                            'color': '#6c757d',
                                            'fontWeight': 'bold'
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
            ], md=6),
            
                        # 오른쪽 메인 콘텐츠 영역
            dbc.Col([
                html.Div([
                    # 탭 메뉴 (노션 스타일)
                    html.Div([
                        dbc.Tabs([
                            dbc.Tab(
                                label="입체", 
                                tab_id="tab-3d-stress",
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
                                tab_id="tab-section-stress",
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
                                tab_id="tab-node-stress",
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
                        ], id="tabs-main-stress", active_tab="tab-3d-stress", className="mb-0")
                    ], style={
                        "backgroundColor": "#f8fafc",
                        "padding": "8px 8px 0 8px",
                        "borderRadius": "8px 8px 0 0",
                        "border": "1px solid #e2e8f0",
                        "borderBottom": "none"
                    }),
                    
                    # 탭 콘텐츠 영역
                    html.Div(id="tab-content-stress", style={
                        "backgroundColor": "white",
                        "border": "1px solid #e2e8f0",
                        "borderTop": "none",
                        "borderRadius": "0 0 8px 8px",
                        "padding": "20px",
                        "minHeight": "calc(100vh - 200px)"
                    })
                ])
            ], md=6)
        ], className="g-4")
    ]
)

# ───────────────────── 콜백 함수들 ─────────────────────

@callback(
    Output("tbl-concrete-stress", "data"),
    Output("tbl-concrete-stress", "columns"),
    Output("tbl-concrete-stress", "selected_rows"),
    Output("tbl-concrete-stress", "style_data_conditional"),
    Output("project-info-store-stress", "data"),
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
            print(f"DEBUG: 프로젝트 키 파싱 오류: {e}")
            pass
    
    if not project_pk:
        return [], [], [], [], None
    
    try:
        # 프로젝트 정보 로드
        df_proj = api_db.get_project_data(project_pk=project_pk)
        if df_proj.empty:
            return [], [], [], [], None
            
        proj_row = df_proj.iloc[0]
        proj_name = proj_row["name"]
        
        # 해당 프로젝트의 콘크리트 데이터 로드
        df_conc = api_db.get_concrete_data(project_pk=project_pk)
        if df_conc.empty:
            return [], [], [], [], {"name": proj_name, "pk": project_pk}
        
    except Exception as e:
        return [], [], [], [], None
    
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
                status = "설정중"
                status_sort = 2  # 두 번째 우선순위
            else:
                status = "설정중"
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

    # 테이블 컬럼 정의
    columns = [
        {"name": "이름", "id": "name", "type": "text"},
        {"name": "타설일(경과일)", "id": "pour_date", "type": "text"},
        {"name": "상태", "id": "status", "type": "text"},
    ]
    
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
        # 설정중 상태 (회색)
        {
            'if': {
                'filter_query': '{status} = "설정중"',
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
    
    # 상태별 기본 정렬 적용 (분석중 → 설정중)
    if table_data:
        table_data = sorted(table_data, key=lambda x: x.get('status_sort', 999))
    
    return table_data, columns, [], style_data_conditional, {"name": proj_name, "pk": project_pk}

@callback(
    Output("current-project-info-stress", "children"),
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
    
    return f"📁 현재 프로젝트: {project_info['name']}"

@callback(
    Output("tab-content-stress", "children"),
    Input("tabs-main-stress", "active_tab"),
    Input("tbl-concrete-stress", "selected_rows"),
    Input("project-url", "pathname"),
    State("tbl-concrete-stress", "data"),
    prevent_initial_call=True,
)
def switch_tab_stress(active_tab, selected_rows, pathname, tbl_data):
    """탭 전환 시 해당 탭의 콘텐츠를 표시합니다."""
    # 응력 분석 페이지에서만 실행
    if '/stress' not in pathname:
        raise PreventUpdate
    
    if not selected_rows or not tbl_data:
        return html.Div("콘크리트를 선택하세요.", className="text-center text-muted mt-5")
    
    row = pd.DataFrame(tbl_data).iloc[selected_rows[0]]
    concrete_pk = row["concrete_pk"]
    
    if active_tab == "tab-3d-stress":
        return create_3d_tab_content_stress(concrete_pk)
    elif active_tab == "tab-section-stress":
        return create_section_tab_content_stress(concrete_pk)
    elif active_tab == "tab-node-stress":
        return create_node_tab_content_stress(concrete_pk)
    else:
        return html.Div("알 수 없는 탭입니다.", className="text-center text-muted mt-5")

def create_3d_tab_content_stress(concrete_pk):
    """입체 탭 콘텐츠를 생성합니다."""
    return html.Div([
        html.H4("3D 응력 분석", className="mb-3"),
        html.P("3D 응력 분석 기능이 여기에 표시됩니다.", className="text-muted")
    ])

def create_section_tab_content_stress(concrete_pk):
    """단면 탭 콘텐츠를 생성합니다."""
    return html.Div([
        html.H4("단면 응력 분석", className="mb-3"),
        html.P("단면 응력 분석 기능이 여기에 표시됩니다.", className="text-muted")
    ])

def create_node_tab_content_stress(concrete_pk):
    """노드별 탭 콘텐츠를 생성합니다."""
    return html.Div([
        html.H4("노드별 응력 분석", className="mb-3"),
        html.P("노드별 응력 분석 기능이 여기에 표시됩니다.", className="text-muted")
    ])
