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

register_page(__name__, path="/download")

# 프로젝트 메타데이터 (URL 파라미터 파싱에 사용)
projects_df = api_db.get_project_data()

def parse_filename_datetime(filename):
    """파일명에서 날짜시간 추출 (YYYYMMDDHHMM 형식)"""
    try:
        base_name = filename.split('.')[0]
        if len(base_name) >= 12 and base_name.isdigit():
            year = int(base_name[:4])
            month = int(base_name[4:6])
            day = int(base_name[6:8])
            hour = int(base_name[8:10])
            minute = int(base_name[10:12])
            return datetime(year, month, day, hour, minute)
    except:
        pass
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
    dbc.Container([
        dbc.Alert(id="download-alert", is_open=False, duration=3000, color="info"),
        dcc.Store(id="file-data-store"),  # 파일 데이터 저장용
        
        dbc.Row([
            # 좌측: 프로젝트 정보 + 콘크리트 목록
            dbc.Col([
                # 프로젝트 정보 카드
                html.Div([
                    dbc.Alert(id="current-project-info", color="info", className="mb-0 py-2"),
                ], className="mb-2"),
                
                # 콘크리트 목록 카드
                html.Div([
                    html.Div([
                        html.H6("🧱 콘크리트 목록", className="mb-2 text-secondary fw-bold", style={"fontSize": "0.9rem"}),
                        html.Small("💡 콘크리트를 클릭하여 선택할 수 있습니다", className="text-muted mb-2 d-block", style={"fontSize": "0.75rem"}),
                        dash_table.DataTable(
                            id="dl-tbl-concrete", 
                            page_size=10, 
                            row_selectable="single",
                            style_table={"overflowY": "auto", "height": "45vh"},
                            style_cell={
                                "whiteSpace": "nowrap", 
                                "textAlign": "center",
                                "fontSize": "0.8rem",
                                "padding": "12px 10px",
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
                                "fontSize": "0.75rem",
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
                                }
                            ]
                        ),
                    ], className="p-3")
                ], className="bg-white rounded shadow-sm border")
            ], md=3),
            dbc.Col([
                # 파일 다운로드 카드
                html.Div([
                    html.Div([
                        html.H6("📁 파일 다운로드", id="dl-concrete-title", className="mb-2 text-secondary fw-bold", style={"fontSize": "0.9rem"}),
                        html.Small("💡 탭을 선택하여 파일 유형을 변경할 수 있습니다", className="text-muted mb-3 d-block", style={"fontSize": "0.75rem"}),
                        dbc.Tabs([
                            dbc.Tab(label="INP 파일", tab_id="tab-inp", 
                                   style={"fontSize": "0.85rem", "padding": "8px 16px"},
                                   active_label_style={"backgroundColor": "#e8f4fd", "color": "#1d4ed8", "fontWeight": "600"}),
                            dbc.Tab(label="FRD 파일", tab_id="tab-frd",
                                   style={"fontSize": "0.85rem", "padding": "8px 16px"},
                                   active_label_style={"backgroundColor": "#e8f4fd", "color": "#1d4ed8", "fontWeight": "600"}),
                            dbc.Tab(label="VTK 파일", tab_id="tab-vtk",
                                   style={"fontSize": "0.85rem", "padding": "8px 16px"},
                                   active_label_style={"backgroundColor": "#e8f4fd", "color": "#1d4ed8", "fontWeight": "600"}),
                        ], id="dl-tabs", active_tab="tab-inp", className="mb-3"),
                        
                        # 날짜 필터 영역
                        html.Div([
                            html.Div([
                                html.Label("📅 날짜 범위", className="form-label", style={"fontSize": "0.8rem", "fontWeight": "600"}),
                                dcc.DatePickerRange(
                                    id="date-range-picker",
                                    start_date=datetime.now() - timedelta(days=30),
                                    end_date=datetime.now(),
                                    display_format="YYYY-MM-DD",
                                    style={"fontSize": "0.8rem"}
                                )
                            ], className="col-md-6"),
                            html.Div([
                                html.Label("🔍 빠른 필터", className="form-label", style={"fontSize": "0.8rem", "fontWeight": "600"}),
                                dcc.Dropdown(
                                    id="quick-filter",
                                    options=[
                                        {"label": "전체", "value": "all"},
                                        {"label": "오늘", "value": "today"},
                                        {"label": "최근 3일", "value": "3days"},
                                        {"label": "최근 7일", "value": "7days"},
                                        {"label": "최근 30일", "value": "30days"}
                                    ],
                                    value="30days",
                                    clearable=False,
                                    style={"fontSize": "0.8rem"}
                                )
                            ], className="col-md-6")
                        ], className="row mb-3"),
                        
                        html.Div(id="dl-tab-content"),
                    ], className="p-3")
                ], className="bg-white rounded shadow-sm border"),
            ], md=9),
        ], className="g-3"),
    ], className="py-3")
])

