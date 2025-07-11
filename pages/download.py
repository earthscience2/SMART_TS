#!/usr/bin/env python3
# pages/download.py
"""Dash 페이지: 파일 다운로드 (inp, frd, vtk)
프로젝트 선택 → 콘크리트 선택 → 파일 유형 탭에서 시간별 그룹핑된 파일 선택 후 다운로드
"""

from __future__ import annotations

import os, glob, io, zipfile
import pandas as pd
from datetime import datetime, timedelta
from collections import defaultdict

import dash
from dash import html, dcc, Input, Output, State, dash_table, register_page
import dash_bootstrap_components as dbc
from dash.exceptions import PreventUpdate

import api_db
from utils.encryption import parse_project_key_from_url
from flask import request as flask_request

register_page(__name__, path="/download", title="파일 다운로드")

# 프로젝트 메타데이터는 콜백에서 동적으로 가져옵니다

def parse_filename_datetime(filename):
    """파일명에서 날짜시간 추출 (YYYYMMDD, YYYYMMDDHH, YYYYMMDDHHMM 형식)"""
    try:
        base_name = filename.split('.')[0]
        # 숫자만으로 구성되고 8자리 이상인 경우 처리
        if base_name.isdigit() and len(base_name) >= 8:
            year = int(base_name[:4])
            month = int(base_name[4:6])
            day = int(base_name[6:8])
            
            # 시간과 분이 있는 경우 (YYYYMMDDHHMM)
            if len(base_name) >= 12:
                hour = int(base_name[8:10])
                minute = int(base_name[10:12])
            # 시간만 있는 경우 (YYYYMMDDHH)
            elif len(base_name) == 10:
                hour = int(base_name[8:10])
                minute = 0
            # 날짜만 있는 경우 (YYYYMMDD)
            elif len(base_name) == 8:
                hour = 0
                minute = 0
            else:
                hour = 0
                minute = 0
                
            return datetime(year, month, day, hour, minute)
    except Exception as e:
        print(f"파일명 파싱 오류 ({filename}): {e}")  # 디버깅용
    return None

def format_file_size(size_bytes):
    """파일 크기를 읽기 쉬운 형태로 변환"""
    if size_bytes == 0:
        return "0B"
    size_names = ["B", "KB", "MB", "GB"]
    i = 0
    while size_bytes >= 1024 and i < len(size_names) - 1:
        size_bytes /= 1024
        i += 1
    return f"{size_bytes:.1f}{size_names[i]}"

def get_file_info_grouped(folder, ext):
    """폴더에서 파일 정보를 가져와 날짜별로 그룹핑"""
    if not os.path.exists(folder):
        return {}
    
    files = [f for f in os.listdir(folder) if f.endswith(ext)]
    grouped_files = defaultdict(list)
    
    for filename in files:
        filepath = os.path.join(folder, filename)
        file_stat = os.stat(filepath)
        file_size = format_file_size(file_stat.st_size)
        
        # 파일명에서 날짜시간 추출
        dt = parse_filename_datetime(filename)
        if dt:
            date_key = dt.strftime("%Y-%m-%d")
            time_str = dt.strftime("%H:%M")
            
            grouped_files[date_key].append({
                "filename": filename,
                "datetime": dt,
                "time_str": time_str,
                "size": file_size,
                "size_bytes": file_stat.st_size
            })
        else:
            # 날짜를 파싱할 수 없는 파일은 "기타"로 분류
            grouped_files["기타"].append({
                "filename": filename,
                "datetime": None,
                "time_str": "N/A",
                "size": file_size,
                "size_bytes": file_stat.st_size
            })
    
    # 각 날짜별로 시간순 정렬 (최신 순)
    for date_key in grouped_files:
        if date_key != "기타":
            grouped_files[date_key].sort(key=lambda x: x["datetime"], reverse=True)
    
    return dict(grouped_files)

