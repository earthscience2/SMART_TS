from __future__ import annotations

import os
import glob
import numpy as np
import pandas as pd
import dash
from dash import html, dcc, Input, Output, State, dash_table, register_page, callback
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
from datetime import datetime, timedelta
import shutil
import api_db
from utils.encryption import parse_project_key_from_url

register_page(__name__, path="/strength", title="강도/탄성계수 3D 분석")

# ────────────── 레이아웃 ──────────────
layout = dbc.Container(
    fluid=True,
    className="px-4 py-3",
    style={"backgroundColor": "#f7f9fc", "minHeight": "100vh"},
    children=[
        dcc.Location(id="project-url-strength", refresh=False),
        
        # ── 데이터 저장용 Store들
        dcc.Store(id="project-info-store-strength", data=None),
        dcc.Store(id="strength-formula-params-store", data={}),
        dcc.Store(id="current-strength-time-store", data=None),
        dcc.Store(id="current-strength-file-title-store", data=None),
        
        # 시간 슬라이더 관련 Store들
        dcc.Store(id="play-state-strength", data={"playing": False}),
        dcc.Store(id="speed-state-strength", data={"speed": 1}),
        dcc.Store(id="unified-strength-colorbar-state", data=False),
        
        # ── 다운로드 컴포넌트들
        dcc.Download(id="download-3d-strength-image"),
        dcc.Download(id="download-current-inp-strength"),
        
        # ── 필수 숨겨진 컴포넌트들 (콜백 오류 방지)
        html.Div([
            # 시간 슬라이더
            dcc.Slider(id="time-slider-strength", min=0, max=5, step=1, value=0, marks={}),
            dbc.Button(id="btn-play-strength"),
            dbc.Button(id="btn-pause-strength"),
            dcc.Dropdown(id="speed-dropdown-strength"),
            dbc.Button(id="btn-unified-strength-colorbar"),
            dbc.Interval(id="play-interval-strength", interval=1000, n_intervals=0, disabled=True),
            dbc.Button(id="btn-save-3d-strength-image"),
            dbc.Button(id="btn-save-3d-strength-image", style={"display": "none"}),
            # 속도 버튼들
            dbc.DropdownMenuItem(id="speed-1x-strength"),
            dbc.DropdownMenuItem(id="speed-2x-strength"),
            dbc.DropdownMenuItem(id="speed-4x-strength"),
            dbc.DropdownMenuItem(id="speed-8x-strength"),
        ], style={"display": "none"}),
        
        # ── 알림 컴포넌트
        dbc.Alert(id="strength-project-alert", is_open=False, duration=4000),
        
        # ── 컨펌 다이얼로그
        dcc.ConfirmDialog(
            id="confirm-del-concrete-strength",
            message="선택한 콘크리트를 정말 삭제하시겠습니까?\n\n※ 관련 FRD 파일도 함께 삭제됩니다."
        ),
        
        # 메인 콘텐츠 영역
        dbc.Row([
            # 왼쪽 사이드바 - 콘크리트 목록
            dbc.Col([
                html.Div([
                    # 프로젝트 안내 박스
                    dbc.Alert(id="current-project-info-strength", color="info", className="mb-3 py-2"),
                    
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
                                    id="tbl-concrete-strength",
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
                                                'filter_query': '{status} = 설정중',
                                                'column_id': 'status'
                                            },
                                            'backgroundColor': '#f5f5f5',
                                            'color': '#6c757d',
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
                                            'fontWeight': '500',
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
                                dbc.Button("분석 시작", id="btn-concrete-analyze-strength", color="success", size="sm", className="px-3", disabled=True),
                                dbc.Button("삭제", id="btn-concrete-del-strength", color="danger", size="sm", className="px-3", disabled=True),
                            ], className="d-flex justify-content-center gap-2 mt-2"),
                        ])
                    ], style={
                        "backgroundColor": "white",
                        "padding": "20px",
                        "borderRadius": "12px",
                        "boxShadow": "0 1px 3px rgba(0,0,0,0.1)",
                        "border": "1px solid #e2e8f0",
                        "height": "fit-content"
                    })
                ])
            ], md=4),
            
            # 오른쪽 메인 콘텐츠 영역
            dbc.Col([
                html.Div([
                    # 탭 메뉴 (노션 스타일)
                    html.Div([
                        dbc.Tabs([
                            dbc.Tab(
                                label="입력 파라미터", 
                                tab_id="tab-strength-params",
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
                                label="3D 강도/탄성계수", 
                                tab_id="tab-strength-3d",
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
                                label="노드별 표", 
                                tab_id="tab-strength-table",
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
                        ], id="tabs-main-strength", active_tab="tab-strength-params", className="mb-0")
                    ], style={
                        "backgroundColor": "#f8fafc",
                        "padding": "8px 8px 0 8px",
                        "borderRadius": "8px 8px 0 0",
                        "border": "1px solid #e2e8f0",
                        "borderBottom": "none"
                    }),
                    
                    # 탭 콘텐츠 영역
                    html.Div(id="tab-content-strength", style={
                        "backgroundColor": "white",
                        "border": "1px solid #e2e8f0",
                        "borderTop": "none",
                        "borderRadius": "0 0 8px 8px",
                        "padding": "20px",
                        "minHeight": "calc(100vh - 200px)"
                    })
                ])
            ], md=8)
        ], className="g-4"),
    ]
)

# 이후 콜백/함수는 TCI 분석 페이지 구조를 참고하여 추가 예정 

# ────────────── 콘크리트 목록 데이터 로딩 콜백 ──────────────
@callback(
    Output("tbl-concrete-strength", "data"),
    Output("tbl-concrete-strength", "columns"),
    Output("tbl-concrete-strength", "selected_rows"),
    Output("tbl-concrete-strength", "style_data_conditional"),
    Output("btn-concrete-analyze-strength", "disabled"),
    Output("btn-concrete-del-strength", "disabled"),
    Output("time-slider-strength", "min"),
    Output("time-slider-strength", "max"),
    Output("time-slider-strength", "value"),
    Output("time-slider-strength", "marks"),
    Output("current-strength-time-store", "data"),
    Output("project-info-store-strength", "data"),
    Input("project-url-strength", "search"),
    Input("project-url-strength", "pathname"),
    prevent_initial_call=True,
)
def load_concrete_data_strength(search, pathname):
    """프로젝트 정보를 로드하고 콘크리트 목록을 표시합니다."""
    # 강도 분석 페이지에서만 실행
    if '/strength' not in pathname:
        raise dash.exceptions.PreventUpdate
    
    # URL에서 프로젝트 정보 추출 (암호화된 URL 지원)
    project_pk = None
    if search:
        try:
            project_pk = parse_project_key_from_url(search)
        except Exception as e:
            print(f"DEBUG: 프로젝트 키 파싱 오류: {e}")
            pass
    
    if not project_pk:
        return [], [], [], [], True, True, 0, 5, 0, {}, None, None
    
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
            return [], [], [], [], True, True, 0, 5, 0, {}, None, {"name": proj_name, "pk": project_pk}
        
    except Exception as e:
        return [], [], [], [], True, True, 0, 5, 0, {}, None, None
    
    table_data = []
    for _, row in df_conc.iterrows():
        try:
            dims = eval(row["dims"])
            nodes = dims["nodes"]
            h = dims["h"]
            shape_info = f"{len(nodes)}각형 (높이: {h:.2f}m)"
        except Exception:
            shape_info = "파싱 오류"
        
        # INP 파일 확인
        concrete_pk = row["concrete_pk"]
        inp_dir = f"inp/{concrete_pk}"
        has_inp = os.path.exists(inp_dir) and len(glob.glob(f"{inp_dir}/*.inp")) > 0
        
        # 상태 결정 (응력분석 페이지와 동일한 로직)
        if row["activate"] == 1:  # 활성
            if has_inp:
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
            "has_inp": has_inp,
        })

    # 테이블 컬럼 정의
    columns = [
        {"name": "이름", "id": "name", "type": "text"},
        {"name": "타설일(경과일)", "id": "pour_date", "type": "text"},
        {"name": "상태", "id": "status", "type": "text"},
    ]
    
    # 테이블 스타일 설정 (응력분석 페이지와 동일)
    style_data_conditional = [
        # 분석중 상태 (초록색)
        {
            'if': {
                'filter_query': '{status} = "분석중"',
                'column_id': 'status'
            },
            'backgroundColor': '#dcfce7',
            'color': '#166534',
            'fontWeight': '600',
            'borderRadius': '4px',
            'textAlign': 'center'
        },
        # 설정중 상태 (회색)
        {
            'if': {
                'filter_query': '{status} = "설정중"',
                'column_id': 'status'
            },
            'backgroundColor': '#f5f5f5',
            'color': '#6c757d',
            'fontWeight': '600',
            'borderRadius': '4px',
            'textAlign': 'center'
        },
        # 타설일(경과일) 컬럼 스타일 추가
        {
            'if': {'column_id': 'pour_date'},
            'fontSize': '0.85rem',
            'color': '#6b7280',
            'fontWeight': '500'
        },
        # 이름 컬럼 스타일 추가
        {
            'if': {'column_id': 'name'},
            'fontWeight': '500',
            'color': '#111827',
            'textAlign': 'left',
            'paddingLeft': '16px'
        }
    ]
    
    # 상태별 기본 정렬 적용 (분석중 → 설정중)
    if table_data:
        table_data = sorted(table_data, key=lambda x: x.get('status_sort', 999))
    
    return table_data, columns, [], style_data_conditional, True, True, 0, 5, 0, {}, None, {"name": proj_name, "pk": project_pk} 