# ───────────────────── ① URL에서 프로젝트 정보 파싱 ─────────────────────
@dash.callback(
    Output("selected-project-store", "data"),
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
        from urllib.parse import parse_qs
        params = parse_qs(search.lstrip('?'))
        project_pk = params.get('page', [None])[0]
        
        if not project_pk:
            return None, [
                "프로젝트가 선택되지 않았습니다. ",
                html.A("홈으로 돌아가기", href="/", className="alert-link")
            ]
        
        # 프로젝트 정보 조회 (project_pk가 문자열일 수 있음)
        project_info = projects_df[projects_df["project_pk"] == project_pk]
        if project_info.empty:
            return None, [
                f"프로젝트 ID {project_pk}를 찾을 수 없습니다. ",
                html.A("홈으로 돌아가기", href="/", className="alert-link")
            ]
        
        project_name = project_info.iloc[0]["name"]
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
    Output("dl-concrete-title", "children"),
    Input("selected-project-store", "data"),
    prevent_initial_call=False,
)
def dl_load_concrete_list(project_pk):
    if not project_pk:
        return [], [], [], "📁 파일 다운로드"
    
    df_conc = api_db.get_concrete_data(project_pk=project_pk)
    data = df_conc[["concrete_pk", "name"]].to_dict("records")
    columns = [{"name": "이름", "id": "name"}]
    return data, columns, [], "📁 파일 다운로드"

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

# ───────────────────── ④ 파일 데이터 저장 ────────────────────
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

# ───────────────────── ⑤ 콘크리트 선택 → 탭 콘텐츠 업데이트 ────────────────────
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
                html.I(className="fas fa-info-circle me-2", style={"color": "#6b7280", "fontSize": "1.2rem"}),
                html.Span("콘크리트를 선택하면 파일 목록이 표시됩니다", style={"color": "#6b7280", "fontSize": "0.9rem"})
            ], className="d-flex align-items-center justify-content-center p-4", style={"backgroundColor": "#f9fafb", "borderRadius": "8px", "border": "1px dashed #d1d5db"})
        ])
    
    grouped_files = file_data["grouped_files"]
    active_tab = file_data["active_tab"]
    
    # 날짜 필터링
    start_dt = datetime.strptime(start_date, "%Y-%m-%d").date() if start_date else None
    end_dt = datetime.strptime(end_date, "%Y-%m-%d").date() if end_date else None
    
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
                html.Span("선택한 날짜 범위에 파일이 없습니다", style={"color": "#6b7280", "fontSize": "0.9rem"})
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
        html.Div([
            dbc.Button("📋 모든 파일 선택", id=f"btn-select-all-{active_tab}", color="outline-primary", size="sm", className="me-2", n_clicks=0),
            dbc.Button("🗑️ 선택 해제", id=f"btn-deselect-all-{active_tab}", color="outline-secondary", size="sm", className="me-2", n_clicks=0),
            dbc.Button("📥 선택한 파일 다운로드", id=f"btn-dl-{active_tab.split('-')[1]}", color="success", size="sm", n_clicks=0),
            dcc.Download(id=f"dl-{active_tab.split('-')[1]}-download")
        ], className="mb-3 text-center")
    )
    
    # 날짜별 그룹 표시
    for date_key in sorted_dates:
        files = filtered_groups[date_key]
        
        # 날짜 헤더
        if date_key == "기타":
            date_display = "📂 기타 파일"
            badge_color = "secondary"
        else:
            date_obj = datetime.strptime(date_key, "%Y-%m-%d")
            if date_obj.date() == datetime.now().date():
                date_display = f"📅 오늘 ({date_key})"
                badge_color = "success"
            elif date_obj.date() == datetime.now().date() - timedelta(days=1):
                date_display = f"📅 어제 ({date_key})"
                badge_color = "warning"
            else:
                date_display = f"📅 {date_key}"
                badge_color = "info"
        
        # 날짜별 섹션
        content.append(
            html.Div([
                html.Div([
                    html.Span(date_display, className=f"badge bg-{badge_color} me-2", style={"fontSize": "0.85rem"}),
                    html.Span(f"{len(files)}개", className="text-muted", style={"fontSize": "0.8rem"}),
                    dbc.Button(f"날짜별 다운로드", id=f"btn-dl-date-{date_key}-{active_tab}", color="outline-success", size="sm", className="ms-auto", n_clicks=0)
                ], className="d-flex align-items-center mb-2"),
                
                # 파일 테이블
                dash_table.DataTable(
                    id=f"tbl-{date_key}-{active_tab}",
                    data=[{
                        "filename": f["filename"],
                        "time": f["time_str"],
                        "size": f["size"],
                        "select": False
                    } for f in files],
                    columns=[
                        {"name": "파일명", "id": "filename"},
                        {"name": "시간", "id": "time"},
                        {"name": "크기", "id": "size"}
                    ],
                    row_selectable="multi",
                    page_size=8,
                    style_cell={
                        "textAlign": "center",
                        "fontSize": "0.75rem",
                        "padding": "8px 6px",
                        "border": "none",
                        "borderBottom": "1px solid #f1f1f0",
                        "fontFamily": "'Inter', sans-serif"
                    },
                    style_header={
                        "backgroundColor": "#f8f9fa", 
                        "fontWeight": 600,
                        "color": "#495057",
                        "border": "none",
                        "fontSize": "0.7rem",
                        "textTransform": "uppercase"
                    },
                    style_data={
                        "backgroundColor": "white",
                        "border": "none",
                        "color": "#37352f"
                    },
                    style_data_conditional=[
                        {
                            'if': {'state': 'selected'},
                            'backgroundColor': '#e8f4fd',
                            'border': '1px solid #579ddb',
                            'color': '#1d4ed8'
                        }
                    ],
                    style_table={"marginBottom": "10px", "borderRadius": "6px", "overflow": "hidden"}
                )
            ], className="mb-4 p-3", style={"backgroundColor": "#fdfdfd", "borderRadius": "8px", "border": "1px solid #e9ecef"})
        )
    
    return html.Div(content)