# ────────────────────────────── 레이아웃 ────────────────────────────
layout = html.Div([
    dcc.Location(id="download-url", refresh=False),
    dcc.Store(id="selected-project-store"),
    dcc.Store(id="file-data-store"),  # 파일 데이터 저장용

    dbc.Container(
        fluid=True,
        className="px-4 py-3",
        style={"backgroundColor": "#f7f9fc", "minHeight": "100vh"},
        children=[
            dbc.Alert(id="download-alert", is_open=False, duration=3000, color="info"),
            
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
                                    html.Div()  # 추가 버튼은 다운로드 페이지에서는 필요 없음
                                ], className="d-flex justify-content-between align-items-center mb-2"),
                                html.Small("💡 행을 클릭하여 선택", className="text-muted mb-2 d-block"),
                                html.Div([
                                    dash_table.DataTable(
                                        id="dl-tbl-concrete",
                                        page_size=5,
                                        row_selectable="single",
                                        sort_action="native",
                                        style_cell={
                                            "textAlign": "center",
                                            "fontSize": "0.8rem",
                                            "padding": "8px 6px",
                                            "border": "none",
                                            "borderBottom": "1px solid #e9ecef",
                                            "fontFamily": "'Inter', sans-serif"
                                        },
                                        style_header={
                                            "backgroundColor": "#f8f9fa", 
                                            "fontWeight": 600,
                                            "color": "#495057",
                                            "border": "none",
                                            "borderBottom": "2px solid #dee2e6",
                                            "fontSize": "0.8rem",
                                            "textAlign": "center"
                                        },
                                        style_data={
                                            "backgroundColor": "white",
                                            "border": "none",
                                            "color": "#212529"
                                        },
                                        style_data_conditional=[
                                            {
                                                'if': {'row_index': 'odd'},
                                                'backgroundColor': '#f8f9fa'
                                            },
                                            {
                                                'if': {'state': 'selected'},
                                                'backgroundColor': '#e3f2fd',
                                                'border': '1px solid #2196f3',
                                                'color': '#1565c0',
                                                'fontWeight': '500'
                                            },
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
                                            },
                                            # 타설일(경과일) 컬럼 스타일
                                            {
                                                'if': {'column_id': 'pour_date'},
                                                'fontSize': '0.85rem',
                                                'color': '#6c757d',
                                                'fontWeight': '500'
                                            }
                                        ],
                                        css=[
                                            {
                                                'selector': '.dash-table-container .dash-spreadsheet-container .dash-spreadsheet-inner tr:hover',
                                                'rule': 'background-color: #e8f5e8 !important; transition: all 0.2s ease;'
                                            }
                                        ],
                                        style_table={"borderRadius": "6px", "overflow": "hidden"}
                                    )
                                ], style={
                                    "backgroundColor": "white",
                                    "borderRadius": "8px",
                                    "border": "1px solid #e2e8f0",
                                    "boxShadow": "0 1px 3px rgba(0,0,0,0.1)"
                                })
                            ], style={
                                "backgroundColor": "white",
                                "padding": "20px",
                                "borderRadius": "12px",
                                "border": "1px solid #e2e8f0",
                                "boxShadow": "0 1px 3px rgba(0,0,0,0.1)"
                            })
                        ])
                    ])
                ], md=4),
                
                # 오른쪽 메인 콘텐츠 - 파일 목록 및 다운로드
                dbc.Col([
                    html.Div([
                        # 탭 네비게이션
                        html.Div([
                            dbc.Tabs([
                                dbc.Tab(label="📄 INP 파일", tab_id="tab-inp", 
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
                                dbc.Tab(label="📊 FRD 파일", tab_id="tab-frd",
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
                                dbc.Tab(label="🎯 VTK 파일", tab_id="tab-vtk",
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
                            ], id="dl-tabs", active_tab="tab-inp", className="mb-3"),
                            
                            # 탭 콘텐츠 영역
                            html.Div([
                                # 필터 컨트롤 영역
                                dbc.Card([
                                    dbc.CardBody([
                                        html.H6("🔍 파일 필터링", className="mb-3 text-secondary fw-bold", style={"fontSize": "0.9rem"}),
                                        dbc.Row([
                                            dbc.Col([
                                                html.Label("빠른 필터", className="form-label mb-2", style={"fontSize": "0.8rem", "fontWeight": "600", "color": "#6c757d"}),
                                                dcc.Dropdown(
                                                    id="quick-filter",
                                                    options=[
                                                        {"label": "🕐 오늘", "value": "today"},
                                                        {"label": "📅 최근 3일", "value": "3days"},
                                                        {"label": "📅 최근 7일", "value": "7days"},
                                                        {"label": "📅 최근 30일", "value": "30days"},
                                                        {"label": "📂 전체", "value": "all"}
                                                    ],
                                                    value="all",
                                                    clearable=False,
                                                    style={"fontSize": "0.8rem"}
                                                )
                                            ], md=6),
                                            dbc.Col([
                                                html.Label("날짜 범위", className="form-label mb-1", style={"fontSize": "0.8rem", "fontWeight": "600", "color": "#6c757d"}),
                                                html.Div([
                                                    dcc.DatePickerRange(
                                                        id="date-range-picker",
                                                        start_date=datetime.now() - timedelta(days=365),  # 기본값을 1년으로 확장
                                                        end_date=datetime.now(),
                                                        display_format="YYYY-MM-DD",
                                                        style={
                                                            "fontSize": "0.75rem", 
                                                            "width": "100%"
                                                        }
                                                    )
                                                ], style={
                                                    "fontSize": "0.75rem",
                                                    "lineHeight": "1.2"
                                                })
                                            ], md=6),
                                        ], className="g-2")
                                    ], className="py-2")
                                ], className="mb-3", style={"border": "1px solid #e9ecef"}),
                                
                                # 탭 콘텐츠
                                html.Div(id="dl-tab-content", children=[
                                    html.Div([
                                        html.Div([
                                            html.I(className="fas fa-info-circle me-2", style={"color": "#6b7280", "fontSize": "1.2rem"}),
                                            html.Span("콘크리트를 선택하면 파일 목록이 표시됩니다", style={"color": "#6b7280", "fontSize": "0.9rem"})
                                        ], className="d-flex align-items-center justify-content-center p-4", style={"backgroundColor": "#f9fafb", "borderRadius": "8px", "border": "1px dashed #d1d5db"})
                                    ])
                                ]),
                            ], style={
                                "backgroundColor": "white",
                                "padding": "20px",
                                "borderRadius": "12px",
                                "border": "1px solid #e2e8f0",
                                "boxShadow": "0 1px 3px rgba(0,0,0,0.1)"
                            })
                        ])
                    ])
                ], md=8),
            ], className="g-3"),
        ]
    )
])