# ────────────── 프로젝트 정보 업데이트 콜백 ──────────────
@callback(
    Output("current-project-info-strength", "children"),
    Input("project-info-store-strength", "data"),
    Input("project-url-strength", "pathname"),
    prevent_initial_call=True,
)
def update_project_info_strength(project_info, pathname):
    """프로젝트 정보를 표시합니다."""
    # 강도 분석 페이지에서만 실행
    if '/strength' not in pathname:
        raise dash.exceptions.PreventUpdate
    
    if not project_info:
        return [
            "프로젝트가 선택되지 않았습니다. ",
            html.A("홈으로 돌아가기", href="/", className="alert-link")
        ]
    
    project_name = project_info.get("name", "알 수 없는 프로젝트")
    return f"📁 현재 프로젝트: {project_name}"

# ────────────── 콘크리트 선택 콜백 ──────────────
@callback(
    Output("btn-concrete-analyze-strength", "disabled", allow_duplicate=True),
    Output("btn-concrete-del-strength", "disabled", allow_duplicate=True),
    Output("current-strength-file-title-store", "data", allow_duplicate=True),
    Output("time-slider-strength", "min", allow_duplicate=True),
    Output("time-slider-strength", "max", allow_duplicate=True),
    Output("time-slider-strength", "value", allow_duplicate=True),
    Output("time-slider-strength", "marks", allow_duplicate=True),
    Input("tbl-concrete-strength", "selected_rows"),
    Input("project-url-strength", "pathname"),
    State("tbl-concrete-strength", "data"),
    prevent_initial_call=True,
)
def on_concrete_select_strength(selected_rows, pathname, tbl_data):
    """콘크리트 선택 시 버튼 상태와 시간 슬라이더를 업데이트합니다."""
    # 강도 분석 페이지에서만 실행
    if '/strength' not in pathname:
        raise dash.exceptions.PreventUpdate
    
    if not selected_rows or not tbl_data:
        return True, True, None, 0, 5, 0, {}  # 버튼 비활성화, 슬라이더 초기화
    
    try:
        row = pd.DataFrame(tbl_data).iloc[selected_rows[0]]
        concrete_pk = row["concrete_pk"]
        concrete_name = row["name"]
        is_active = row["activate"] == "활성"
        
        # 버튼 상태 결정
        if not is_active:  # 분석중
            analyze_disabled = True
            delete_disabled = False
        else:  # 설정중
            analyze_disabled = False
            delete_disabled = True
        
        # 초기값 설정
        current_file_title = concrete_name
        slider_min, slider_max, slider_value = 0, 5, 0
        slider_marks = {}
        
        # 분석중 상태일 때 INP 파일에서 시간 정보 추출 (온도 분석 페이지와 동일한 방식)
        if not is_active:
            inp_dir = f"inp/{concrete_pk}"
            inp_files = sorted(glob.glob(f"{inp_dir}/*.inp"))
            if inp_files:
                # 파일명에서 시간 정보 추출 (YYYYMMDDHH 형식)
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
                    # 온도/응력 분석 페이지 방식으로 marks 생성
                    marks = {}
                    seen_dates = set()
                    for i, dt in enumerate(times):
                        date_str = dt.strftime("%m/%d")
                        # 0, 마지막, 새로운 날짜만 표시
                        if date_str not in seen_dates or i == 0 or i == max_idx:
                            marks[i] = date_str
                            seen_dates.add(date_str)
                    # marks가 너무 적으면 시간까지 표시
                    if len(marks) < 3:
                        marks = {i: times[i].strftime("%m/%d %Hh") for i in range(len(times))}
                    slider_marks = marks
        
        return analyze_disabled, delete_disabled, current_file_title, slider_min, slider_max, slider_value, slider_marks
        
    except Exception as e:
        print(f"콘크리트 선택 오류: {e}")
        return True, True, None, 0, 5, 0, {}

# ────────────── 삭제 확인 콜백 ──────────────
@callback(
    Output("confirm-del-concrete-strength", "displayed"),
    Input("btn-concrete-del-strength", "n_clicks"),
    State("tbl-concrete-strength", "selected_rows"),
    prevent_initial_call=True
)
def ask_delete_concrete_strength(n, sel):
    return bool(n and sel)

# ────────────── 분석 시작 콜백 ──────────────
@callback(
    Output("strength-project-alert", "children", allow_duplicate=True),
    Output("strength-project-alert", "color", allow_duplicate=True),
    Output("strength-project-alert", "is_open", allow_duplicate=True),
    Output("tbl-concrete-strength", "data", allow_duplicate=True),
    Output("btn-concrete-analyze-strength", "disabled", allow_duplicate=True),
    Output("btn-concrete-del-strength", "disabled", allow_duplicate=True),
    Input("btn-concrete-analyze-strength", "n_clicks"),
    State("tbl-concrete-strength", "selected_rows"),
    State("tbl-concrete-strength", "data"),
    prevent_initial_call=True,
)
def start_analysis_strength(n_clicks, selected_rows, tbl_data):
    if not selected_rows or not tbl_data:
        return "콘크리트를 선택하세요", "warning", True, dash.no_update, dash.no_update, dash.no_update

    row = pd.DataFrame(tbl_data).iloc[selected_rows[0]]
    concrete_pk = row["concrete_pk"]

    try:
        # activate를 0으로 변경
        api_db.update_concrete_data(concrete_pk=concrete_pk, activate=0)
        
        # 테이블 데이터 업데이트
        updated_data = tbl_data.copy()
        updated_data[selected_rows[0]]["activate"] = "비활성"
        updated_data[selected_rows[0]]["status"] = "분석중"
        
        return f"{concrete_pk} 분석이 시작되었습니다", "success", True, updated_data, True, False
    except Exception as e:
        return f"분석 시작 실패: {e}", "danger", True, dash.no_update, dash.no_update, dash.no_update