# ───────────────────── ⑥ 파일 다운로드 콜백 (새로운 구조) ────────────────────
@dash.callback(
    Output("dl-inp-download", "data"),
    Input("btn-dl-inp", "n_clicks"),
    State("file-data-store", "data"),
    State("dl-tab-content", "children"),
    prevent_initial_call=True,
)
def dl_download_inp(n_clicks, file_data, tab_content):
    return _download_selected_files(n_clicks, file_data, "inp")

@dash.callback(
    Output("dl-frd-download", "data"),
    Input("btn-dl-frd", "n_clicks"),
    State("file-data-store", "data"),
    State("dl-tab-content", "children"),
    prevent_initial_call=True,
)
def dl_download_frd(n_clicks, file_data, tab_content):
    return _download_selected_files(n_clicks, file_data, "frd")

@dash.callback(
    Output("dl-vtk-download", "data"),
    Input("btn-dl-vtk", "n_clicks"),
    State("file-data-store", "data"),
    State("dl-tab-content", "children"),
    prevent_initial_call=True,
)
def dl_download_vtk(n_clicks, file_data, tab_content):
    return _download_selected_files(n_clicks, file_data, "vtk")

# ───────────────────── 새로운 다운로드 로직 ────────────────────
def _download_selected_files(n_clicks, file_data, ftype):
    """선택된 파일들을 다운로드하는 함수 (새로운 구조에 맞게 수정 필요)"""
    if not n_clicks or not file_data:
        raise PreventUpdate
    
    # 임시로 모든 파일을 다운로드하도록 구현 (선택 기능은 향후 구현)
    folder = file_data["folder"]
    grouped_files = file_data["grouped_files"]
    
    all_files = []
    for date_files in grouped_files.values():
        all_files.extend([f["filename"] for f in date_files])
    
    if not all_files:
        raise PreventUpdate
    
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for fname in all_files:
            path = os.path.join(folder, fname)
            if os.path.exists(path):
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
    return dcc.send_bytes(buf.getvalue(), filename=f"{ftype}_files_{timestamp}.zip") 