# ───────────────────── ① URL에서 프로젝트 정보 파싱 ─────────────────────
@dash.callback(
    Output("selected-project-store", "data", allow_duplicate=True),
    Output("current-project-info", "children", allow_duplicate=True),
    Input("download-url", "search"),
    prevent_initial_call='initial_duplicate'
)
def parse_url_project(search):
    if not search:
        return None, [
            "프로젝트가 선택되지 않았습니다. ",
            html.A("홈으로 돌아가기", href="/", className="alert-link")
        ]
    
    try:
        # 암호화된 프로젝트 키 파싱
        project_pk = parse_project_key_from_url(search)
        
        if not project_pk:
            return None, [
                "프로젝트가 선택되지 않았습니다. ",
                html.A("홈으로 돌아가기", href="/", className="alert-link")
            ]
        
        # 사용자 정보 가져오기
        user_id = flask_request.cookies.get("login_user")
        
        if not user_id:
            return None, [
                "로그인이 필요합니다. ",
                html.A("로그인 페이지로 이동", href="/login", className="alert-link")
            ]
        
        # 접근 가능한 프로젝트 목록 조회 (ITS1과 ITS2 모두에서)
        result = api_db.get_accessible_projects(user_id, its_num=1)
        
        # ITS1에서 실패하면 ITS2에서 시도
        if result["result"] != "Success":
            result = api_db.get_accessible_projects(user_id, its_num=2)
        
        if result["result"] != "Success":
            return None, [
                f"프로젝트 목록을 가져올 수 없습니다: {result['msg']} ",
                html.A("홈으로 돌아가기", href="/", className="alert-link")
            ]
        
        projects_df = result["projects"]
        if projects_df.empty:
            return None, [
                "접근 가능한 프로젝트가 없습니다. ",
                html.A("홈으로 돌아가기", href="/", className="alert-link")
            ]
        
        # 프로젝트 정보 조회 (project_pk가 문자열일 수 있음)
        project_info = projects_df[projects_df["projectid"] == project_pk]
        if project_info.empty:
            return None, [
                f"프로젝트 ID {project_pk}를 찾을 수 없습니다. ",
                html.A("홈으로 돌아가기", href="/", className="alert-link")
            ]
        
        project_name = project_info.iloc[0]["projectname"]
        return project_pk, f"📁 현재 프로젝트: {project_name}"
        
    except Exception as e:
        return None, [
            f"프로젝트 정보를 읽는 중 오류가 발생했습니다: {str(e)} ",
            html.A("홈으로 돌아가기", href="/", className="alert-link")
        ]