# ────────────── 삭제 실행 콜백 ──────────────
@callback(
    Output("strength-project-alert", "children", allow_duplicate=True),
    Output("strength-project-alert", "color", allow_duplicate=True),
    Output("strength-project-alert", "is_open", allow_duplicate=True),
    Output("tbl-concrete-strength", "data", allow_duplicate=True),
    Input("confirm-del-concrete-strength", "submit_n_clicks"),
    State("tbl-concrete-strength", "selected_rows"),
    State("tbl-concrete-strength", "data"),
    prevent_initial_call=True,
)
def delete_concrete_confirm_strength(_click, sel, tbl_data):
    if not sel or not tbl_data:
        raise dash.exceptions.PreventUpdate

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

# ────────────── 입력 파라미터 탭 콘텐츠 함수 ──────────────
def create_strength_params_tab_content():
    return html.Div([
        html.H5("강도/탄성계수 공식 및 입력값", style={"fontWeight": "700", "marginBottom": "18px", "color": "#1e293b"}),
        html.Hr(style={"margin": "8px 0 20px 0", "borderColor": "#e5e7eb"}),
        
        # 기본 입력값 섹션
        html.H6("📋 기본 입력값", style={"fontWeight": "600", "marginBottom": "15px", "color": "#374151"}),
        dbc.Row([
            dbc.Col([
                html.Label("28일 압축강도 fcm28 (MPa)", style={"fontWeight": "600"}),
                dbc.Input(id="strength-fcm28", type="number", value=30, min=10, max=100, 
                         style={"marginBottom": "15px"}),
                html.Label("28일 탄성계수 Ec28 (MPa)", style={"fontWeight": "600"}),
                dbc.Input(id="strength-ec28", type="number", value=30000, min=10000, max=50000,
                         style={"marginBottom": "15px"}),
            ], md=6),
            dbc.Col([
                html.Label("기준온도 Tref (°C)", style={"fontWeight": "600"}),
                dbc.Input(id="strength-tref", type="number", value=20, min=10, max=30,
                         style={"marginBottom": "15px"}),
                html.Label("강도 계수 s", style={"fontWeight": "600"}),
                dbc.Input(id="strength-s-coef", type="number", value=0.2, min=0.1, max=1, step=0.01,
                         style={"marginBottom": "15px"}),
            ], md=6),
        ]),
        
        # 강도 공식 섹션
        html.H6("🧱 강도 공식", style={"fontWeight": "600", "marginTop": "25px", "marginBottom": "15px", "color": "#374151"}),
        dbc.Row([
            dbc.Col([
                html.Label("강도 공식 선택", style={"fontWeight": "600"}),
                dcc.Dropdown(
                    id="strength-fc-formula",
                    options=[
                        {"label": "CEB-FIP Model Code 1990", "value": "ceb"},
                        {"label": "ACI 318", "value": "aci"},
                        {"label": "Eurocode2", "value": "ec2"},
                    ],
                    value="ceb", clearable=False,
                    style={"marginBottom": "15px"}
                ),
            ], md=6),
            dbc.Col([
                html.Label("(CEB-FIP) 강도 공식 계수", style={"fontWeight": "600"}),
                dbc.Row([
                    dbc.Col([
                        html.Label("a 계수", style={"fontSize": "0.9rem"}),
                        dbc.Input(id="strength-fc-coef-a", type="number", value=1, min=0.1, max=2, step=0.01),
                    ], md=6),
                    dbc.Col([
                        html.Label("b 계수", style={"fontSize": "0.9rem"}),
                        dbc.Input(id="strength-fc-coef-b", type="number", value=1, min=0.1, max=2, step=0.01),
                    ], md=6),
                ]),
            ], md=6),
        ]),
        
        # 탄성계수 공식 섹션
        html.H6("📐 탄성계수 공식", style={"fontWeight": "600", "marginTop": "25px", "marginBottom": "15px", "color": "#374151"}),
        dbc.Row([
            dbc.Col([
                html.Label("탄성계수 공식 선택", style={"fontWeight": "600"}),
                dcc.Dropdown(
                    id="strength-ec-formula",
                    options=[
                        {"label": "CEB-FIP Model Code 1990", "value": "ceb"},
                        {"label": "ACI 318", "value": "aci"},
                        {"label": "Eurocode2", "value": "ec2"},
                    ],
                    value="ceb", clearable=False,
                    style={"marginBottom": "15px"}
                ),
            ], md=6),
            dbc.Col([
                html.Label("(CEB-FIP) 탄성계수 s계수", style={"fontWeight": "600"}),
                dbc.Input(id="strength-ec-s", type="number", value=0.2, min=0.1, max=1, step=0.01),
            ], md=6),
        ]),
        
        # 공식 미리보기
        html.Div(id="strength-formula-preview", className="mt-4"),
    ], style={"maxWidth": "900px", "margin": "0 auto"})

