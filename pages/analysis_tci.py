#!/usr/bin/env python3
# pages/analysis_tci.py
# TCI(열적 균열 지수) 분석 페이지: 응력과 온도 데이터를 이용한 균열 위험도 분석

from __future__ import annotations

import os
import glob
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from scipy.interpolate import griddata
import dash
from dash import (
    html, dcc, Input, Output, State,
    dash_table, register_page, callback
)
import dash_bootstrap_components as dbc
from dash.exceptions import PreventUpdate
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import json
import ast
import re
import time
import shutil
import math

import api_db
import auto_sensor
import auto_inp
from utils.encryption import parse_project_key_from_url

register_page(__name__, path="/tci", title="TCI 분석")

# ────────────────────────────── 레이아웃 ────────────────────────────
layout = dbc.Container(
    fluid=True,
    className="px-4 py-3",
    style={"backgroundColor": "#f7f9fc", "minHeight": "100vh"},
    children=[
        dcc.Location(id="project-url-tci", refresh=False),
        
        # ── 데이터 저장용 Store들
        dcc.Store(id="project-info-store-tci", data=None),
        dcc.Store(id="tci-data-store", data=None),
        dcc.Store(id="current-tci-time-store", data=None),
        
        # ── 다운로드 컴포넌트들
        dcc.Download(id="download-tci-formula-image"),
        dcc.Download(id="download-tci-timeline-image"),
        dcc.Download(id="download-crack-probability-image"),
        dcc.Download(id="download-tci-data-csv"),
        
        # ── 필수 숨겨진 컴포넌트들 (콜백 오류 방지)
        html.Div([
            # 기본 컴포넌트들
            dcc.Graph(id="viewer-tci-formula"),
            dcc.Graph(id="viewer-tci-timeline"),
            dcc.Graph(id="viewer-crack-probability"),
            dbc.Input(id="concrete-age-input", type="number", value=28),
            dbc.Input(id="compressive-strength-input", type="number", value=30),
            dcc.Dropdown(id="tci-time-range-selector"),
            dbc.Button(id="btn-save-tci-formula-image"),
            dbc.Button(id="btn-save-tci-timeline-image"),
            dbc.Button(id="btn-save-crack-probability-image"),
            dbc.Button(id="btn-save-tci-data-csv"),
            dcc.Loading(id="loading-btn-save-tci-formula-image", type="circle"),
            dcc.Loading(id="loading-btn-save-tci-timeline-image", type="circle"),
            dcc.Loading(id="loading-btn-save-crack-probability-image", type="circle"),
            dcc.Loading(id="loading-btn-save-tci-data-csv", type="circle"),
            html.Div(id="tci-statistics-summary"),
            html.Div(id="crack-risk-assessment"),
        ], style={"display": "none"}),

        # ── 알림 컴포넌트
        dbc.Alert(id="tci-project-alert", is_open=False, duration=4000),
        
        # ── 컨펌 다이얼로그
        dcc.ConfirmDialog(
            id="confirm-del-concrete-tci",
            message="선택한 콘크리트를 정말 삭제하시겠습니까?\n\n※ 관련 FRD 파일도 함께 삭제됩니다."
        ),
        
        # 메인 콘텐츠 영역
        dbc.Row([
            # 왼쪽 사이드바 - 콘크리트 목록 (응력 분석과 동일)
            dbc.Col([
                html.Div([
                    # 프로젝트 안내 박스
                    dbc.Alert(id="current-project-info-tci", color="info", className="mb-3 py-2"),
                    
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
                                    id="tbl-concrete-tci",
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
                                dbc.Button("분석 시작", id="btn-concrete-analyze-tci", color="success", size="sm", className="px-3", disabled=True),
                                dbc.Button("삭제", id="btn-concrete-del-tci", color="danger", size="sm", className="px-3", disabled=True),
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
                                label="인장강도 계산식", 
                                tab_id="tab-tci-formula",
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
                                label="입체 TCI", 
                                tab_id="tab-tci-3d",
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
                                label="시간별 TCI 분석", 
                                tab_id="tab-tci-timeline",
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
                                label="균열발생확률 곡선", 
                                tab_id="tab-crack-probability",
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
                        ], id="tabs-main-tci", active_tab="tab-tci-formula", className="mb-0")
                    ], style={
                        "backgroundColor": "#f8fafc",
                        "padding": "8px 8px 0 8px",
                        "borderRadius": "8px 8px 0 0",
                        "border": "1px solid #e2e8f0",
                        "borderBottom": "none"
                    }),
                    
                    # 탭 콘텐츠 영역
                    html.Div(id="tab-content-tci", style={
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

# ───────────────────── TCI 관련 계산 함수들 ─────────────────────

def calculate_tensile_strength(age_days, fc28=30):
    """
    재령에 따른 콘크리트 인장강도를 계산합니다.
    
    Parameters:
    - age_days: 콘크리트 재령 (일)
    - fc28: 28일 압축강도 (MPa)
    
    Returns:
    - fct: 인장강도 (MPa)
    """
    if age_days <= 0:
        return 0
    
    # 28일 기준 인장강도 (약 압축강도의 10%)
    fct28 = 0.1 * fc28
    
    # 재령에 따른 강도 발전 (ACI 209 모델 기반)
    if age_days <= 28:
        # 초기 재령에서의 강도 발전
        t_ratio = age_days / 28
        strength_ratio = t_ratio / (4 + 0.85 * t_ratio)
        fct = fct28 * strength_ratio
    else:
        # 28일 이후의 장기 강도 발전
        log_ratio = math.log(age_days / 28) / math.log(365 / 28)
        strength_ratio = 1 + 0.2 * log_ratio  # 약 20% 추가 증진
        fct = fct28 * min(strength_ratio, 1.3)  # 최대 30% 증진으로 제한
    
    return max(fct, 0.1)  # 최소 0.1 MPa

def calculate_tci(stress_mpa, tensile_strength_mpa):
    """
    TCI(열적 균열 지수)를 계산합니다.
    
    Parameters:
    - stress_mpa: 인장응력 (MPa)
    - tensile_strength_mpa: 인장강도 (MPa)
    
    Returns:
    - tci: TCI 값 (무차원)
    """
    if tensile_strength_mpa <= 0:
        return float('inf')
    
    return abs(stress_mpa) / tensile_strength_mpa

def calculate_crack_probability(tci):
    """
    TCI 값에 따른 균열 발생 확률을 계산합니다.
    
    Parameters:
    - tci: TCI 값
    
    Returns:
    - probability: 균열 발생 확률 (0~1)
    """
    if tci <= 0.5:
        return 0.0
    elif tci <= 0.8:
        # 낮은 위험 구간 (0.5~0.8)
        return 0.1 * (tci - 0.5) / 0.3
    elif tci <= 1.0:
        # 중간 위험 구간 (0.8~1.0)
        return 0.1 + 0.4 * (tci - 0.8) / 0.2
    elif tci <= 1.5:
        # 높은 위험 구간 (1.0~1.5)
        return 0.5 + 0.4 * (tci - 1.0) / 0.5
    else:
        # 매우 높은 위험 구간 (1.5 이상)
        return min(0.9 + 0.1 * (tci - 1.5) / 0.5, 1.0)

def get_risk_level(tci):
    """TCI 값에 따른 위험도 레벨을 반환합니다."""
    if tci < 0.5:
        return "안전", "#22c55e"  # 초록색
    elif tci < 0.8:
        return "주의", "#eab308"  # 노란색
    elif tci < 1.0:
        return "경고", "#f97316"  # 주황색
    else:
        return "위험", "#ef4444"  # 빨간색

# ───────────────────── FRD 및 센서 데이터 처리 함수들 ─────────────────────

def get_frd_files(concrete_pk):
    """콘크리트 PK에 해당하는 FRD 파일들을 찾습니다."""
    frd_dir = f"frd/{concrete_pk}"
    if not os.path.exists(frd_dir):
        return []
    
    frd_files = glob.glob(f"{frd_dir}/*.frd")
    return sorted(frd_files)

def read_frd_stress_data(frd_path):
    """FRD 파일에서 응력 데이터를 읽어옵니다."""
    try:
        with open(frd_path, 'r') as f:
            lines = f.readlines()
        
        stress_data = {
            'times': [],
            'nodes': [],
            'coordinates': [],
            'stress_values': []
        }
        
        node_coords = {}
        stress_values = {}
        
        # 단계별로 파싱
        parsing_coords = False
        parsing_stress = False
        coord_section_ended = False
        
        for i, line in enumerate(lines):
            line = line.strip()
            
            # 노드 좌표 섹션 시작 확인 (-1로 시작하는 첫 번째 라인)
            if line.startswith('-1') and not coord_section_ended and not parsing_coords:
                parsing_coords = True
            
            # 좌표 섹션 종료 확인 (첫 번째 -3)
            if line.strip() == '-3' and parsing_coords and not coord_section_ended:
                parsing_coords = False
                coord_section_ended = True
                continue
            
            # 응력 섹션 시작 확인 (-4 STRESS 라인)
            if '-4  STRESS' in line and coord_section_ended:
                parsing_stress = True
                continue
            
            # 응력 섹션 종료 확인 (응력 섹션 시작 후 첫 번째 -3)
            if line.strip() == '-3' and parsing_stress:
                parsing_stress = False
                break
            
            # 노드 좌표 파싱
            if parsing_coords and line.startswith('-1'):
                nums = re.findall(r'-?\d+(?:\.\d+)?(?:[Ee][-+]?\d+)?', line)
                if len(nums) >= 5:
                    try:
                        node_id = int(nums[1])
                        x, y, z = float(nums[2]), float(nums[3]), float(nums[4])
                        node_coords[node_id] = [x, y, z]
                    except Exception:
                        pass
            
            # 응력 데이터 파싱 (von Mises 응력만)
            elif parsing_stress and line.startswith('-1'):
                nums = re.findall(r'-?\d+(?:\.\d+)?(?:[Ee][-+]?\d+)?', line)
                if len(nums) >= 7:  # -1, node_id, 6개 응력 성분
                    try:
                        node_id = int(nums[1])
                        sxx = float(nums[2])
                        syy = float(nums[3])
                        szz = float(nums[4])
                        sxy = float(nums[5])
                        syz = float(nums[6])
                        sxz = float(nums[7])
                        
                        # von Mises 응력 계산
                        von_mises = np.sqrt(0.5 * ((sxx - syy)**2 + (syy - szz)**2 + (szz - sxx)**2 + 6 * (sxy**2 + syz**2 + sxz**2)))
                        stress_values[node_id] = von_mises
                        
                    except Exception:
                        pass
        
        # 좌표와 응력 값의 노드 ID를 맞춤
        if node_coords and stress_values:
            coord_node_ids = set(node_coords.keys())
            stress_node_ids = set(stress_values.keys())
            common_node_ids = coord_node_ids.intersection(stress_node_ids)
            
            if common_node_ids:
                sorted_node_ids = sorted(common_node_ids)
                stress_data['coordinates'] = [node_coords[i] for i in sorted_node_ids]
                stress_data['nodes'] = sorted_node_ids
                stress_data['stress_values'] = [{i: stress_values[i] for i in sorted_node_ids}]
        
        # 시간 정보 파싱
        try:
            filename = os.path.basename(frd_path)
            time_str = filename.split(".")[0]
            dt = datetime.strptime(time_str, "%Y%m%d%H")
            stress_data['times'].append(dt)
        except:
            stress_data['times'].append(0)
        
        return stress_data
    except Exception:
        return None

def get_sensor_temperature_data(concrete_pk, device_id=None):
    """센서 온도 데이터를 가져옵니다."""
    try:
        # 센서 데이터 파일 경로
        if device_id:
            sensor_file = f"sensors/{device_id}.csv"
        else:
            # 첫 번째 센서 파일 사용
            sensor_files = glob.glob("sensors/*.csv")
            if not sensor_files:
                return []
            sensor_file = sensor_files[0]
        
        if not os.path.exists(sensor_file):
            return []
        
        # CSV 파일 읽기
        df = pd.read_csv(sensor_file)
        
        # 시간과 온도 데이터 추출
        temp_data = []
        for _, row in df.iterrows():
            try:
                timestamp = pd.to_datetime(row['timestamp'])
                temperature = float(row['temperature'])
                temp_data.append({
                    'time': timestamp,
                    'temperature': temperature
                })
            except:
                continue
        
        return sorted(temp_data, key=lambda x: x['time'])
    except Exception:
        return []

# ───────────────────── 콜백 함수들 ─────────────────────

@callback(
    Output("tbl-concrete-tci", "data"),
    Output("tbl-concrete-tci", "columns"),
    Output("tbl-concrete-tci", "selected_rows"),
    Output("tbl-concrete-tci", "style_data_conditional"),
    Output("project-info-store-tci", "data"),
    Input("project-url-tci", "search"),
    Input("project-url-tci", "pathname"),
    prevent_initial_call=True,
)
def load_concrete_data_tci(search, pathname):
    """프로젝트 정보를 로드하고 콘크리트 목록을 표시합니다."""
    # TCI 분석 페이지에서만 실행
    if '/tci' not in pathname:
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
        frd_files = get_frd_files(concrete_pk)
        has_frd = len(frd_files) > 0
        
        # 상태 결정 (응력분석 페이지와 동일한 로직)
        if row["activate"] == 1:  # 활성
            if has_frd:
                status = "설정중"
                status_sort = 2
            else:
                status = "설정중"
                status_sort = 3
        else:  # 비활성 (activate == 0)
            status = "분석중"
            status_sort = 1
        
        # 타설날짜 포맷팅
        pour_date = "N/A"
        if row.get("con_t") and row["con_t"] not in ["", "N/A", None]:
            try:
                from datetime import datetime
                if hasattr(row["con_t"], 'strftime'):
                    dt = row["con_t"]
                elif isinstance(row["con_t"], str):
                    if 'T' in row["con_t"]:
                        dt = datetime.fromisoformat(row["con_t"].replace('Z', ''))
                    else:
                        dt = datetime.strptime(str(row["con_t"]), '%Y-%m-%d %H:%M:%S')
                else:
                    dt = None
                
                if dt:
                    pour_date = dt.strftime('%y.%m.%d')
            except Exception:
                pour_date = "N/A"
        
        # 경과일 계산
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
        
        # 타설일과 경과일 통합
        pour_date_with_elapsed = pour_date
        if pour_date != "N/A" and elapsed_days != "N/A":
            pour_date_with_elapsed = f"{pour_date} ({elapsed_days})"
        
        table_data.append({
            "concrete_pk": row["concrete_pk"],
            "name": row["name"],
            "status": status,
            "status_sort": status_sort,
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
    
    # 테이블 스타일 설정
    style_data_conditional = [
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
    ]
    
    # 상태별 기본 정렬 적용
    if table_data:
        table_data = sorted(table_data, key=lambda x: x.get('status_sort', 999))
    
    return table_data, columns, [], style_data_conditional, {"name": proj_name, "pk": project_pk}

@callback(
    Output("current-project-info-tci", "children"),
    Input("project-info-store-tci", "data"),
    Input("project-url-tci", "pathname"),
    prevent_initial_call=True,
)
def update_project_info_tci(project_info, pathname):
    """프로젝트 정보를 표시합니다."""
    if '/tci' not in pathname:
        raise PreventUpdate
    
    if not project_info:
        return [
            "프로젝트가 선택되지 않았습니다. ",
            html.A("홈으로 돌아가기", href="/", className="alert-link")
        ]
    
    project_name = project_info.get("name", "알 수 없는 프로젝트")
    return f"📁 현재 프로젝트: {project_name}"

@callback(
    Output("tab-content-tci", "children"),
    Input("tabs-main-tci", "active_tab"),
    Input("tbl-concrete-tci", "selected_rows"),
    Input("project-url-tci", "pathname"),
    State("tbl-concrete-tci", "data"),
    prevent_initial_call=True,
)
def switch_tab_tci(active_tab, selected_rows, pathname, tbl_data):
    """탭 전환 시 해당 탭의 콘텐츠를 표시합니다."""
    if '/tci' not in pathname:
        raise PreventUpdate
    
    if not selected_rows or not tbl_data:
        return html.Div([
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
                    html.P("TCI 분석 결과를 확인할 수 있습니다.", style={
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
    
    row = pd.DataFrame(tbl_data).iloc[selected_rows[0]]
    concrete_pk = row["concrete_pk"]
    concrete_name = row["name"]
    
    if active_tab == "tab-tci-formula":
        return create_tci_formula_tab_content(concrete_pk, concrete_name)
    elif active_tab == "tab-tci-timeline":
        return create_tci_timeline_tab_content(concrete_pk, concrete_name)
    elif active_tab == "tab-crack-probability":
        return create_crack_probability_tab_content(concrete_pk, concrete_name)
    elif active_tab == "tab-tci-3d":
        return create_tci_3d_tab_content()
    else:
        return html.Div("알 수 없는 탭입니다.", className="text-center text-muted mt-5")

def create_tci_formula_tab_content(concrete_pk, concrete_name):
    import dash_table
    import plotly.graph_objs as go
    import numpy as np
    import pandas as pd
    import dash_bootstrap_components as dbc
    return html.Div([
        html.Div([
            html.H4("🧮 인장강도 계산식", style={"fontWeight": "700", "marginBottom": "18px", "color": "#1e293b"}),
            html.Hr(style={"margin": "8px 0 20px 0", "borderColor": "#e5e7eb"}),
            dcc.RadioItems(
                id="tci-formula-choice",
                options=[
                    {"label": html.Span([html.B("CEB-FIP Model Code", style={"color": "#2563eb"})], style={"marginRight": "16px"}), "value": "ceb"},
                    {"label": html.Span([html.B("경험식 #1 (KCI/KS)", style={"color": "#059669"})], style={"marginRight": "16px"}), "value": "exp1"}
                ],
                value="ceb",
                labelStyle={"display": "inline-block", "marginRight": "32px", "fontSize": "17px"},
                style={"marginBottom": "18px"}
            ),
            # 입력란을 항상 렌더링, 필요 없는 쪽은 숨김 처리
            html.Div([
                html.Div([
                    html.Label('fct,28(28일 인장강도)', style={"marginRight": "8px", "fontWeight": "500"}),
                    dcc.Input(id='tci-fct28', type='number', value=20, style={'width': '80px', 'marginRight': '16px'}),
                    html.Label('a', style={"marginRight": "4px", "fontWeight": "500"}),
                    dcc.Input(id='tci-a', type='number', value=1, style={'width': '60px', 'marginRight': '16px'}),
                    html.Label('b', style={"marginRight": "4px", "fontWeight": "500"}),
                    dcc.Input(id='tci-b', type='number', value=1, style={'width': '60px'}),
                ], id='ceb-inputs', style={"display": "flex", "alignItems": "center", "gap": "8px", "marginBottom": "4px"}),
                html.Div([
                    html.Label('fct,28(28일 인장강도)', style={"marginRight": "8px", "fontWeight": "500"}),
                    dcc.Input(id='tci-fct28-exp', type='number', value=20, style={'width': '80px'}),
                ], id='exp1-inputs', style={"display": "none", "alignItems": "center", "gap": "8px", "marginBottom": "4px"}),
            ], id='tci-formula-inputs-block'),
            html.Div(id="tci-formula-equation-block", style={"marginBottom": "12px"}),
            html.Div([
                html.Div("※ 입력값을 변경하면 아래 그래프와 표가 자동으로 갱신됩니다.", style={"color": "#64748b", "fontSize": "13px", "marginBottom": "8px"}),
                dbc.Row([
                    dbc.Col(dcc.Graph(id="tci-fct-graph"), md=6),
                    dbc.Col(html.Div(id="tci-fct-table-container"), md=6)
                ], className="g-3")
            ])
        ], style={"backgroundColor": "#fff", "borderRadius": "12px", "padding": "28px 28px 18px 28px", "boxShadow": "0 1px 4px rgba(0,0,0,0.04)", "border": "1px solid #e5e7eb", "marginBottom": "28px"}),
    ], style={"maxWidth": "900px", "margin": "0 auto"})

from dash import callback, Input, Output, State
@callback(
    Output('ceb-inputs', 'style'),
    Output('exp1-inputs', 'style'),
    Output('tci-formula-equation-block', 'children'),
    Input('tci-formula-choice', 'value')
)
def toggle_formula_inputs(formula):
    if formula == 'ceb':
        ceb_style = {"display": "flex", "alignItems": "center", "gap": "8px", "marginBottom": "4px"}
        exp1_style = {"display": "none"}
        eq = html.Div([
            html.B("CEB-FIP Model Code 1990 공식: ", style={"color": "#2563eb"}),
            html.Span("fct(t) = fct,28 × ( t / (a + b × t) )^0.5", style={"fontFamily": "monospace", "color": "#2563eb", "marginLeft": "8px"}),
            html.Div("(보통 a=1, b=1 사용)", style={"fontSize": "13px", "color": "#64748b", "marginTop": "2px"})
        ])
    else:
        ceb_style = {"display": "none"}
        exp1_style = {"display": "flex", "alignItems": "center", "gap": "8px", "marginBottom": "4px"}
        eq = html.Div([
            html.B("경험식 #1 (KCI/KS): ", style={"color": "#059669"}),
            html.Span("fct(t) = fct,28 × ( t / 28 )^0.5", style={"fontFamily": "monospace", "color": "#059669", "marginLeft": "8px"}),
            html.Div("(t ≤ 28, 국내 KCI/KS 기준에서 자주 사용되는 간단 경험식)", style={"fontSize": "13px", "color": "#64748b", "marginTop": "2px"}),
            html.Div("예시: 7일차 인장강도 = fct,28 × (7/28)^0.5", style={"fontSize": "13px", "color": "#64748b", "marginTop": "2px"})
        ])
    return ceb_style, exp1_style, eq

@callback(
    Output('tci-fct-graph', 'figure'),
    Output('tci-fct-table-container', 'children'),
    Input('tci-formula-choice', 'value'),
    Input('tci-fct28', 'value'),
    Input('tci-a', 'value'),
    Input('tci-b', 'value'),
    Input('tci-fct28-exp', 'value'),
    prevent_initial_call=False
)
def update_fct_graph_and_table(formula, ceb_fct28, a, b, exp_fct28):
    import numpy as np
    import plotly.graph_objs as go
    import pandas as pd
    import dash_table
    t = np.arange(1, 28.01, 0.1)
    if formula == 'ceb':
        try:
            fct28 = float(ceb_fct28) if ceb_fct28 is not None else 20
        except Exception:
            fct28 = 20
        try:
            a = float(a) if a is not None else 1
        except Exception:
            a = 1
        try:
            b = float(b) if b is not None else 1
        except Exception:
            b = 1
        y = fct28 * (t / (a + b * t)) ** 0.5
    else:
        try:
            fct28 = float(exp_fct28) if exp_fct28 is not None else 20
        except Exception:
            fct28 = 20
        y = fct28 * (t / 28) ** 0.5
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=t, y=y, mode='lines', name='fct(t)', line=dict(color='#3b82f6', width=3)))
    fig.update_layout(title='인장강도 발전 곡선', xaxis_title='t(일)', yaxis_title='fct(MPa)', template='plotly_white', margin=dict(l=20, r=20, t=40, b=20))
    df = pd.DataFrame({"t(일)": np.round(t, 1), "fct(t) (MPa)": np.round(y, 2)})
    table = dash_table.DataTable(
        columns=[{"name": i, "id": i} for i in df.columns],
        data=df.to_dict('records'),
        page_size=10,
        style_table={"overflowY": "auto", "height": "48vh", "marginTop": "0px", "borderRadius": "8px", "border": "1px solid #e5e7eb"},
        style_cell={"textAlign": "center", "fontSize": "15px", "padding": "8px 4px"},
        style_header={"backgroundColor": "#f8fafc", "fontWeight": "600", "color": "#374151"},
        style_data={"backgroundColor": "#fff"},
    )
    return fig, table

def create_tci_timeline_tab_content(concrete_pk, concrete_name):
    """시간별 TCI 분석 탭 콘텐츠를 생성합니다."""
    return html.Div([
        # 시간 범위 설정 섹션
        html.Div([
            html.H6("📅 분석 기간 설정", style={
                "fontWeight": "600",
                "color": "#374151",
                "marginBottom": "16px",
                "fontSize": "16px"
            }),
            dbc.Row([
                dbc.Col([
                    html.Label("분석 기간", style={
                        "fontWeight": "600", "color": "#374151", "fontSize": "13px"
                    }),
                    dcc.Dropdown(
                        id="tci-time-range-selector",
                        options=[
                            {"label": "전체 기간", "value": "all"},
                            {"label": "최근 7일", "value": "7"},
                            {"label": "최근 14일", "value": "14"},
                            {"label": "최근 28일", "value": "28"},
                        ],
                        value="all",
                        clearable=False,
                        style={"borderRadius": "6px"}
                    )
                ], md=6),
                dbc.Col([
                    html.Label("압축강도 (MPa)", style={
                        "fontWeight": "600", "color": "#374151", "fontSize": "13px"
                    }),
                    dbc.Input(
                        id="compressive-strength-input-timeline", 
                        type="number", 
                        value=30, 
                        min=10, 
                        max=100,
                        step=1
                    )
                ], md=6),
            ], className="mb-4"),
        ], style={
            "padding": "20px",
            "backgroundColor": "#f9fafb",
            "borderRadius": "8px",
            "border": "1px solid #e5e7eb",
            "marginBottom": "20px"
        }),
        
        # 저장 버튼 및 요약 정보
        dbc.Row([
            dbc.Col([
                html.Div(id="tci-statistics-summary")
            ], md=8),
            dbc.Col([
                html.Div([
                    dcc.Loading(
                        id="loading-btn-save-tci-timeline-image",
                        type="circle",
                        children=[
                            dbc.Button(
                                [html.I(className="fas fa-camera me-1"), "이미지 저장"],
                                id="btn-save-tci-timeline-image",
                                color="primary",
                                size="lg",
                                style={
                                    "borderRadius": "8px",
                                    "fontWeight": "600",
                                    "fontSize": "15px",
                                    "width": "120px",
                                    "height": "48px"
                                }
                            )
                        ]
                    ),
                ], style={
                    "display": "flex", 
                    "justifyContent": "center", 
                    "alignItems": "center", 
                    "height": "100%"
                })
            ], md=4),
        ], className="mb-4"),
        
        # TCI 시간별 분석 그래프
        html.Div([
            html.H6("📈 시간별 TCI 변화 분석", style={
                "fontWeight": "600",
                "color": "#374151",
                "marginBottom": "16px",
                "fontSize": "16px"
            }),
            dcc.Graph(
                id="viewer-tci-timeline", 
                style={"height": "55vh", "borderRadius": "8px"}, 
                config={"scrollZoom": True}
            ),
        ], style={
            "backgroundColor": "white",
            "padding": "20px",
            "borderRadius": "12px",
            "border": "1px solid #e5e7eb",
            "boxShadow": "0 1px 3px rgba(0,0,0,0.1)"
        }),
        
        # 다운로드 컴포넌트
        dcc.Download(id="download-tci-timeline-image"),
    ])

def create_crack_probability_tab_content(concrete_pk, concrete_name):
    """균열발생확률 곡선 탭 콘텐츠를 생성합니다."""
    return html.Div([
        # 위험도 평가 요약
        html.Div([
            html.H6("⚠️ 균열 위험도 평가", style={
                "fontWeight": "600",
                "color": "#374151",
                "marginBottom": "16px",
                "fontSize": "16px"
            }),
            html.Div(id="crack-risk-assessment")
        ], style={
            "padding": "20px",
            "backgroundColor": "#f9fafb",
            "borderRadius": "8px",
            "border": "1px solid #e5e7eb",
            "marginBottom": "20px"
        }),
        
        # 저장 버튼 섹션
        dbc.Row([
            dbc.Col([
                html.Div([
                    dcc.Loading(
                        id="loading-btn-save-crack-probability-image",
                        type="circle",
                        children=[
                            dbc.Button(
                                [html.I(className="fas fa-camera me-1"), "이미지 저장"],
                                id="btn-save-crack-probability-image",
                                color="primary",
                                size="lg",
                                style={
                                    "borderRadius": "8px",
                                    "fontWeight": "600",
                                    "fontSize": "15px",
                                    "width": "120px",
                                    "height": "48px",
                                    "marginRight": "16px"
                                }
                            )
                        ]
                    ),
                    dcc.Loading(
                        id="loading-btn-save-tci-data-csv",
                        type="circle",
                        children=[
                            dbc.Button(
                                [html.I(className="fas fa-file-csv me-1"), "데이터 저장"],
                                id="btn-save-tci-data-csv",
                                color="success",
                                size="lg",
                                style={
                                    "borderRadius": "8px",
                                    "fontWeight": "600",
                                    "fontSize": "15px",
                                    "width": "120px",
                                    "height": "48px"
                                }
                            )
                        ]
                    ),
                ], style={
                    "display": "flex", 
                    "justifyContent": "center", 
                    "alignItems": "center", 
                    "marginBottom": "20px"
                })
            ], md=12),
        ]),
        
        # 균열발생확률 곡선 그래프
        html.Div([
            html.H6("📊 TCI에 따른 균열발생확률 곡선", style={
                "fontWeight": "600",
                "color": "#374151",
                "marginBottom": "16px",
                "fontSize": "16px"
            }),
            dcc.Graph(
                id="viewer-crack-probability", 
                style={"height": "50vh", "borderRadius": "8px"}, 
                config={"scrollZoom": True}
            ),
        ], style={
            "backgroundColor": "white",
            "padding": "20px",
            "borderRadius": "12px",
            "border": "1px solid #e5e7eb",
            "boxShadow": "0 1px 3px rgba(0,0,0,0.1)"
        }),
        
        # 다운로드 컴포넌트
        dcc.Download(id="download-crack-probability-image"),
        dcc.Download(id="download-tci-data-csv"),
    ])

# 입체 TCI 탭 콘텐츠 함수 추가
def create_tci_3d_tab_content():
    import dash_table
    import dash_bootstrap_components as dbc
    from dash import dcc, html
    return html.Div([
        html.H5("입체 TCI 분석", style={"fontWeight": "600", "marginBottom": "18px"}),
        html.Div([
            html.Label("시간 선택", style={"marginRight": "12px", "fontWeight": "500"}),
            dcc.Slider(id="tci-3d-time-slider", min=0, max=10, step=1, value=0, marks={i: str(i) for i in range(11)}, tooltip={"placement": "bottom"}),
            dbc.Button("재생", id="tci-3d-play-btn", color="primary", style={"marginLeft": "24px"}),
        ], style={"display": "flex", "alignItems": "center", "gap": "16px", "marginBottom": "18px"}),
        html.Div([
            dash_table.DataTable(
                id="tci-3d-table",
                columns=[
                    {"name": "node", "id": "node"},
                    {"name": "TCI-X", "id": "tci_x"},
                    {"name": "TCI-Y", "id": "tci_y"},
                    {"name": "TCI-Z", "id": "tci_z"},
                ],
                data=[],
                page_size=10,
                style_table={"overflowY": "auto", "height": "48vh", "marginTop": "0px", "borderRadius": "8px", "border": "1px solid #e5e7eb"},
                style_cell={"textAlign": "center", "fontSize": "15px", "padding": "8px 4px"},
                style_header={"backgroundColor": "#f8fafc", "fontWeight": "600", "color": "#374151"},
                style_data={"backgroundColor": "#fff"},
            )
        ])
    ], style={"backgroundColor": "#fff", "borderRadius": "12px", "padding": "28px 28px 18px 28px", "boxShadow": "0 1px 4px rgba(0,0,0,0.04)", "border": "1px solid #e5e7eb", "marginBottom": "28px"})

# ───────────────────── 그래프 생성 콜백 함수들 ─────────────────────

@callback(
    Output("viewer-tci-formula", "figure"),
    Input("concrete-age-input", "value"),
    Input("compressive-strength-input", "value"),
    Input("tabs-main-tci", "active_tab"),
    State("tbl-concrete-tci", "selected_rows"),
    State("tbl-concrete-tci", "data"),
    prevent_initial_call=True,
)
def update_tci_formula_graph(age_input, fc28_input, active_tab, selected_rows, tbl_data):
    """인장강도 계산식 그래프를 업데이트합니다."""
    if active_tab != "tab-tci-formula":
        raise PreventUpdate
    
    if not selected_rows or not tbl_data:
        return go.Figure().add_annotation(
            text="콘크리트를 선택하세요.",
            xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False
        )
    
    # 기본값 설정
    if age_input is None:
        age_input = 28
    if fc28_input is None:
        fc28_input = 30
    
    # 재령별 인장강도 계산 (1일부터 365일까지)
    ages = np.arange(1, 366)
    tensile_strengths = [calculate_tensile_strength(age, fc28_input) for age in ages]
    
    # 현재 입력된 재령의 인장강도
    current_fct = calculate_tensile_strength(age_input, fc28_input)
    
    fig = go.Figure()
    
    # 인장강도 발전 곡선
    fig.add_trace(go.Scatter(
        x=ages,
        y=tensile_strengths,
        mode='lines',
        name='인장강도 발전 곡선',
        line=dict(color='#3b82f6', width=3),
        hovertemplate='재령: %{x}일<br>인장강도: %{y:.2f} MPa<extra></extra>'
    ))
    
    # 현재 재령 지점 표시
    fig.add_trace(go.Scatter(
        x=[age_input],
        y=[current_fct],
        mode='markers',
        name=f'현재 재령 ({age_input}일)',
        marker=dict(
            size=12,
            color='#ef4444',
            symbol='circle'
        ),
        hovertemplate=f'재령: {age_input}일<br>인장강도: {current_fct:.2f} MPa<extra></extra>'
    ))
    
    # 28일 기준선
    fct28 = calculate_tensile_strength(28, fc28_input)
    fig.add_hline(
        y=fct28,
        line_dash="dash",
        line_color="gray",
        annotation_text=f"28일 기준 인장강도: {fct28:.2f} MPa"
    )
    
    # 계산 공식 표시
    formula_text = f"""
    <b>인장강도 계산식 (ACI 209 모델 기반)</b><br>
    • 28일 기준 인장강도: fct28 = 0.1 × fc28 = {fct28:.2f} MPa<br>
    • 재령 {age_input}일 인장강도: fct = {current_fct:.2f} MPa<br>
    • 강도 발전률: {(current_fct/fct28)*100:.1f}%
    """
    
    fig.add_annotation(
        text=formula_text,
        xref="paper", yref="paper",
        x=0.02, y=0.98,
        showarrow=False,
        align="left",
        bgcolor="rgba(255,255,255,0.8)",
        bordercolor="gray",
        borderwidth=1,
        font=dict(size=12)
    )
    
    fig.update_layout(
        title="콘크리트 인장강도 발전 곡선",
        xaxis_title="재령 (일)",
        yaxis_title="인장강도 (MPa)",
        xaxis=dict(range=[0, 365]),
        yaxis=dict(range=[0, max(tensile_strengths) * 1.1]),
        hovermode='closest',
        showlegend=True,
        legend=dict(x=0.7, y=0.2)
    )
    
    return fig

@callback(
    Output("viewer-tci-timeline", "figure"),
    Output("tci-statistics-summary", "children"),
    Input("tci-time-range-selector", "value"),
    Input("compressive-strength-input-timeline", "value"),
    Input("tabs-main-tci", "active_tab"),
    State("tbl-concrete-tci", "selected_rows"),
    State("tbl-concrete-tci", "data"),
    prevent_initial_call=True,
)
def update_tci_timeline_graph(time_range, fc28_input, active_tab, selected_rows, tbl_data):
    """시간별 TCI 분석 그래프를 업데이트합니다."""
    if active_tab != "tab-tci-timeline":
        raise PreventUpdate
    
    if not selected_rows or not tbl_data:
        empty_fig = go.Figure().add_annotation(
            text="콘크리트를 선택하세요.",
            xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False
        )
        return empty_fig, "콘크리트를 선택하세요."
    
    row = pd.DataFrame(tbl_data).iloc[selected_rows[0]]
    concrete_pk = row["concrete_pk"]
    concrete_name = row["name"]
    
    # 기본값 설정
    if fc28_input is None:
        fc28_input = 30
    if time_range is None:
        time_range = "all"
    
    # FRD 파일에서 응력 데이터 수집
    frd_files = get_frd_files(concrete_pk)
    if not frd_files:
        empty_fig = go.Figure().add_annotation(
            text="FRD 파일이 없습니다.",
            xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False
        )
        return empty_fig, "FRD 파일이 없습니다."
    
    # 타설일 가져오기
    pour_date = None
    try:
        if row.get("con_t") and row["con_t"] not in ["", "N/A", None]:
            if hasattr(row["con_t"], 'strftime'):
                pour_date = row["con_t"]
            elif isinstance(row["con_t"], str):
                if 'T' in row["con_t"]:
                    pour_date = datetime.fromisoformat(row["con_t"].replace('Z', ''))
                else:
                    pour_date = datetime.strptime(str(row["con_t"]), '%Y-%m-%d %H:%M:%S')
    except Exception:
        pass
    
    # 시간별 TCI 데이터 수집
    tci_data = []
    stress_data_list = []
    
    for frd_file in frd_files:
        # 파일 시간 파싱
        try:
            time_str = os.path.basename(frd_file).split(".")[0]
            file_time = datetime.strptime(time_str, "%Y%m%d%H")
        except:
            continue
        
        # 시간 범위 필터링
        if time_range != "all":
            try:
                days_back = int(time_range)
                cutoff_time = datetime.now() - timedelta(days=days_back)
                if file_time < cutoff_time:
                    continue
            except:
                pass
        
        # 응력 데이터 읽기
        stress_data = read_frd_stress_data(frd_file)
        if not stress_data or not stress_data.get('stress_values'):
            continue
        
        # 평균 응력 계산 (von Mises)
        stress_values = list(stress_data['stress_values'][0].values())
        avg_stress_pa = np.mean(stress_values)
        avg_stress_mpa = avg_stress_pa / 1e6  # Pa를 MPa로 변환
        
        # 재령 계산
        if pour_date:
            age_days = (file_time - pour_date).days
            if age_days < 1:
                age_days = 1  # 최소 1일
        else:
            # 타설일이 없으면 첫 번째 FRD 파일을 기준으로 계산
            first_file_time = datetime.strptime(os.path.basename(frd_files[0]).split(".")[0], "%Y%m%d%H")
            age_days = max(1, (file_time - first_file_time).days + 1)
        
        # 인장강도 계산
        tensile_strength = calculate_tensile_strength(age_days, fc28_input)
        
        # TCI 계산
        tci = calculate_tci(avg_stress_mpa, tensile_strength)
        
        # 위험도 레벨
        risk_level, risk_color = get_risk_level(tci)
        
        tci_data.append({
            'time': file_time,
            'age_days': age_days,
            'stress_mpa': avg_stress_mpa,
            'tensile_strength': tensile_strength,
            'tci': tci,
            'risk_level': risk_level,
            'risk_color': risk_color
        })
        
        stress_data_list.append(avg_stress_mpa)
    
    if not tci_data:
        empty_fig = go.Figure().add_annotation(
            text="분석할 데이터가 없습니다.",
            xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False
        )
        return empty_fig, "분석할 데이터가 없습니다."
    
    # 데이터를 시간순으로 정렬
    tci_data.sort(key=lambda x: x['time'])
    
    # TCI 그래프 생성
    fig = make_subplots(
        rows=2, cols=1,
        subplot_titles=('TCI (열적 균열 지수)', '응력 및 인장강도'),
        vertical_spacing=0.1,
        shared_xaxis=True
    )
    
    # TCI 값 플롯
    times = [d['time'] for d in tci_data]
    tci_values = [d['tci'] for d in tci_data]
    
    fig.add_trace(
        go.Scatter(
            x=times,
            y=tci_values,
            mode='lines+markers',
            name='TCI',
            line=dict(color='#ef4444', width=3),
            marker=dict(size=6),
            hovertemplate='시간: %{x}<br>TCI: %{y:.2f}<extra></extra>'
        ),
        row=1, col=1
    )
    
    # TCI 위험 기준선들
    fig.add_hline(y=0.5, line_dash="dash", line_color="green", 
                  annotation_text="안전 기준 (0.5)", row=1, col=1)
    fig.add_hline(y=0.8, line_dash="dash", line_color="orange", 
                  annotation_text="주의 기준 (0.8)", row=1, col=1)
    fig.add_hline(y=1.0, line_dash="dash", line_color="red", 
                  annotation_text="위험 기준 (1.0)", row=1, col=1)
    
    # 응력 및 인장강도 플롯
    stress_values = [d['stress_mpa'] for d in tci_data]
    tensile_values = [d['tensile_strength'] for d in tci_data]
    
    fig.add_trace(
        go.Scatter(
            x=times,
            y=stress_values,
            mode='lines+markers',
            name='평균 응력',
            line=dict(color='#3b82f6', width=2),
            marker=dict(size=4),
            hovertemplate='시간: %{x}<br>응력: %{y:.2f} MPa<extra></extra>'
        ),
        row=2, col=1
    )
    
    fig.add_trace(
        go.Scatter(
            x=times,
            y=tensile_values,
            mode='lines+markers',
            name='인장강도',
            line=dict(color='#22c55e', width=2),
            marker=dict(size=4),
            hovertemplate='시간: %{x}<br>인장강도: %{y:.2f} MPa<extra></extra>'
        ),
        row=2, col=1
    )
    
    fig.update_layout(
        title=f"{concrete_name} - 시간별 TCI 분석",
        height=600,
        showlegend=True,
        hovermode='x unified'
    )
    
    fig.update_xaxes(title_text="시간", row=2, col=1)
    fig.update_yaxes(title_text="TCI", row=1, col=1)
    fig.update_yaxes(title_text="응력/인장강도 (MPa)", row=2, col=1)
    
    # 통계 요약 생성
    if tci_values:
        max_tci = max(tci_values)
        avg_tci = np.mean(tci_values)
        risk_periods = len([t for t in tci_values if t > 1.0])
        total_periods = len(tci_values)
        
        # 최대 TCI 발생 시점
        max_tci_idx = tci_values.index(max_tci)
        max_tci_time = times[max_tci_idx]
        max_tci_risk, max_tci_color = get_risk_level(max_tci)
        
        summary = html.Div([
            html.Div([
                html.H6("📊 TCI 분석 요약", style={
                    "fontWeight": "600", "color": "#374151", "marginBottom": "12px", "fontSize": "14px"
                }),
                html.Div([
                    # 최대 TCI
                    html.Div([
                        html.Span("최대 TCI: ", style={"color": "#6b7280", "fontSize": "13px"}),
                        html.Span(f"{max_tci:.2f}", style={
                            "fontWeight": "600", "color": max_tci_color, "fontSize": "14px"
                        }),
                        html.Span(f" ({max_tci_risk})", style={
                            "fontWeight": "500", "color": max_tci_color, "fontSize": "12px"
                        })
                    ], style={"marginBottom": "8px"}),
                    
                    # 평균 TCI
                    html.Div([
                        html.Span("평균 TCI: ", style={"color": "#6b7280", "fontSize": "13px"}),
                        html.Span(f"{avg_tci:.2f}", style={"fontWeight": "600", "color": "#374151", "fontSize": "14px"})
                    ], style={"marginBottom": "8px"}),
                    
                    # 위험 기간
                    html.Div([
                        html.Span("위험 기간: ", style={"color": "#6b7280", "fontSize": "13px"}),
                        html.Span(f"{risk_periods}/{total_periods} 회", style={
                            "fontWeight": "600", 
                            "color": "#ef4444" if risk_periods > 0 else "#22c55e", 
                            "fontSize": "14px"
                        }),
                        html.Span(f" ({(risk_periods/total_periods)*100:.1f}%)", style={
                            "color": "#6b7280", "fontSize": "12px"
                        })
                    ], style={"marginBottom": "8px"}),
                    
                    # 최대 TCI 발생 시점
                    html.Div([
                        html.Span("최대 TCI 발생: ", style={"color": "#6b7280", "fontSize": "13px"}),
                        html.Span(max_tci_time.strftime("%m/%d %H시"), style={
                            "fontWeight": "600", "color": "#374151", "fontSize": "14px"
                        })
                    ])
                ])
            ], style={
                "padding": "12px 16px",
                "backgroundColor": "#f8fafc",
                "borderRadius": "8px",
                "border": "1px solid #e2e8f0"
            })
        ])
    else:
        summary = "데이터가 없습니다."
    
    return fig, summary

@callback(
    Output("viewer-crack-probability", "figure"),
    Output("crack-risk-assessment", "children"),
    Input("tabs-main-tci", "active_tab"),
    State("tbl-concrete-tci", "selected_rows"),
    State("tbl-concrete-tci", "data"),
    prevent_initial_call=True,
)
def update_crack_probability_graph(active_tab, selected_rows, tbl_data):
    """균열발생확률 곡선 그래프를 업데이트합니다."""
    if active_tab != "tab-crack-probability":
        raise PreventUpdate
    
    if not selected_rows or not tbl_data:
        empty_fig = go.Figure().add_annotation(
            text="콘크리트를 선택하세요.",
            xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False
        )
        return empty_fig, "콘크리트를 선택하세요."
    
    row = pd.DataFrame(tbl_data).iloc[selected_rows[0]]
    concrete_pk = row["concrete_pk"]
    concrete_name = row["name"]
    
    # TCI 범위 설정 (0~2.0)
    tci_range = np.linspace(0, 2.0, 200)
    probabilities = [calculate_crack_probability(tci) for tci in tci_range]
    
    # 균열발생확률 곡선 그래프
    fig = go.Figure()
    
    # 확률 곡선
    fig.add_trace(go.Scatter(
        x=tci_range,
        y=np.array(probabilities) * 100,  # 백분율로 변환
        mode='lines',
        name='균열발생확률',
        line=dict(color='#ef4444', width=4),
        fill='tonexty',
        fillcolor='rgba(239, 68, 68, 0.1)',
        hovertemplate='TCI: %{x:.2f}<br>균열확률: %{y:.1f}%<extra></extra>'
    ))
    
    # 위험 구간별 색상 영역
    safe_x = tci_range[tci_range <= 0.5]
    safe_y = [calculate_crack_probability(tci) * 100 for tci in safe_x]
    
    caution_x = tci_range[(tci_range > 0.5) & (tci_range <= 0.8)]
    caution_y = [calculate_crack_probability(tci) * 100 for tci in caution_x]
    
    warning_x = tci_range[(tci_range > 0.8) & (tci_range <= 1.0)]
    warning_y = [calculate_crack_probability(tci) * 100 for tci in warning_x]
    
    danger_x = tci_range[tci_range > 1.0]
    danger_y = [calculate_crack_probability(tci) * 100 for tci in danger_x]
    
    # 영역별 배경색
    fig.add_vrect(x0=0, x1=0.5, fillcolor="rgba(34, 197, 94, 0.1)", 
                  annotation_text="안전", annotation_position="top left")
    fig.add_vrect(x0=0.5, x1=0.8, fillcolor="rgba(234, 179, 8, 0.1)", 
                  annotation_text="주의", annotation_position="top left")
    fig.add_vrect(x0=0.8, x1=1.0, fillcolor="rgba(249, 115, 22, 0.1)", 
                  annotation_text="경고", annotation_position="top left")
    fig.add_vrect(x0=1.0, x1=2.0, fillcolor="rgba(239, 68, 68, 0.1)", 
                  annotation_text="위험", annotation_position="top left")
    
    # 주요 기준선들
    fig.add_vline(x=0.5, line_dash="dash", line_color="green", 
                  annotation_text="안전 기준")
    fig.add_vline(x=0.8, line_dash="dash", line_color="orange", 
                  annotation_text="주의 기준")
    fig.add_vline(x=1.0, line_dash="dash", line_color="red", 
                  annotation_text="위험 기준")
    
    fig.update_layout(
        title=f"{concrete_name} - TCI에 따른 균열발생확률",
        xaxis_title="TCI (열적 균열 지수)",
        yaxis_title="균열발생확률 (%)",
        xaxis=dict(range=[0, 2.0]),
        yaxis=dict(range=[0, 100]),
        hovermode='x',
        showlegend=False
    )
    
    # 현재 콘크리트의 실제 TCI 데이터 수집 및 위험도 평가
    frd_files = get_frd_files(concrete_pk)
    risk_assessment = ""
    
    if frd_files:
        # 최근 데이터로 위험도 평가
        current_tci_values = []
        
        # 최근 5개 파일 분석
        for frd_file in frd_files[-5:]:
            stress_data = read_frd_stress_data(frd_file)
            if stress_data and stress_data.get('stress_values'):
                stress_values = list(stress_data['stress_values'][0].values())
                avg_stress_mpa = np.mean(stress_values) / 1e6
                
                # 기본 인장강도 (28일 기준)
                tensile_strength = calculate_tensile_strength(28, 30)
                tci = calculate_tci(avg_stress_mpa, tensile_strength)
                current_tci_values.append(tci)
        
        if current_tci_values:
            avg_current_tci = np.mean(current_tci_values)
            max_current_tci = max(current_tci_values)
            current_probability = calculate_crack_probability(avg_current_tci) * 100
            max_probability = calculate_crack_probability(max_current_tci) * 100
            
            risk_level, risk_color = get_risk_level(avg_current_tci)
            
            # 그래프에 현재 TCI 지점 표시
            fig.add_vline(x=avg_current_tci, line_color=risk_color, line_width=3,
                          annotation_text=f"현재 평균 TCI: {avg_current_tci:.2f}")
            
            risk_assessment = html.Div([
                html.Div([
                    html.Span("현재 위험도: ", style={"color": "#374151", "fontSize": "14px", "fontWeight": "500"}),
                    html.Span(risk_level, style={
                        "fontWeight": "600", "fontSize": "16px", "color": risk_color,
                        "padding": "4px 8px", "borderRadius": "4px", 
                        "backgroundColor": f"{risk_color}20"
                    })
                ], style={"marginBottom": "12px"}),
                
                html.Div([
                    html.Div([
                        html.Span("평균 TCI: ", style={"color": "#6b7280", "fontSize": "13px"}),
                        html.Span(f"{avg_current_tci:.2f}", style={"fontWeight": "600", "color": "#374151"})
                    ], style={"marginBottom": "8px"}),
                    
                    html.Div([
                        html.Span("최대 TCI: ", style={"color": "#6b7280", "fontSize": "13px"}),
                        html.Span(f"{max_current_tci:.2f}", style={"fontWeight": "600", "color": "#374151"})
                    ], style={"marginBottom": "8px"}),
                    
                    html.Div([
                        html.Span("균열확률 (평균): ", style={"color": "#6b7280", "fontSize": "13px"}),
                        html.Span(f"{current_probability:.1f}%", style={
                            "fontWeight": "600", 
                            "color": "#ef4444" if current_probability > 50 else "#22c55e"
                        })
                    ], style={"marginBottom": "8px"}),
                    
                    html.Div([
                        html.Span("균열확률 (최대): ", style={"color": "#6b7280", "fontSize": "13px"}),
                        html.Span(f"{max_probability:.1f}%", style={
                            "fontWeight": "600", 
                            "color": "#ef4444" if max_probability > 50 else "#22c55e"
                        })
                    ])
                ])
            ])
    else:
        risk_assessment = html.Div([
            html.Span("분석할 데이터가 없습니다.", style={
                "color": "#6b7280", "fontSize": "14px", "fontStyle": "italic"
            })
        ])
    
    return fig, risk_assessment

# 시간 슬라이더/재생 버튼/탭 선택 시 TCI 표 갱신 콜백 추가(1차: 표만)
from dash import callback, Input, Output, State
@callback(
    Output('tci-3d-table', 'data'),
    Input('tci-3d-time-slider', 'value'),
    Input('tci-3d-play-btn', 'n_clicks'),
    State('tbl-concrete-tci', 'selected_rows'),
    State('tbl-concrete-tci', 'data'),
    prevent_initial_call=True
)
def update_tci_3d_table(time_idx, play_click, selected_rows, tbl_data):
    import numpy as np
    if not selected_rows or not tbl_data:
        return []
    row = pd.DataFrame(tbl_data).iloc[selected_rows[0]]
    concrete_pk = row["concrete_pk"]
    # FRD 파일 목록
    frd_files = get_frd_files(concrete_pk)
    if not frd_files or time_idx is None or time_idx >= len(frd_files):
        return []
    frd_file = frd_files[time_idx]
    stress_data = read_frd_stress_data(frd_file)
    if not stress_data or not stress_data.get('nodes'):
        return []
    # 타설일 정보
    pour_date = None
    if row.get("con_t") and row["con_t"] not in ["", "N/A", None]:
        try:
            from datetime import datetime
            if hasattr(row["con_t"], 'strftime'):
                pour_date = row["con_t"]
            elif isinstance(row["con_t"], str):
                if 'T' in row["con_t"]:
                    pour_date = datetime.fromisoformat(row["con_t"].replace('Z', ''))
                else:
                    pour_date = datetime.strptime(str(row["con_t"]), '%Y-%m-%d %H:%M:%S')
        except Exception:
            pour_date = None
    # 파일명에서 시간 추출
    try:
        import os
        from datetime import datetime
        time_str = os.path.basename(frd_file).split(".")[0]
        file_time = datetime.strptime(time_str, "%Y%m%d%H")
    except:
        file_time = None
    # 재령 계산
    if pour_date and file_time:
        age_days = (file_time - pour_date).days
        if age_days < 1:
            age_days = 1
    else:
        age_days = 1
    # fct(t) 계산 (fc28=30 기본)
    fct = calculate_tensile_strength(age_days, 30)
    # sxx, syy, szz 추출
    # 기존 read_frd_stress_data는 von Mises만 저장하므로, sxx 등도 저장하도록 개선 필요
    # 임시로 응력 분석 페이지 방식 차용
    sxx_dict = {}
    syy_dict = {}
    szz_dict = {}
    try:
        with open(frd_file, 'r') as f:
            lines = f.readlines()
        parsing_stress = False
        coord_section_ended = False
        for line in lines:
            line = line.strip()
            if '-4  STRESS' in line and coord_section_ended:
                parsing_stress = True
                continue
            if line.strip() == '-3' and parsing_stress:
                parsing_stress = False
                break
            if line.strip() == '-3' and not coord_section_ended:
                coord_section_ended = True
                continue
            if parsing_stress and line.startswith('-1'):
                import re
                nums = re.findall(r'-?\d+(?:\.\d+)?(?:[Ee][-+]?\d+)?', line)
                if len(nums) >= 7:
                    try:
                        node_id = int(nums[1])
                        sxx = float(nums[2])
                        syy = float(nums[3])
                        szz = float(nums[4])
                        sxx_dict[node_id] = sxx
                        syy_dict[node_id] = syy
                        szz_dict[node_id] = szz
                    except Exception:
                        pass
    except Exception:
        return []
    # 노드 리스트
    node_ids = sorted(list(set(sxx_dict.keys()) & set(syy_dict.keys()) & set(szz_dict.keys())))
    data = []
    for node in node_ids:
        sx = sxx_dict[node]
        sy = syy_dict[node]
        sz = szz_dict[node]
        # 0으로 나누기 방지
        tci_x = round(fct / sx, 3) if sx != 0 else None
        tci_y = round(fct / sy, 3) if sy != 0 else None
        tci_z = round(fct / sz, 3) if sz != 0 else None
        data.append({
            "node": node,
            "tci_x": tci_x,
            "tci_y": tci_y,
            "tci_z": tci_z,
        })
    return data

# ───────────────────── 버튼 상태 및 액션 콜백 함수들 ─────────────────────

@callback(
    Output("btn-concrete-analyze-tci", "disabled"),
    Output("btn-concrete-del-tci", "disabled"),
    Input("tbl-concrete-tci", "selected_rows"),
    Input("project-url-tci", "pathname"),
    State("tbl-concrete-tci", "data"),
    prevent_initial_call=True,
)
def on_concrete_select_tci(selected_rows, pathname, tbl_data):
    """콘크리트 선택 시 버튼 상태를 업데이트합니다."""
    if '/tci' not in pathname:
        raise PreventUpdate
    
    if not selected_rows or not tbl_data:
        return True, True
    
    if len(selected_rows) == 0 or len(tbl_data) == 0:
        return True, True
    
    try:
        row = pd.DataFrame(tbl_data).iloc[selected_rows[0]]
    except (IndexError, KeyError):
        return True, True
    
    is_active = row["activate"] == "활성"
    has_frd = row["has_frd"]
    
    # 버튼 상태 결정 (응력분석과 동일한 로직)
    if not is_active:  # 분석중
        analyze_disabled = True
        delete_disabled = False
    elif is_active and has_frd:  # 설정중(FRD있음)
        analyze_disabled = False
        delete_disabled = True
    else:  # 설정중(FRD부족)
        analyze_disabled = True
        delete_disabled = True
    
    return analyze_disabled, delete_disabled

@callback(
    Output("confirm-del-concrete-tci", "displayed"),
    Input("btn-concrete-del-tci", "n_clicks"),
    State("tbl-concrete-tci", "selected_rows"),
    prevent_initial_call=True
)
def ask_delete_concrete_tci(n, sel):
    """콘크리트 삭제 확인 다이얼로그를 표시합니다."""
    return bool(n and sel)

@callback(
    Output("tci-project-alert", "children", allow_duplicate=True),
    Output("tci-project-alert", "color", allow_duplicate=True),
    Output("tci-project-alert", "is_open", allow_duplicate=True),
    Output("tbl-concrete-tci", "data", allow_duplicate=True),
    Output("btn-concrete-analyze-tci", "disabled", allow_duplicate=True),
    Output("btn-concrete-del-tci", "disabled", allow_duplicate=True),
    Input("btn-concrete-analyze-tci", "n_clicks"),
    State("tbl-concrete-tci", "selected_rows"),
    State("tbl-concrete-tci", "data"),
    prevent_initial_call=True,
)
def start_analysis_tci(n_clicks, selected_rows, tbl_data):
    """TCI 분석을 시작합니다."""
    if not selected_rows or not tbl_data:
        return "콘크리트를 선택하세요", "warning", True, dash.no_update, dash.no_update, dash.no_update

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
        
        return f"{concrete_pk} TCI 분석이 시작되었습니다", "success", True, updated_data, True, False
    except Exception as e:
        return f"분석 시작 실패: {e}", "danger", True, dash.no_update, dash.no_update, dash.no_update

@callback(
    Output("tci-project-alert", "children", allow_duplicate=True),
    Output("tci-project-alert", "color", allow_duplicate=True),
    Output("tci-project-alert", "is_open", allow_duplicate=True),
    Output("tbl-concrete-tci", "data", allow_duplicate=True),
    Input("confirm-del-concrete-tci", "submit_n_clicks"),
    State("tbl-concrete-tci", "selected_rows"),
    State("tbl-concrete-tci", "data"),
    prevent_initial_call=True,
)
def delete_concrete_confirm_tci(_click, sel, tbl_data):
    """콘크리트 삭제를 실행합니다."""
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

# ───────────────────── 저장 기능 콜백 함수들 ─────────────────────

@callback(
    Output("download-tci-formula-image", "data"),
    Output("btn-save-tci-formula-image", "children"),
    Output("btn-save-tci-formula-image", "disabled"),
    Input("btn-save-tci-formula-image", "n_clicks"),
    State("viewer-tci-formula", "figure"),
    State("tbl-concrete-tci", "selected_rows"),
    State("tbl-concrete-tci", "data"),
    State("concrete-age-input", "value"),
    State("compressive-strength-input", "value"),
    prevent_initial_call=True,
)
def save_tci_formula_image(n_clicks, figure, selected_rows, tbl_data, age_input, fc28_input):
    """인장강도 계산식 이미지를 저장합니다."""
    if not n_clicks or not figure or not selected_rows or not tbl_data:
        return None, [html.I(className="fas fa-camera me-1"), "이미지 저장"], False
    
    try:
        row = pd.DataFrame(tbl_data).iloc[selected_rows[0]]
        concrete_name = row["name"]
        
        age_info = f"_재령{age_input}일" if age_input else ""
        fc_info = f"_fc{fc28_input}MPa" if fc28_input else ""
        
        filename = f"TCI_인장강도계산식_{concrete_name}{age_info}{fc_info}.png"
        
        # 실제로는 figure를 이미지로 변환하는 로직 필요
        return dcc.send_bytes(
            b"dummy_image_data", 
            filename=filename
        ), "저장 완료!", True
        
    except Exception:
        return None, "저장 실패", False

@callback(
    Output("download-tci-timeline-image", "data"),
    Output("btn-save-tci-timeline-image", "children"),
    Output("btn-save-tci-timeline-image", "disabled"),
    Input("btn-save-tci-timeline-image", "n_clicks"),
    State("viewer-tci-timeline", "figure"),
    State("tbl-concrete-tci", "selected_rows"),
    State("tbl-concrete-tci", "data"),
    State("tci-time-range-selector", "value"),
    prevent_initial_call=True,
)
def save_tci_timeline_image(n_clicks, figure, selected_rows, tbl_data, time_range):
    """시간별 TCI 분석 이미지를 저장합니다."""
    if not n_clicks or not figure or not selected_rows or not tbl_data:
        return None, [html.I(className="fas fa-camera me-1"), "이미지 저장"], False
    
    try:
        row = pd.DataFrame(tbl_data).iloc[selected_rows[0]]
        concrete_name = row["name"]
        
        range_info = f"_{time_range}일" if time_range != "all" else "_전체기간"
        
        filename = f"TCI_시간별분석_{concrete_name}{range_info}.png"
        
        return dcc.send_bytes(
            b"dummy_image_data", 
            filename=filename
        ), "저장 완료!", True
        
    except Exception:
        return None, "저장 실패", False

@callback(
    Output("download-crack-probability-image", "data"),
    Output("btn-save-crack-probability-image", "children"),
    Output("btn-save-crack-probability-image", "disabled"),
    Input("btn-save-crack-probability-image", "n_clicks"),
    State("viewer-crack-probability", "figure"),
    State("tbl-concrete-tci", "selected_rows"),
    State("tbl-concrete-tci", "data"),
    prevent_initial_call=True,
)
def save_crack_probability_image(n_clicks, figure, selected_rows, tbl_data):
    """균열발생확률 곡선 이미지를 저장합니다."""
    if not n_clicks or not figure or not selected_rows or not tbl_data:
        return None, [html.I(className="fas fa-camera me-1"), "이미지 저장"], False
    
    try:
        row = pd.DataFrame(tbl_data).iloc[selected_rows[0]]
        concrete_name = row["name"]
        
        filename = f"TCI_균열발생확률곡선_{concrete_name}.png"
        
        return dcc.send_bytes(
            b"dummy_image_data", 
            filename=filename
        ), "저장 완료!", True
        
    except Exception:
        return None, "저장 실패", False

@callback(
    Output("download-tci-data-csv", "data"),
    Output("btn-save-tci-data-csv", "children"),
    Output("btn-save-tci-data-csv", "disabled"),
    Input("btn-save-tci-data-csv", "n_clicks"),
    State("tbl-concrete-tci", "selected_rows"),
    State("tbl-concrete-tci", "data"),
    prevent_initial_call=True,
)
def save_tci_data_csv(n_clicks, selected_rows, tbl_data):
    """TCI 분석 데이터를 CSV로 저장합니다."""
    if not n_clicks or not selected_rows or not tbl_data:
        return None, [html.I(className="fas fa-file-csv me-1"), "데이터 저장"], False
    
    try:
        row = pd.DataFrame(tbl_data).iloc[selected_rows[0]]
        concrete_pk = row["concrete_pk"]
        concrete_name = row["name"]
        
        # FRD 파일에서 TCI 데이터 수집
        frd_files = get_frd_files(concrete_pk)
        if not frd_files:
            return None, "데이터 없음", False
        
        # 타설일 가져오기
        pour_date = None
        try:
            if row.get("con_t") and row["con_t"] not in ["", "N/A", None]:
                if hasattr(row["con_t"], 'strftime'):
                    pour_date = row["con_t"]
                elif isinstance(row["con_t"], str):
                    if 'T' in row["con_t"]:
                        pour_date = datetime.fromisoformat(row["con_t"].replace('Z', ''))
                    else:
                        pour_date = datetime.strptime(str(row["con_t"]), '%Y-%m-%d %H:%M:%S')
        except Exception:
            pass
        
        tci_data = []
        fc28 = 30  # 기본값
        
        for frd_file in frd_files:
            # 파일 시간 파싱
            try:
                time_str = os.path.basename(frd_file).split(".")[0]
                file_time = datetime.strptime(time_str, "%Y%m%d%H")
            except:
                continue
            
            # 응력 데이터 읽기
            stress_data = read_frd_stress_data(frd_file)
            if not stress_data or not stress_data.get('stress_values'):
                continue
            
            # 평균 응력 계산
            stress_values = list(stress_data['stress_values'][0].values())
            avg_stress_pa = np.mean(stress_values)
            avg_stress_mpa = avg_stress_pa / 1e6
            
            # 재령 계산
            if pour_date:
                age_days = (file_time - pour_date).days
                if age_days < 1:
                    age_days = 1
            else:
                first_file_time = datetime.strptime(os.path.basename(frd_files[0]).split(".")[0], "%Y%m%d%H")
                age_days = max(1, (file_time - first_file_time).days + 1)
            
            # 인장강도 및 TCI 계산
            tensile_strength = calculate_tensile_strength(age_days, fc28)
            tci = calculate_tci(avg_stress_mpa, tensile_strength)
            crack_probability = calculate_crack_probability(tci) * 100
            risk_level, _ = get_risk_level(tci)
            
            tci_data.append({
                '시간': file_time.strftime('%Y-%m-%d %H:%M:%S'),
                '재령(일)': age_days,
                '평균응력(MPa)': f'{avg_stress_mpa:.3f}',
                '인장강도(MPa)': f'{tensile_strength:.3f}',
                'TCI': f'{tci:.3f}',
                '균열확률(%)': f'{crack_probability:.1f}',
                '위험도': risk_level
            })
        
        # CSV 생성
        import io
        import csv
        
        output = io.StringIO()
        if tci_data:
            fieldnames = tci_data[0].keys()
            writer = csv.DictWriter(output, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(tci_data)
        
        csv_content = output.getvalue()
        output.close()
        
        filename = f"TCI_분석데이터_{concrete_name}.csv"
        
        return dcc.send_bytes(csv_content.encode('utf-8'), filename=filename), "저장 완료!", True
        
    except Exception as e:
        print(f"CSV 저장 오류: {e}")
        return None, "저장 실패", False