# ───────────────────── ② 프로젝트 정보 → 콘크리트 테이블 ────────────────────
@dash.callback(
    Output("dl-tbl-concrete", "data"),
    Output("dl-tbl-concrete", "columns"),
    Output("dl-tbl-concrete", "selected_rows"),
    Input("selected-project-store", "data"),
    prevent_initial_call=False,
)
def dl_load_concrete_list(project_pk):
    if not project_pk:
        return [], [], []
    
    try:
        # 해당 프로젝트의 콘크리트 데이터 로드
        df_conc = api_db.get_concrete_data(project_pk=project_pk)
        if df_conc.empty:
            return [], [], []
        
        table_data = []
        for _, row in df_conc.iterrows():
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
            
            # 상태 결정 (정렬을 위해 우선순위도 함께 설정)
            if row["activate"] == 1:  # 활성
                status = "설정중"
                status_sort = 2  # 두 번째 우선순위
            else:  # 비활성 (activate == 0)
                status = "분석중"
                status_sort = 1  # 첫 번째 우선순위
            
            table_data.append({
                "concrete_pk": row["concrete_pk"],
                "name": row["name"],
                "status": status,
                "status_sort": status_sort,  # 정렬용 숨겨진 필드
                "pour_date": pour_date_with_elapsed,
            })
        
        # 상태별 기본 정렬 적용 (분석중 → 설정중)
        if table_data:
            table_data = sorted(table_data, key=lambda x: x.get('status_sort', 999))
        
        # 테이블 컬럼 정의 (온도 분석 페이지와 동일)
        columns = [
            {"name": "이름", "id": "name", "type": "text"},
            {"name": "타설일(경과일)", "id": "pour_date", "type": "text"},
            {"name": "상태", "id": "status", "type": "text"},
        ]
        
        return table_data, columns, []
        
    except Exception as e:
        return [], [], []

# ───────────────────── ③ 빠른 필터 업데이트 ────────────────────
@dash.callback(
    Output("date-range-picker", "start_date"),
    Output("date-range-picker", "end_date"),
    Input("quick-filter", "value"),
    prevent_initial_call=True,
)
def update_date_range(filter_value):
    today = datetime.now().date()
    
    if filter_value == "today":
        return today, today
    elif filter_value == "3days":
        return today - timedelta(days=3), today
    elif filter_value == "7days":
        return today - timedelta(days=7), today
    elif filter_value == "30days":
        return today - timedelta(days=30), today
    else:  # "all"
        return datetime(2020, 1, 1).date(), today

# ───────────────────── ④ 파일 데이터 저장 (자동 조회) ────────────────────
@dash.callback(
    Output("file-data-store", "data"),
    Input("dl-tabs", "active_tab"),
    Input("dl-tbl-concrete", "selected_rows"),
    State("dl-tbl-concrete", "data"),
    State("selected-project-store", "data"),
    prevent_initial_call=True,
)
def update_file_data(active_tab, sel_rows, tbl_data, project_pk):
    if not sel_rows or not project_pk:
        return {}
    
    concrete_pk = tbl_data[sel_rows[0]]["concrete_pk"]
    
    if active_tab == "tab-inp":
        folder = f"inp/{concrete_pk}"
        ext = ".inp"
    elif active_tab == "tab-frd":
        folder = f"frd/{concrete_pk}"
        ext = ".frd"
    else:
        folder = f"assets/vtk/{concrete_pk}"
        ext = ".vtk"
    
    grouped_files = get_file_info_grouped(folder, ext)
    return {
        "grouped_files": grouped_files,
        "folder": folder,
        "ext": ext,
        "active_tab": active_tab,
        "concrete_pk": concrete_pk,
        "project_pk": project_pk
    }