# ────────────── 탭 콘텐츠 스위치 콜백 ──────────────
@callback(
    Output("tab-content-strength", "children"),
    Input("tabs-main-strength", "active_tab"),
    Input("tbl-concrete-strength", "selected_rows"),
    Input("project-url-strength", "pathname"),
    State("tbl-concrete-strength", "data"),
    prevent_initial_call=True,
)
def switch_tab_strength(active_tab, selected_rows, pathname, tbl_data):
    """탭 전환 시 해당 탭의 콘텐츠를 표시합니다."""
    # 강도 분석 페이지에서만 실행
    if '/strength' not in pathname:
        raise dash.exceptions.PreventUpdate
    
    if not selected_rows or not tbl_data:
        return html.Div([
            # 안내 메시지 (노션 스타일)
            html.Div([
                html.Div([
                    html.I(className="fas fa-mouse-pointer fa-2x", style={"color": "#3b82f6", "marginBottom": "16px"}),
                    html.H5("콘크리트를 선택해주세요", style={
                        "color": "#1f2937",
                        "fontWeight": "600",
                        "lineHeight": "1.6",
                        "margin": "0",
                        "marginBottom": "8px"
                    }),
                    html.P("왼쪽 콘크리트 목록에서 분석할 콘크리트를 선택하시면", style={
                        "color": "#6b7280",
                        "fontSize": "14px",
                        "margin": "0",
                        "lineHeight": "1.5"
                    }),
                    html.P("분석 결과를 확인할 수 있습니다.", style={
                        "color": "#6b7280",
                        "fontSize": "14px",
                        "margin": "0",
                        "lineHeight": "1.5"
                    })
                ], style={
                    "textAlign": "center",
                    "padding": "80px 40px",
                    "backgroundColor": "#f8fafc",
                    "borderRadius": "12px",
                    "border": "1px solid #e2e8f0",
                    "marginTop": "40px"
                })
            ])
        ])
    
    if active_tab == "tab-strength-params":
        return create_strength_params_tab_content()
    elif active_tab == "tab-strength-3d":
        return html.Div([
            # 시간 슬라이더 섹션
            html.Div([
                html.H6("⏰ 시간 슬라이더", style={"fontWeight": "600", "marginBottom": "15px", "color": "#374151"}),
                dbc.Row([
                    dbc.Col([
                        dcc.Slider(
                            id="time-slider-display-strength",
                            min=0, max=5, step=1, value=0,
                            marks={},
                            tooltip={"placement": "bottom", "always_visible": True}
                        )
                    ], md=8),
                    dbc.Col([
                        dbc.ButtonGroup([
                            dbc.Button("▶️", id="btn-play-strength", size="sm", color="primary"),
                            dbc.Button("⏸️", id="btn-pause-strength", size="sm", color="secondary"),
                        ], size="sm"),
                        dcc.Interval(id="play-interval-strength", interval=1000, n_intervals=0, disabled=True),
                    ], md=4, className="d-flex align-items-center")
                ], className="mb-4"),
                
                # 현재 시간 정보
                html.Div(id="strength-time-info", className="mb-3"),
            ], style={
                "backgroundColor": "#f8fafc",
                "padding": "20px",
                "borderRadius": "8px",
                "border": "1px solid #e2e8f0",
                "marginBottom": "20px"
            }),
            
            # 3D 뷰어 영역 (온도 분석 페이지와 유사한 구조)
            html.Div([
                html.Div([
                    html.H6("🧱 3D 강도 분포", style={
                        "fontWeight": "600", "color": "#374151", "marginBottom": "0", "fontSize": "16px",
                        "display": "inline-block", "marginRight": "20px"
                    }),
                    html.Div([
                        html.Label("강도 바 통일", style={
                            "fontWeight": "500", "color": "#374151", "marginBottom": "8px", "fontSize": "13px",
                            "display": "inline-block", "marginRight": "8px"
                        }),
                        dbc.Switch(id="btn-unified-strength-colorbar", value=False, style={"display": "inline-block"}),
                    ], style={"display": "inline-block", "verticalAlign": "top", "marginRight": "16px"}),
                    html.Div([
                        html.Label("강도 종류", style={
                            "fontWeight": "500", "color": "#374151", "marginBottom": "8px", "fontSize": "13px",
                            "display": "inline-block", "marginRight": "8px"
                        }),
                        dcc.Dropdown(
                            options=[
                                {"label": "압축강도", "value": "compressive"},
                                {"label": "인장강도", "value": "tensile"},
                            ],
                            value="compressive", id="strength-component-selector",
                            style={"width": "120px", "fontSize": "12px"},
                            clearable=False, searchable=False
                        ),
                    ], style={"display": "inline-block", "verticalAlign": "top"}),
                ], style={"marginBottom": "16px"}),
                
                # 3D 뷰어
                dcc.Graph(
                    id="viewer-3d-strength",
                    style={"height": "600px", "borderRadius": "8px", "border": "1px solid #e2e8f0"},
                    config={
                        'displayModeBar': True,
                        'displaylogo': False,
                        'modeBarButtonsToRemove': ['pan2d', 'lasso2d', 'select2d'],
                        'toImageButtonOptions': {
                            'format': 'png',
                            'filename': 'strength_3d_view',
                            'height': 600,
                            'width': 800,
                            'scale': 2
                        }
                    }
                ),
                
                # 저장 버튼들
                html.Div([
                    dcc.Loading(
                        id="loading-btn-save-3d-strength-image", type="circle",
                        children=[
                            dbc.Button(
                                [html.I(className="fas fa-camera me-1"), "이미지 저장"],
                                id="btn-save-3d-strength-image", color="primary", size="lg",
                                style={
                                    "borderRadius": "8px", "fontWeight": "600", "boxShadow": "0 1px 2px rgba(0,0,0,0.1)",
                                    "fontSize": "15px", "width": "120px", "height": "48px", "marginRight": "16px"
                                }
                            )
                        ]
                    ),
                    dcc.Loading(
                        id="loading-btn-save-current-inp-strength", type="circle",
                        children=[
                            dbc.Button(
                                [html.I(className="fas fa-file-download me-1"), "INP 저장"],
                                id="btn-save-current-inp-strength", color="secondary", size="lg",
                                style={
                                    "borderRadius": "8px", "fontWeight": "600", "boxShadow": "0 1px 2px rgba(0,0,0,0.1)",
                                    "fontSize": "15px", "width": "120px", "height": "48px"
                                }
                            )
                        ]
                    ),
                ], style={"display": "flex", "justifyContent": "center", "alignItems": "center", "marginTop": "20px"}),
                
                # Store들
                dcc.Store(id="unified-strength-colorbar-state", data=False),
            ], style={
                "padding": "20px",
                "backgroundColor": "white",
                "borderRadius": "12px",
                "border": "1px solid #e2e8f0",
                "boxShadow": "0 1px 3px rgba(0,0,0,0.1)"
            })
        ])
    elif active_tab == "tab-strength-table":
        return html.Div([
            html.H5("노드별 강도/탄성계수 표", style={"fontWeight": "700", "marginBottom": "18px", "color": "#1e293b"}),
            html.Hr(style={"margin": "8px 0 20px 0", "borderColor": "#e5e7eb"}),
            html.Div(id="strength-table-content", style={"minHeight": "400px"})
        ])
    else:
        return html.Div("알 수 없는 탭입니다.")

# ────────────── 입력값 Store 저장 콜백 ──────────────
@callback(
    Output("strength-formula-params-store", "data"),
    Output("strength-formula-preview", "children"),
    Input("strength-fc-formula", "value"),
    Input("strength-fcm28", "value"),
    Input("strength-fc-coef-a", "value"),
    Input("strength-fc-coef-b", "value"),
    Input("strength-ec-formula", "value"),
    Input("strength-ec28", "value"),
    Input("strength-ec-s", "value"),
    Input("strength-tref", "value"),
    Input("strength-s-coef", "value"),
    prevent_initial_call=False
)
def update_strength_formula_params(fc_formula, fcm28, fc_a, fc_b, ec_formula, ec28, ec_s, tref, s_coef):
    params = {
        "fc_formula": fc_formula,
        "fcm28": fcm28,
        "fc_a": fc_a,
        "fc_b": fc_b,
        "ec_formula": ec_formula,
        "ec28": ec28,
        "ec_s": ec_s,
        "tref": tref,
        "s_coef": s_coef
    }
    
    # 미리보기 텍스트
    preview = html.Div([
        html.Div([
            html.Strong("📋 기본 입력값:", style={"color": "#1f2937"}),
            html.Br(),
            f"• 28일 압축강도: {fcm28} MPa",
            html.Br(),
            f"• 28일 탄성계수: {ec28:,} MPa",
            html.Br(),
            f"• 기준온도: {tref}°C",
            html.Br(),
            f"• 강도 계수: {s_coef}"
        ], style={"color": "#64748b", "fontSize": "14px", "marginBottom": "10px"}),
        html.Div([
            html.Strong("🧱 강도 공식:", style={"color": "#1f2937"}),
            html.Br(),
            f"• 선택된 공식: {fc_formula.upper()}",
            html.Br(),
            f"• a 계수: {fc_a}, b 계수: {fc_b}"
        ], style={"color": "#64748b", "fontSize": "14px", "marginBottom": "10px"}),
        html.Div([
            html.Strong("📐 탄성계수 공식:", style={"color": "#1f2937"}),
            html.Br(),
            f"• 선택된 공식: {ec_formula.upper()}",
            html.Br(),
            f"• s 계수: {ec_s}"
        ], style={"color": "#64748b", "fontSize": "14px"})
    ])
    return params, preview 

# ────────────── INP 파일 파서: 노드 좌표 및 온도 데이터 추출 ──────────────
def read_inp_nodes_and_temperatures(inp_path):
    """INP 파일에서 노드 좌표와 온도 데이터를 추출합니다."""
    nodes = []
    temperatures = []
    time_stamps = []
    
    try:
        with open(inp_path, 'r') as f:
            lines = f.readlines()
        
        node_section = False
        temp_section = False
        current_time = None
        
        for line in lines:
            line = line.strip()
            
            # 노드 섹션 처리
            if line.startswith('*NODE'):
                node_section = True
                temp_section = False
                continue
            elif line.startswith('*TEMPERATURE'):
                node_section = False
                temp_section = True
                # 시간 정보 추출 (예: *TEMPERATURE, TIME=2024010110)
                if 'TIME=' in line:
                    time_str = line.split('TIME=')[1].split(',')[0]
                    try:
                        current_time = datetime.strptime(time_str, "%Y%m%d%H")
                        time_stamps.append(current_time)
                    except:
                        current_time = None
                continue
            elif line.startswith('*'):
                node_section = False
                temp_section = False
                continue
            
            # 노드 좌표 파싱
            if node_section and line:
                parts = line.split(',')
                if len(parts) >= 4:
                    node_id = int(parts[0])
                    x = float(parts[1])
                    y = float(parts[2])
                    z = float(parts[3])
                    nodes.append({"id": node_id, "x": x, "y": y, "z": z})
            
            # 온도 데이터 파싱
            elif temp_section and line and current_time:
                parts = line.split(',')
                if len(parts) >= 2:
                    node_id = int(parts[0])
                    temp = float(parts[1])
                    temperatures.append({
                        "time": current_time,
                        "node_id": node_id,
                        "temperature": temp
                    })
                    
    except Exception as e:
        print(f"INP 파싱 오류: {e}")
    
    return nodes, temperatures, time_stamps