# ───────────────────── ⑤ 파일 데이터 변경 → 탭 콘텐츠 업데이트 ────────────────────
@dash.callback(
    Output("dl-tab-content", "children"),
    Input("file-data-store", "data"),
    Input("date-range-picker", "start_date"),
    Input("date-range-picker", "end_date"),
    prevent_initial_call=True,
)
def dl_switch_tab(file_data, start_date, end_date):
    if not file_data or not file_data.get("grouped_files"):
        return html.Div([
            html.Div([
                html.I(className="fas fa-folder-open me-2", style={"color": "#6b7280", "fontSize": "1.2rem"}),
                html.Span("조회된 파일이 없습니다", style={"color": "#6b7280", "fontSize": "0.9rem"})
            ], className="d-flex align-items-center justify-content-center p-4", style={"backgroundColor": "#f9fafb", "borderRadius": "8px", "border": "1px dashed #d1d5db"})
        ])
    
    grouped_files = file_data["grouped_files"]
    active_tab = file_data["active_tab"]
    
    # 날짜 필터링 (ISO 형식 날짜 처리)
    start_dt = None
    end_dt = None
    
    if start_date:
        # ISO 형식 또는 YYYY-MM-DD 형식 모두 처리
        if 'T' in str(start_date):
            start_dt = datetime.fromisoformat(str(start_date)).date()
        else:
            start_dt = datetime.strptime(str(start_date), "%Y-%m-%d").date()
    
    if end_date:
        # ISO 형식 또는 YYYY-MM-DD 형식 모두 처리
        if 'T' in str(end_date):
            end_dt = datetime.fromisoformat(str(end_date)).date()
        else:
            end_dt = datetime.strptime(str(end_date), "%Y-%m-%d").date()
    
    filtered_groups = {}
    total_files = 0
    
    for date_key, files in grouped_files.items():
        if date_key == "기타":
            filtered_groups[date_key] = files
            total_files += len(files)
        else:
            date_obj = datetime.strptime(date_key, "%Y-%m-%d").date()
            if (not start_dt or date_obj >= start_dt) and (not end_dt or date_obj <= end_dt):
                filtered_groups[date_key] = files
                total_files += len(files)
    
    if not filtered_groups:
        return html.Div([
            html.Div([
                html.I(className="fas fa-calendar-times me-2", style={"color": "#6b7280", "fontSize": "1.2rem"}),
                html.Span("선택한 날짜 범위에 해당하는 파일이 없습니다", style={"color": "#6b7280", "fontSize": "0.9rem"})
            ], className="d-flex align-items-center justify-content-center p-4", style={"backgroundColor": "#f9fafb", "borderRadius": "8px", "border": "1px dashed #d1d5db"})
        ])
    
    # 날짜별로 정렬 (최신 날짜 먼저)
    sorted_dates = sorted([k for k in filtered_groups.keys() if k != "기타"], reverse=True)
    if "기타" in filtered_groups:
        sorted_dates.append("기타")
    
    content = []
    
    # 전체 통계
    content.append(
        html.Div([
            html.Span(f"📊 총 {total_files}개 파일", className="badge bg-info me-2", style={"fontSize": "0.8rem"}),
            html.Span(f"📅 {len([k for k in filtered_groups.keys() if k != '기타'])}일간", className="badge bg-secondary", style={"fontSize": "0.8rem"})
        ], className="mb-3")
    )
    
    # 전체 제어 버튼
    content.append(
        dbc.Card([
            dbc.CardBody([
                html.Div([
                    html.Div([
                        dbc.Button("📋 모든 파일 선택", 
                                 id={"type": "select-all-btn", "index": active_tab}, 
                                 color="outline-primary", 
                                 size="sm", 
                                 className="me-2",
                                 style={"fontSize": "0.8rem"},
                                 n_clicks=0),
                        dbc.Button("🗑️ 선택 해제", 
                                 id={"type": "deselect-all-btn", "index": active_tab}, 
                                 color="outline-secondary", 
                                 size="sm", 
                                 className="me-2",
                                 style={"fontSize": "0.8rem"},
                                 n_clicks=0),
                    ], className="d-flex"),
                    dbc.Button("📥 선택한 파일 다운로드", 
                             id=f"btn-dl-{active_tab.split('-')[1]}", 
                             color="success", 
                             size="sm",
                             style={"fontSize": "0.8rem", "fontWeight": "600"},
                             n_clicks=0,
                             disabled=False),
                    dcc.Download(id=f"dl-{active_tab.split('-')[1]}-download")
                ], className="d-flex justify-content-between align-items-center")
            ], className="py-2")
        ], className="mb-3", style={"backgroundColor": "#f8f9fa", "border": "1px solid #dee2e6"})
    )
    
    # 모든 파일을 하나의 리스트로 통합
    all_files_data = []
    for date_key in sorted_dates:
        files = filtered_groups[date_key]
        for f in files:
            # 날짜 표시 준비 (정확한 날짜로 표기)
            if date_key == "기타":
                date_display = "기타"
                date_badge = "🗂️"
            else:
                date_display = date_key  # 항상 정확한 날짜 표기 (YYYY-MM-DD)
                date_badge = "📅"
            
            all_files_data.append({
                "filename": f["filename"],
                "date": f"{date_badge} {date_display}",
                "time": f["time_str"] if f["time_str"] != "N/A" else "00:00",
                "size": f["size"],
                "sort_key": f["datetime"] if f["datetime"] and isinstance(f["datetime"], datetime) else datetime.min
            })
    
    # 날짜시간 순으로 정렬 (최신 순)
    all_files_data.sort(key=lambda x: x["sort_key"], reverse=True)
    
    # sort_key 제거 (테이블에 표시하지 않음)
    for item in all_files_data:
        del item["sort_key"]
    
    # 파일이 없는 경우 처리
    if not all_files_data:
        content.append(
            html.Div([
                html.Div([
                    html.I(className="fas fa-file-times me-2", style={"color": "#6b7280", "fontSize": "1.2rem"}),
                    html.Span("파일이 없습니다", style={"color": "#6b7280", "fontSize": "0.9rem"})
                ], className="d-flex align-items-center justify-content-center p-4", style={"backgroundColor": "#f9fafb", "borderRadius": "8px", "border": "1px dashed #d1d5db"})
            ])
        )
        return html.Div(content)
    
    # 통합된 파일 테이블
    content.append(
        dbc.Card([
            dbc.CardBody([
                dash_table.DataTable(
                    id={"type": "all-files-table", "index": active_tab},
                    data=all_files_data,
                    columns=[
                        {"name": "📄 파일명", "id": "filename", "type": "text"},
                        {"name": "📅 날짜", "id": "date", "type": "text"},
                        {"name": "🕐 시간", "id": "time", "type": "text"},
                        {"name": "💾 크기", "id": "size", "type": "text"}
                    ],
                    row_selectable="multi",
                    page_size=10,
                    style_cell={
                        "textAlign": "center",
                        "fontSize": "0.8rem",
                        "padding": "12px 10px",
                        "border": "none",
                        "borderBottom": "1px solid #e9ecef",
                        "fontFamily": "'Inter', sans-serif"
                    },
                    style_header={
                        "backgroundColor": "#f8f9fa", 
                        "fontWeight": 600,
                        "color": "#495057",
                        "border": "none",
                        "borderBottom": "2px solid #dee2e6",
                        "fontSize": "0.8rem",
                        "textAlign": "center"
                    },
                    style_data={
                        "backgroundColor": "white",
                        "border": "none",
                        "color": "#212529"
                    },
                    style_data_conditional=[
                        {
                            'if': {'row_index': 'odd'},
                            'backgroundColor': '#f8f9fa'
                        },
                        {
                            'if': {'state': 'selected'},
                            'backgroundColor': '#e3f2fd',
                            'border': '1px solid #2196f3',
                            'color': '#1565c0',
                            'fontWeight': '500'
                        },
                        {
                            'if': {'column_id': 'filename'},
                            'textAlign': 'center',
                            'fontWeight': '500'
                        },
                        {
                            'if': {'column_id': 'date'},
                            'textAlign': 'center',
                            'fontWeight': '500'
                        }
                    ],
                    css=[
                        {
                            'selector': '.dash-table-container .dash-spreadsheet-container .dash-spreadsheet-inner tr:hover',
                            'rule': 'background-color: #e8f5e8 !important; transition: all 0.2s ease;'
                        }
                    ],
                    style_table={"borderRadius": "6px", "overflow": "hidden"}
                )
            ], className="p-0")
        ], className="mb-3", style={"border": "1px solid #dee2e6", "boxShadow": "0 2px 4px rgba(0,0,0,0.1)"})
    )
    
    return html.Div(content)