def read_inp_nodes_and_elements(inp_path):
    """INP 파일에서 노드 좌표와 엘리먼트 정보를 추출합니다."""
    nodes = {}
    elements = []
    
    try:
        with open(inp_path, 'r') as f:
            lines = f.readlines()
        
        node_section = False
        element_section = False
        
        for line in lines:
            line = line.strip()
            
            # 노드 섹션 처리
            if line.startswith('*NODE'):
                node_section = True
                element_section = False
                continue
            elif line.startswith('*ELEMENT'):
                node_section = False
                element_section = True
                continue
            elif line.startswith('*'):
                node_section = False
                element_section = False
                continue
            
            # 노드 좌표 파싱
            if node_section and line:
                parts = line.split(',')
                if len(parts) >= 4:
                    node_id = int(parts[0])
                    x = float(parts[1])
                    y = float(parts[2])
                    z = float(parts[3])
                    nodes[node_id] = {"x": x, "y": y, "z": z}
            
            # 엘리먼트 정보 파싱
            elif element_section and line:
                parts = line.split(',')
                if len(parts) >= 4:  # 최소 4개 노드 (테트라헤드론)
                    element_nodes = [int(parts[i]) for i in range(1, len(parts)) if parts[i].strip()]
                    if len(element_nodes) >= 3:  # 최소 3개 노드 필요
                        elements.append(element_nodes)
                    
    except Exception as e:
        print(f"INP 엘리먼트 파싱 오류: {e}")
    
    return nodes, elements

def read_inp_nodes(inp_path):
    """INP 파일에서 노드 좌표만 추출합니다."""
    nodes, _, _ = read_inp_nodes_and_temperatures(inp_path)
    return nodes

def create_mesh3d_figure(nodes_dict, elements, values_dict, title, colorbar_title, colorscale):
    """Mesh3d 그래프를 생성합니다."""
    # 노드 좌표 배열 생성
    x_coords = []
    y_coords = []
    z_coords = []
    node_ids = list(nodes_dict.keys())
    node_id_to_index = {node_id: i for i, node_id in enumerate(node_ids)}
    
    for node_id in node_ids:
        node = nodes_dict[node_id]
        x_coords.append(node["x"])
        y_coords.append(node["y"])
        z_coords.append(node["z"])
    
    # 엘리먼트 인덱스 배열 생성
    i_indices = []
    j_indices = []
    k_indices = []
    element_values = []
    
    for element in elements:
        if len(element) >= 3:
            # 첫 번째 삼각형
            i_indices.append(node_id_to_index[element[0]])
            j_indices.append(node_id_to_index[element[1]])
            k_indices.append(node_id_to_index[element[2]])
            
            # 엘리먼트의 평균값 계산
            avg_value = sum(values_dict.get(node_id, 0) for node_id in element[:3]) / 3
            element_values.append(avg_value)
            
            # 4개 이상의 노드가 있으면 추가 삼각형 생성
            if len(element) >= 4:
                # 두 번째 삼각형
                i_indices.append(node_id_to_index[element[0]])
                j_indices.append(node_id_to_index[element[2]])
                k_indices.append(node_id_to_index[element[3]])
                
                avg_value2 = sum(values_dict.get(node_id, 0) for node_id in [element[0], element[2], element[3]]) / 3
                element_values.append(avg_value2)
    
    # Mesh3d 그래프 생성
    fig = go.Figure(data=go.Mesh3d(
        x=x_coords,
        y=y_coords,
        z=z_coords,
        i=i_indices,
        j=j_indices,
        k=k_indices,
        intensity=element_values,
        colorscale=colorscale,
        colorbar=dict(title=colorbar_title, thickness=10),
        showscale=True,
        opacity=0.8,
        hoverinfo='all',
        hovertemplate='<b>엘리먼트</b><br>' +
                     f'{colorbar_title}: %{{intensity:.2f}}<br>' +
                     '<extra></extra>'
    ))
    
    fig.update_layout(
        title=title,
        scene=dict(
            aspectmode='data',
            bgcolor='white',
            xaxis_title='X (m)',
            yaxis_title='Y (m)',
            zaxis_title='Z (m)'
        ),
        margin=dict(l=0, r=0, t=30, b=0)
    )
    
    return fig

# ────────────── 등가재령 및 강도/탄성계수 계산 함수 ──────────────
def calc_equivalent_age(chronological_age, temperatures, tref=20):
    """
    온도 이력을 고려한 등가재령 계산
    chronological_age: 실제 경과일수
    temperatures: 온도 이력 데이터 (시간별 온도)
    tref: 기준온도 (기본값 20°C)
    """
    if not temperatures or chronological_age <= 0:
        return chronological_age
    
    # 온도별 성숙도 계수 계산 (Arrhenius 공식)
    def maturity_coefficient(T):
        # Q = 4000 K (활성화 에너지)
        # R = 8.314 J/(mol·K) (기체상수)
        Q = 4000
        R = 8.314
        T_kelvin = T + 273.15  # 섭씨를 켈빈으로 변환
        Tref_kelvin = tref + 273.15
        return np.exp((Q/R) * (1/Tref_kelvin - 1/T_kelvin))
    
    # 시간 간격 (시간 단위)
    dt = 1.0  # 1시간 간격으로 가정
    
    equivalent_age = 0
    for temp_data in temperatures:
        T = temp_data["temperature"]
        if T > -10:  # 동해 방지 (온도가 너무 낮으면 성숙도 중단)
            maturity = maturity_coefficient(T)
            equivalent_age += maturity * dt
    
    # 시간을 일 단위로 변환
    equivalent_age /= 24.0
    
    return equivalent_age

def calc_strength_over_age(age_days, fcm28, formula="ceb", a=1, b=1):
    """
    재령(age_days)에 따른 압축강도(MPa) 계산
    formula: 'ceb', 'aci', 'ec2'
    """
    if age_days <= 0:
        return 0
    if formula == "ceb":
        # CEB-FIP: fcm(t) = fcm28 * ( t / (a + b*t) )^0.5
        return fcm28 * (age_days / (a + b * age_days)) ** 0.5
    elif formula == "aci":
        # ACI: fcm(t) = fcm28 * (age_days/28)^0.5 (t<=28), 이후는 fcm28
        return fcm28 * (age_days/28) ** 0.5 if age_days <= 28 else fcm28
    elif formula == "ec2":
        # EC2: fcm(t) = fcm28 * exp[s*(1-(28/t))], s=0.2(보통강도)
        s = 0.2
        return fcm28 * np.exp(s * (1 - 28/age_days))
    else:
        return fcm28

def calc_elastic_modulus_over_age(age_days, fc_t, ec28, formula="ceb", s=0.2):
    """
    재령(age_days)에 따른 탄성계수(MPa) 계산
    fc_t: 해당 시점 강도(MPa)
    formula: 'ceb', 'aci', 'ec2'
    """
    if formula == "ceb":
        # CEB-FIP: Ec(t) = Ec28 * exp[s*(1-28/t)]
        return ec28 * np.exp(s * (1 - 28/age_days))
    elif formula == "aci":
        # ACI: Ec = 4700 * sqrt(fc)
        return 4700 * np.sqrt(fc_t)
    elif formula == "ec2":
        # EC2: Ec = 22000 * (fc/10)^0.3
        return 22000 * (fc_t/10) ** 0.3
    else:
        return ec28 