# ───────────────────── ⑥ 파일 다운로드 콜백 (새로운 구조) ────────────────────
@dash.callback(
    Output("dl-inp-download", "data"),
    Input("btn-dl-inp", "n_clicks"),
    State("file-data-store", "data"),
    State({"type": "all-files-table", "index": "tab-inp"}, "selected_rows"),
    State({"type": "all-files-table", "index": "tab-inp"}, "data"),
    prevent_initial_call=True,
)
def dl_download_inp(n_clicks, file_data, selected_rows, table_data):
    return _download_selected_files(n_clicks, file_data, "inp", selected_rows, table_data)

@dash.callback(
    Output("dl-frd-download", "data"),
    Input("btn-dl-frd", "n_clicks"),
    State("file-data-store", "data"),
    State({"type": "all-files-table", "index": "tab-frd"}, "selected_rows"),
    State({"type": "all-files-table", "index": "tab-frd"}, "data"),
    prevent_initial_call=True,
)
def dl_download_frd(n_clicks, file_data, selected_rows, table_data):
    return _download_selected_files(n_clicks, file_data, "frd", selected_rows, table_data)

@dash.callback(
    Output("dl-vtk-download", "data"),
    Input("btn-dl-vtk", "n_clicks"),
    State("file-data-store", "data"),
    State({"type": "all-files-table", "index": "tab-vtk"}, "selected_rows"),
    State({"type": "all-files-table", "index": "tab-vtk"}, "data"),
    prevent_initial_call=True,
)
def dl_download_vtk(n_clicks, file_data, selected_rows, table_data):
    return _download_selected_files(n_clicks, file_data, "vtk", selected_rows, table_data)