# ────────────── 3D 그래프 및 표 콜백 ──────────────
@callback(
    Output("viewer-3d-strength", "figure"),
    Output("strength-time-info", "children"),
    Output("current-strength-time-store", "data", allow_duplicate=True),
    Input("tbl-concrete-strength", "selected_rows"),
    Input("strength-formula-params-store", "data"),
    Input("time-slider-strength", "value"),
    Input("tabs-main-strength", "active_tab"),
    Input("unified-strength-colorbar-state", "data"),
    Input("strength-component-selector", "value"),
    State("tbl-concrete-strength", "data"),
    State("current-strength-file-title-store", "data"),
    prevent_initial_call=True
)
def update_strength_3d_viewer(selected_rows, formula_params, time_idx, active_tab, unified_colorbar, strength_type, tbl_data, current_file_title):
    """콘크리트 선택 시 3D 강도 분석을 수행합니다."""
    if not selected_rows or not tbl_data or not formula_params:
        return go.Figure(), "", None
    
    try:
        row = pd.DataFrame(tbl_data).iloc[selected_rows[0]]
        concrete_pk = row["concrete_pk"]
        concrete_name = row["name"]
        
        # 콘크리트 DB에서 타설일 정보 가져오기
        df_conc = api_db.get_concrete_data(concrete_pk=concrete_pk)
        if df_conc.empty:
            return go.Figure(), "", None
        
        concrete_info = df_conc.iloc[0]
        pour_date = concrete_info.get("con_t")
        
        # INP 파일 찾기
        inp_dir = f"inp/{concrete_pk}"
        if not os.path.exists(inp_dir):
            return go.Figure(), "", None
        
        inp_files = glob.glob(f"{inp_dir}/*.inp")
        if not inp_files:
            return go.Figure(), "", None
        
        # 파일명에서 시간 정보 추출 (온도 분석 페이지와 동일한 방식)
        times = []
        for f in inp_files:
            try:
                time_str = os.path.basename(f).split(".")[0]
                dt = datetime.strptime(time_str, "%Y%m%d%H")
                times.append(dt)
            except:
                continue
        
        if not times:
            return go.Figure(), "", None
        
        # 현재 시간 인덱스에 해당하는 INP 파일 선택
        if 0 <= time_idx < len(times):
            current_time = times[time_idx]
            current_inp_file = inp_files[time_idx]
        else:
            return go.Figure(), "", None
        
        # 현재 INP 파일에서 노드와 온도 데이터 추출
        nodes, temperatures, time_stamps = read_inp_nodes_and_temperatures(current_inp_file)
        if not nodes:
            return go.Figure(), "", None
        
        # 엘리먼트 정보도 추출 (면 표시용)
        nodes_dict, elements = read_inp_nodes_and_elements(current_inp_file)
        if not elements:
            # 엘리먼트가 없으면 점 표시로 fallback
            use_mesh = False
        else:
            use_mesh = True
        
        # 현재 시간에 해당하는 온도 데이터 필터링
        current_temps = []
        if temperatures:
            current_temps = temperatures  # 모든 온도 데이터 사용 (시간별로 이미 분리되어 있음)
        
        # 경과일 계산
        chronological_age = 0
        if pour_date:
            try:
                if hasattr(pour_date, 'strftime'):
                    pour_dt = pour_date
                elif isinstance(pour_date, str):
                    if 'T' in pour_date:
                        pour_dt = datetime.fromisoformat(pour_date.replace('Z', ''))
                    else:
                        pour_dt = datetime.strptime(str(pour_date), '%Y-%m-%d %H:%M:%S')
                else:
                    pour_dt = None
                
                if pour_dt:
                    chronological_age = (current_time - pour_dt).total_seconds() / (24 * 3600)  # 일 단위
            except Exception as e:
                print(f"경과일 계산 오류: {e}")
                chronological_age = 7.0  # 기본값
        
        # 등가재령 계산 (온도 이력 고려)
        equivalent_age = calc_equivalent_age(
            chronological_age, 
            temperatures, 
            formula_params.get("tref", 20)
        )
        
        # 강도 계산
        fc_t = calc_strength_over_age(
            equivalent_age, 
            formula_params["fcm28"], 
            formula_params["fc_formula"],
            formula_params["fc_a"],
            formula_params["fc_b"]
        )
        
        # 노드별 온도에 따른 강도 계산
        strength_values = {}
        
        for node in nodes:
            node_id = node["id"]
            # 해당 노드의 현재 온도 찾기
            node_temp = None
            for temp in current_temps:
                if temp["node_id"] == node_id:
                    node_temp = temp["temperature"]
                    break
            
            if node_temp is not None:
                # 노드별 등가재령 계산
                node_equivalent_age = calc_equivalent_age(
                    chronological_age, 
                    [{"temperature": node_temp}], 
                    formula_params.get("tref", 20)
                )
                
                # 노드별 강도 계산
                if strength_type == "compressive":
                    node_fc = calc_strength_over_age(
                        node_equivalent_age,
                        formula_params["fcm28"],
                        formula_params["fc_formula"],
                        formula_params["fc_a"],
                        formula_params["fc_b"]
                    )
                else:  # tensile
                    # 인장강도는 압축강도의 약 10%로 가정
                    node_fc = calc_strength_over_age(
                        node_equivalent_age,
                        formula_params["fcm28"],
                        formula_params["fc_formula"],
                        formula_params["fc_a"],
                        formula_params["fc_b"]
                    ) * 0.1
            else:
                # 온도 데이터가 없으면 평균값 사용
                if strength_type == "compressive":
                    node_fc = fc_t
                else:  # tensile
                    node_fc = fc_t * 0.1
            
            strength_values[node_id] = node_fc
        
        # 3D 그래프 생성
        if use_mesh and elements:
            # 면 표시 (Mesh3d) - 온도 분석 페이지와 유사한 방식
            # 노드 좌표 배열 생성
            x_coords = []
            y_coords = []
            z_coords = []
            node_ids = list(nodes_dict.keys())
            node_id_to_index = {node_id: i for i, node_id in enumerate(node_ids)}
            
            for node_id in node_ids:
                node = nodes_dict[node_id]
                x_coords.append(node["x"])
                y_coords.append(node["y"])
                z_coords.append(node["z"])
            
            # 엘리먼트 인덱스 배열 생성
            i_indices = []
            j_indices = []
            k_indices = []
            element_values = []
            
            for element in elements:
                if len(element) >= 3:
                    # 첫 번째 삼각형
                    i_indices.append(node_id_to_index[element[0]])
                    j_indices.append(node_id_to_index[element[1]])
                    k_indices.append(node_id_to_index[element[2]])
                    
                    # 엘리먼트의 평균값 계산
                    avg_value = sum(strength_values.get(node_id, 0) for node_id in element[:3]) / 3
                    element_values.append(avg_value)
                    
                    # 4개 이상의 노드가 있으면 추가 삼각형 생성
                    if len(element) >= 4:
                        # 두 번째 삼각형
                        i_indices.append(node_id_to_index[element[0]])
                        j_indices.append(node_id_to_index[element[2]])
                        k_indices.append(node_id_to_index[element[3]])
                        
                        avg_value2 = sum(strength_values.get(node_id, 0) for node_id in [element[0], element[2], element[3]]) / 3
                        element_values.append(avg_value2)
            
            # Mesh3d 그래프 생성
            fig = go.Figure(data=go.Mesh3d(
                x=x_coords,
                y=y_coords,
                z=z_coords,
                i=i_indices,
                j=j_indices,
                k=k_indices,
                intensity=element_values,
                colorscale='Viridis',
                colorbar=dict(
                    title=f"{'압축' if strength_type == 'compressive' else '인장'}강도 (MPa)", 
                    thickness=15,
                    len=0.8,
                    x=1.02
                ),
                showscale=True,
                opacity=0.8,
                hoverinfo='all',
                hovertemplate='<b>엘리먼트</b><br>' +
                             f"{'압축' if strength_type == 'compressive' else '인장'}강도: %{{intensity:.2f}} MPa<br>" +
                             '<extra></extra>'
            ))
            
            fig.update_layout(
                title=f"{concrete_name} - 3D {'압축' if strength_type == 'compressive' else '인장'}강도 분포",
                scene=dict(
                    aspectmode='data',
                    bgcolor='white',
                    xaxis=dict(
                        title='X (m)',
                        showgrid=True,
                        gridcolor='lightgray',
                        zeroline=True,
                        zerolinecolor='black'
                    ),
                    yaxis=dict(
                        title='Y (m)',
                        showgrid=True,
                        gridcolor='lightgray',
                        zeroline=True,
                        zerolinecolor='black'
                    ),
                    zaxis=dict(
                        title='Z (m)',
                        showgrid=True,
                        gridcolor='lightgray',
                        zeroline=True,
                        zerolinecolor='black'
                    ),
                    camera=dict(
                        eye=dict(x=1.5, y=1.5, z=1.5)
                    )
                ),
                margin=dict(l=0, r=0, t=50, b=0),
                height=600
            )
        else:
            # 점 표시 (Scatter3d) - fallback
            x_coords = [node["x"] for node in nodes]
            y_coords = [node["y"] for node in nodes]
            z_coords = [node["z"] for node in nodes]
            strength_vals = [strength_values.get(node["id"], fc_t) for node in nodes]
            
            fig = go.Figure(data=go.Scatter3d(
                x=x_coords, y=y_coords, z=z_coords, 
                mode='markers',
                marker=dict(
                    size=5,
                    color=strength_vals,
                    colorscale='Viridis',
                    colorbar=dict(
                        title=f"{'압축' if strength_type == 'compressive' else '인장'}강도 (MPa)", 
                        thickness=15,
                        len=0.8,
                        x=1.02
                    ),
                    showscale=True
                ),
                text=[f"노드 {node['id']}<br>{'압축' if strength_type == 'compressive' else '인장'}강도: {val:.2f} MPa" for node, val in zip(nodes, strength_vals)],
                hovertemplate='%{text}<extra></extra>'
            ))
            fig.update_layout(
                title=f"{concrete_name} - 3D {'압축' if strength_type == 'compressive' else '인장'}강도 분포",
                scene=dict(
                    aspectmode='data', 
                    bgcolor='white',
                    xaxis=dict(
                        title='X (m)',
                        showgrid=True,
                        gridcolor='lightgray',
                        zeroline=True,
                        zerolinecolor='black'
                    ),
                    yaxis=dict(
                        title='Y (m)',
                        showgrid=True,
                        gridcolor='lightgray',
                        zeroline=True,
                        zerolinecolor='black'
                    ),
                    zaxis=dict(
                        title='Z (m)',
                        showgrid=True,
                        gridcolor='lightgray',
                        zeroline=True,
                        zerolinecolor='black'
                    ),
                    camera=dict(
                        eye=dict(x=1.5, y=1.5, z=1.5)
                    )
                ),
                margin=dict(l=0, r=0, t=50, b=0),
                height=600
            )
        
        # 시간 정보 표시
        time_info = ""
        if time_stamps and 0 <= time_idx < len(time_stamps):
            current_time = time_stamps[time_idx]
            time_info = html.Div([
                html.Strong(f"📅 현재 시간: {current_time.strftime('%Y-%m-%d %H:%M')}"),
                html.Br(),
                html.Strong(f"⏱️ 경과일: {chronological_age:.1f}일"),
                html.Br(),
                html.Strong(f"🌡️ 등가재령: {equivalent_age:.1f}일"),
                html.Br(),
                html.Strong(f"📊 평균 {'압축' if strength_type == 'compressive' else '인장'}강도: {fc_t:.2f} MPa")
            ], style={"color": "#374151", "fontSize": "14px"})
        
        return fig, time_info, time_idx
            
    except Exception as e:
        return go.Figure(), f"분석 중 오류 발생: {str(e)}", None

# ────────────── 시간 슬라이더 동기화 콜백 ──────────────
@callback(
    Output("time-slider-display-strength", "value"),
    Output("time-slider-display-strength", "min"),
    Output("time-slider-display-strength", "max"),
    Output("time-slider-display-strength", "marks"),
    Input("time-slider-strength", "value"),
    Input("time-slider-strength", "min"),
    Input("time-slider-strength", "max"),
    Input("time-slider-strength", "marks"),
    prevent_initial_call=True,
)
def sync_time_slider_strength(value, min_val, max_val, marks):
    """숨겨진 슬라이더와 표시 슬라이더를 동기화합니다."""
    return value, min_val, max_val, marks

# ────────────── 재생/일시정지 콜백 ──────────────
@callback(
    Output("play-state-strength", "data"),
    Output("play-interval-strength", "disabled"),
    Output("btn-play-strength", "disabled"),
    Output("btn-pause-strength", "disabled"),
    Input("btn-play-strength", "n_clicks"),
    State("play-state-strength", "data"),
    prevent_initial_call=True,
)
def start_playback_strength(n_clicks, play_state):
    """재생을 시작합니다."""
    if not n_clicks:
        raise dash.exceptions.PreventUpdate
    
    return {"playing": True}, False, True, False

@callback(
    Output("play-state-strength", "data", allow_duplicate=True),
    Output("play-interval-strength", "disabled", allow_duplicate=True),
    Output("btn-play-strength", "disabled", allow_duplicate=True),
    Output("btn-pause-strength", "disabled", allow_duplicate=True),
    Input("btn-pause-strength", "n_clicks"),
    State("play-state-strength", "data"),
    prevent_initial_call=True,
)
def stop_playback_strength(n_clicks, play_state):
    """재생을 일시정지합니다."""
    if not n_clicks:
        raise dash.exceptions.PreventUpdate
    
    return {"playing": False}, True, False, True

# ────────────── 자동 재생 콜백 ──────────────
@callback(
    Output("time-slider-display-strength", "value", allow_duplicate=True),
    Input("play-interval-strength", "n_intervals"),
    State("play-state-strength", "data"),
    State("speed-state-strength", "data"),
    State("time-slider-display-strength", "value"),
    State("time-slider-display-strength", "max"),
    prevent_initial_call=True,
)
def auto_play_slider_strength(n_intervals, play_state, speed_state, current_value, max_value):
    """자동 재생 시 슬라이더 값을 업데이트합니다."""
    if not play_state or not play_state.get("playing", False):
        raise dash.exceptions.PreventUpdate
    
    speed = speed_state.get("speed", 1) if speed_state else 1
    new_value = current_value + speed
    
    if new_value > max_value:
        new_value = 0  # 처음으로 돌아가기
    
    return new_value

# ────────────── 속도 설정 콜백 ──────────────
@callback(
    Output("speed-state-strength", "data"),
    Input("speed-1x-strength", "n_clicks"),
    Input("speed-2x-strength", "n_clicks"),
    Input("speed-4x-strength", "n_clicks"),
    Input("speed-8x-strength", "n_clicks"),
    prevent_initial_call=True,
)
def set_speed_strength(speed_1x, speed_2x, speed_4x, speed_8x):
    """재생 속도를 설정합니다."""
    ctx = dash.callback_context
    if not ctx.triggered:
        raise dash.exceptions.PreventUpdate
    
    button_id = ctx.triggered[0]["prop_id"].split(".")[0]
    
    if "speed-1x" in button_id:
        return {"speed": 1}
    elif "speed-2x" in button_id:
        return {"speed": 2}
    elif "speed-4x" in button_id:
        return {"speed": 4}
    elif "speed-8x" in button_id:
        return {"speed": 8}
    else:
        return {"speed": 1} 