# ───────────────────── 새로운 다운로드 로직 ────────────────────
# ───────────────────── ⑦ 모든 파일 선택/해제 콜백 ────────────────────
@dash.callback(
    Output({"type": "all-files-table", "index": dash.MATCH}, "selected_rows"),
    Input({"type": "select-all-btn", "index": dash.MATCH}, "n_clicks"),
    Input({"type": "deselect-all-btn", "index": dash.MATCH}, "n_clicks"),
    State({"type": "all-files-table", "index": dash.MATCH}, "data"),
    prevent_initial_call=True,
)
def handle_select_all(select_clicks, deselect_clicks, data):
    ctx = dash.callback_context
    if not ctx.triggered or not data:
        raise PreventUpdate
    
    # callback_context.triggered_id를 사용하여 더 간단하게 처리
    triggered_id = ctx.triggered_id
    
    if triggered_id and 'type' in triggered_id:
        button_type = triggered_id['type']
        
        if button_type == "select-all-btn":
            return list(range(len(data)))
        elif button_type == "deselect-all-btn":
            return []
    
    raise PreventUpdate

def _download_selected_files(n_clicks, file_data, ftype, selected_rows, table_data):
    """선택된 파일들을 다운로드하는 함수"""
    if not n_clicks or not file_data:
        raise PreventUpdate
    
    folder = file_data["folder"]
    
    # 선택된 파일들만 다운로드
    if selected_rows and table_data:
        # 선택된 행의 파일명들 추출
        selected_files = [table_data[i]["filename"] for i in selected_rows if table_data and i < len(table_data)]
        download_type = "선택된"
    else:
        # 선택된 파일이 없으면 모든 파일 다운로드
        grouped_files = file_data["grouped_files"]
        selected_files = []
        for date_files in grouped_files.values():
            selected_files.extend([f["filename"] for f in date_files])
        download_type = "전체"
    
    if not selected_files:
        raise PreventUpdate
    
    # 실제 존재하는 파일만 필터링
    existing_files = []
    for fname in selected_files:
        path = os.path.join(folder, fname)
        if os.path.exists(path):
            existing_files.append(fname)
    
    if not existing_files:
        raise PreventUpdate
    
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for fname in existing_files:
            path = os.path.join(folder, fname)
            # 날짜별 폴더 구조로 압축
            dt = parse_filename_datetime(fname)
            if dt:
                date_folder = dt.strftime("%Y-%m-%d")
                archive_path = f"{date_folder}/{fname}"
            else:
                archive_path = f"기타/{fname}"
            zf.write(path, arcname=archive_path)
    
    buf.seek(0)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_count = len(existing_files)
    return dcc.send_bytes(buf.getvalue(), filename=f"{ftype}_{download_type}파일_{file_count}개_{timestamp}.zip") 