# ────────────── 노드별 표 콜백 ──────────────
@callback(
    Output("strength-table-content", "children"),
    Input("tbl-concrete-strength", "selected_rows"),
    Input("strength-formula-params-store", "data"),
    Input("time-slider-strength", "value"),
    State("tbl-concrete-strength", "data"),
    prevent_initial_call=True
)
def update_strength_table(selected_rows, formula_params, time_idx, tbl_data):
    """콘크리트 선택 시 노드별 강도/탄성계수 표를 생성합니다."""
    if not selected_rows or not tbl_data or not formula_params:
        return html.Div("콘크리트를 선택하고 입력 파라미터를 설정하세요.")
    
    try:
        row = pd.DataFrame(tbl_data).iloc[selected_rows[0]]
        concrete_pk = row["concrete_pk"]
        concrete_name = row["name"]
        
        # 콘크리트 DB에서 타설일 정보 가져오기
        df_conc = api_db.get_concrete_data(concrete_pk=concrete_pk)
        if df_conc.empty:
            return html.Div("콘크리트 정보를 찾을 수 없습니다.")
        
        concrete_info = df_conc.iloc[0]
        pour_date = concrete_info.get("con_t")
        
        # INP 파일 찾기
        inp_dir = f"inp/{concrete_pk}"
        if not os.path.exists(inp_dir):
            return html.Div("INP 파일이 없습니다.")
        
        inp_files = glob.glob(f"{inp_dir}/*.inp")
        if not inp_files:
            return html.Div("INP 파일이 없습니다.")
        
        # 첫 번째 INP 파일에서 노드와 온도 데이터 추출
        inp_file = inp_files[0]
        nodes, temperatures, time_stamps = read_inp_nodes_and_temperatures(inp_file)
        if not nodes:
            return html.Div("노드 정보를 읽을 수 없습니다.")
        
        # 현재 시간 인덱스에 해당하는 온도 데이터 필터링
        current_temps = []
        if time_stamps and 0 <= time_idx < len(time_stamps):
            current_time = time_stamps[time_idx]
            current_temps = [t for t in temperatures if t["time"] == current_time]
        
        # 경과일 계산
        chronological_age = 0
        if pour_date:
            try:
                if hasattr(pour_date, 'strftime'):
                    pour_dt = pour_date
                elif isinstance(pour_date, str):
                    if 'T' in pour_date:
                        pour_dt = datetime.fromisoformat(pour_date.replace('Z', ''))
                    else:
                        pour_dt = datetime.strptime(str(pour_date), '%Y-%m-%d %H:%M:%S')
                else:
                    pour_dt = None
                
                if pour_dt:
                    chronological_age = (current_time - pour_dt).total_seconds() / (24 * 3600)  # 일 단위
            except Exception as e:
                print(f"경과일 계산 오류: {e}")
                chronological_age = 7.0  # 기본값
        
        # 노드별 표 데이터 생성
        table_data = []
        for i, node in enumerate(nodes[:50]):  # 처음 50개 노드만 표시
            node_id = node["id"]
            
            # 해당 노드의 현재 온도 찾기
            node_temp = None
            for temp in current_temps:
                if temp["node_id"] == node_id:
                    node_temp = temp["temperature"]
                    break
            
            # 노드별 등가재령 및 강도/탄성계수 계산
            if node_temp is not None:
                node_equivalent_age = calc_equivalent_age(
                    chronological_age, 
                    [{"temperature": node_temp}], 
                    formula_params.get("tref", 20)
                )
                
                node_fc = calc_strength_over_age(
                    node_equivalent_age,
                    formula_params["fcm28"],
                    formula_params["fc_formula"],
                    formula_params["fc_a"],
                    formula_params["fc_b"]
                )
                node_ec = calc_elastic_modulus_over_age(
                    node_equivalent_age,
                    node_fc,
                    formula_params["ec28"],
                    formula_params["ec_formula"],
                    formula_params["ec_s"]
                )
            else:
                # 온도 데이터가 없으면 평균값 사용
                equivalent_age = calc_equivalent_age(
                    chronological_age, 
                    temperatures, 
                    formula_params.get("tref", 20)
                )
                node_fc = calc_strength_over_age(
                    equivalent_age,
                    formula_params["fcm28"],
                    formula_params["fc_formula"],
                    formula_params["fc_a"],
                    formula_params["fc_b"]
                )
                node_ec = calc_elastic_modulus_over_age(
                    equivalent_age,
                    node_fc,
                    formula_params["ec28"],
                    formula_params["ec_formula"],
                    formula_params["ec_s"]
                )
                node_temp = "N/A"
            
            table_data.append({
                "노드ID": node_id,
                "X (m)": round(node["x"], 3),
                "Y (m)": round(node["y"], 3),
                "Z (m)": round(node["z"], 3),
                "온도 (°C)": node_temp if node_temp != "N/A" else "N/A",
                "강도 (MPa)": round(node_fc, 2),
                "탄성계수 (MPa)": round(node_ec, 0)
            })
        
        # 시간 정보 표시
        time_info = ""
        if time_stamps and 0 <= time_idx < len(time_stamps):
            current_time = time_stamps[time_idx]
            equivalent_age = calc_equivalent_age(
                chronological_age, 
                temperatures, 
                formula_params.get("tref", 20)
            )
            time_info = html.Div([
                html.Strong(f"📅 현재 시간: {current_time.strftime('%Y-%m-%d %H:%M')}"),
                html.Br(),
                html.Strong(f"⏱️ 경과일: {chronological_age:.1f}일"),
                html.Br(),
                html.Strong(f"🌡️ 등가재령: {equivalent_age:.1f}일")
            ], style={"color": "#374151", "fontSize": "14px", "marginBottom": "15px"})
        
        # 표 생성
        table = dash_table.DataTable(
            columns=[
                {"name": "노드ID", "id": "노드ID", "type": "numeric"},
                {"name": "X (m)", "id": "X (m)", "type": "numeric", "format": {"specifier": ".3f"}},
                {"name": "Y (m)", "id": "Y (m)", "type": "numeric", "format": {"specifier": ".3f"}},
                {"name": "Z (m)", "id": "Z (m)", "type": "numeric", "format": {"specifier": ".3f"}},
                {"name": "온도 (°C)", "id": "온도 (°C)", "type": "numeric", "format": {"specifier": ".1f"}},
                {"name": "강도 (MPa)", "id": "강도 (MPa)", "type": "numeric", "format": {"specifier": ".2f"}},
                {"name": "탄성계수 (MPa)", "id": "탄성계수 (MPa)", "type": "numeric", "format": {"specifier": ".0f"}}
            ],
            data=table_data,
            page_size=15,
            style_table={"overflowY": "auto", "height": "500px"},
            style_cell={
                "textAlign": "center", 
                "fontSize": "13px",
                "padding": "8px",
                "border": "1px solid #e2e8f0"
            },
            style_header={
                "backgroundColor": "#f8fafc", 
                "fontWeight": "600",
                "color": "#374151",
                "border": "1px solid #e2e8f0"
            },
            style_data={
                "backgroundColor": "white",
                "border": "1px solid #e2e8f0"
            },
            style_data_conditional=[
                {
                    'if': {'row_index': 'odd'},
                    'backgroundColor': '#fbfbfa'
                }
            ]
        )
        
        return html.Div([
            time_info,
            table
        ])
            
    except Exception as e:
        return html.Div(f"표 생성 중 오류 발생: {str(e)}") 

# ────────────── 통일된 컬러바 상태 관리 콜백 ──────────────
@callback(
    Output("unified-strength-colorbar-state", "data"),
    Input("btn-unified-strength-colorbar", "value"),
    prevent_initial_call=True,
)
def toggle_unified_strength_colorbar(switch_value):
    """통일된 컬러바 상태를 토글합니다."""
    return switch_value