#!/usr/bin/env python3
# pages/analysis_stress.py
# 응력 분석 페이지: FRD 파일에서 응력 데이터를 읽어와 3D 시각화

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
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import json
import ast
import re

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
        dcc.Store(id="stress-data-store", data=None),
        dcc.Store(id="current-stress-time-store", data=None),
        dcc.Store(id="current-stress-file-title-store", data=None),
        
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
                                            'fontWeight': '600',
                                            'color': '#111827',
                                            'textAlign': 'center',
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
            ], md=8)
        ], className="g-4")
    ]
)

# ───────────────────── FRD 파일 처리 함수들 ─────────────────────

# 데이터 캐시 (메모리 최적화)
_stress_data_cache = {}
_material_info_cache = {}

# 전체 응력 범위 저장 (페이지 로딩 시 미리 계산)
_global_stress_ranges = {}  # {concrete_pk: {component: (min, max), ...}}

def read_frd_stress_data(frd_path):
    """FRD 파일에서 응력 데이터를 읽어옵니다. (캐싱 적용)"""
    # 캐시 확인
    if frd_path in _stress_data_cache:
        return _stress_data_cache[frd_path]
    
    try:
        with open(frd_path, 'r') as f:
            lines = f.readlines()
        
        stress_data = {
            'times': [],
            'nodes': [],
            'coordinates': [],
            'stress_values': [],
            'stress_components': {}  # 각 응력 성분별 데이터 저장
        }
        
        node_coords = {}
        stress_values = {}
        stress_components = {
            'SXX': {}, 'SYY': {}, 'SZZ': {}, 
            'SXY': {}, 'SYZ': {}, 'SZX': {}
        }
        
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
                # 과학적 표기법을 포함한 숫자 추출
                nums = re.findall(r'-?\d+(?:\.\d+)?(?:[Ee][-+]?\d+)?', line)
                if len(nums) >= 5:
                    try:
                        node_id = int(nums[1])
                        x, y, z = float(nums[2]), float(nums[3]), float(nums[4])
                        node_coords[node_id] = [x, y, z]
                    except Exception:
                        pass
            
            # 응력 데이터 파싱
            elif parsing_stress and line.startswith('-1'):
                # 노드 ID와 응력 값들 추출
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
                        
                        # 각 응력 성분 저장
                        stress_components['SXX'][node_id] = sxx
                        stress_components['SYY'][node_id] = syy
                        stress_components['SZZ'][node_id] = szz
                        stress_components['SXY'][node_id] = sxy
                        stress_components['SYZ'][node_id] = syz
                        stress_components['SZX'][node_id] = sxz
                        
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
                # 노드 ID 순서를 정렬하여 일관성 보장
                sorted_node_ids = sorted(common_node_ids)
                
                # 공통 노드 ID만 사용 (정렬된 순서로)
                stress_data['coordinates'] = [node_coords[i] for i in sorted_node_ids]
                stress_data['nodes'] = sorted_node_ids
                stress_data['stress_values'] = [{i: stress_values[i] for i in sorted_node_ids}]
                
                # 각 응력 성분별 데이터 저장 (정렬된 순서로)
                for component in stress_components:
                    component_data = {}
                    for node_id in sorted_node_ids:
                        if node_id in stress_components[component]:
                            component_data[node_id] = stress_components[component][node_id]
                    stress_data['stress_components'][component] = component_data
        
        # 시간 정보 파싱
        try:
            filename = os.path.basename(frd_path)
            time_str = filename.split(".")[0]
            dt = datetime.strptime(time_str, "%Y%m%d%H")
            stress_data['times'].append(dt)
        except:
            stress_data['times'].append(0)
        
        # 캐시에 저장 (최대 10개 파일까지만 캐시)
        if len(_stress_data_cache) >= 10:
            # 가장 오래된 항목 제거
            oldest_key = next(iter(_stress_data_cache))
            del _stress_data_cache[oldest_key]
        
        _stress_data_cache[frd_path] = stress_data
        return stress_data
    except Exception:
        return None

def get_frd_files(concrete_pk):
    """콘크리트 PK에 해당하는 FRD 파일들을 찾습니다."""
    frd_dir = f"frd/{concrete_pk}"
    if not os.path.exists(frd_dir):
        return []
    
    frd_files = glob.glob(f"{frd_dir}/*.frd")
    return sorted(frd_files)

def calculate_global_stress_ranges(concrete_pk):
    """콘크리트의 모든 FRD 파일에서 전체 응력 범위를 미리 계산합니다."""
    if concrete_pk in _global_stress_ranges:
        return _global_stress_ranges[concrete_pk]
    
    frd_files = get_frd_files(concrete_pk)
    if not frd_files:
        return {}
    
    # 각 응력 성분별 전체 범위 계산
    global_ranges = {
        'von_mises': {'min': float('inf'), 'max': float('-inf')},
        'SXX': {'min': float('inf'), 'max': float('-inf')},
        'SYY': {'min': float('inf'), 'max': float('-inf')},
        'SZZ': {'min': float('inf'), 'max': float('-inf')},
        'SXY': {'min': float('inf'), 'max': float('-inf')},
        'SYZ': {'min': float('inf'), 'max': float('-inf')},
        'SZX': {'min': float('inf'), 'max': float('-inf')}
    }
    
    for frd_file in frd_files:
        stress_data = read_frd_stress_data(frd_file)
        if not stress_data or not stress_data['stress_values']:
            continue
        
        # von Mises 응력 범위
        if stress_data['stress_values']:
            von_mises_values = list(stress_data['stress_values'][0].values())
            von_mises_gpa = np.array(von_mises_values) / 1e9
            file_min, file_max = np.nanmin(von_mises_gpa), np.nanmax(von_mises_gpa)
            global_ranges['von_mises']['min'] = min(global_ranges['von_mises']['min'], file_min)
            global_ranges['von_mises']['max'] = max(global_ranges['von_mises']['max'], file_max)
        
        # 각 응력 성분별 범위
        for component in ['SXX', 'SYY', 'SZZ', 'SXY', 'SYZ', 'SZX']:
            if component in stress_data.get('stress_components', {}):
                component_values = list(stress_data['stress_components'][component].values())
                component_gpa = np.array(component_values) / 1e9
                file_min, file_max = np.nanmin(component_gpa), np.nanmax(component_gpa)
                global_ranges[component]['min'] = min(global_ranges[component]['min'], file_min)
                global_ranges[component]['max'] = max(global_ranges[component]['max'], file_max)
    
    # 무한대 값이 있으면 0으로 설정
    for component in global_ranges:
        if global_ranges[component]['min'] == float('inf'):
            global_ranges[component]['min'] = 0
        if global_ranges[component]['max'] == float('-inf'):
            global_ranges[component]['max'] = 0
    
    _global_stress_ranges[concrete_pk] = global_ranges
    return global_ranges

def clear_stress_cache(concrete_pk=None):
    """응력 데이터 캐시를 정리합니다."""
    global _stress_data_cache, _material_info_cache, _global_stress_ranges
    
    if concrete_pk:
        # 특정 콘크리트의 캐시만 정리
        keys_to_remove = [k for k in _stress_data_cache.keys() if concrete_pk in k]
        for key in keys_to_remove:
            del _stress_data_cache[key]
        
        if concrete_pk in _global_stress_ranges:
            del _global_stress_ranges[concrete_pk]
    else:
        # 전체 캐시 정리
        _stress_data_cache.clear()
        _material_info_cache.clear()
        _global_stress_ranges.clear()

def get_sensor_positions(concrete_pk):
    """콘크리트에 속한 센서들의 위치 정보를 가져옵니다."""
    try:
        df_sensors = api_db.get_sensors_data(concrete_pk=concrete_pk)
        if df_sensors.empty:
            return []
        
        sensor_positions = []
        for _, row in df_sensors.iterrows():
            try:
                dims = ast.literal_eval(row["dims"])
                x = float(dims["nodes"][0])
                y = float(dims["nodes"][1])
                z = float(dims["nodes"][2])
                device_id = row["device_id"]
                sensor_positions.append({
                    "x": x, "y": y, "z": z,
                    "device_id": device_id
                })
            except Exception:
                continue
        
        return sensor_positions
    except Exception:
        return []

def parse_material_info_from_inp_cached(inp_file_path):
    """INP 파일에서 물성치 정보를 캐싱하여 추출합니다."""
    # 캐시 확인
    if inp_file_path in _material_info_cache:
        return _material_info_cache[inp_file_path]
    
    try:
        with open(inp_file_path, 'r') as f:
            lines = f.readlines()
        material_info = parse_material_info_from_inp(lines)
        
        # 캐시에 저장 (최대 20개 파일까지만 캐시)
        if len(_material_info_cache) >= 20:
            oldest_key = next(iter(_material_info_cache))
            del _material_info_cache[oldest_key]
        
        _material_info_cache[inp_file_path] = material_info
        return material_info
    except:
        return "물성치 정보 없음"

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
        # 프로젝트가 없으면 캐시 정리
        clear_stress_cache()
        return [], [], [], [], None
    
    try:
        # 프로젝트 정보 로드
        df_proj = api_db.get_project_data(project_pk=project_pk)
        if df_proj.empty:
            clear_stress_cache()
            return [], [], [], [], None
            
        proj_row = df_proj.iloc[0]
        proj_name = proj_row["name"]
        
        # 해당 프로젝트의 콘크리트 데이터 로드
        df_conc = api_db.get_concrete_data(project_pk=project_pk)
        if df_conc.empty:
            clear_stress_cache()
            return [], [], [], [], {"name": proj_name, "pk": project_pk}
        
    except Exception as e:
        clear_stress_cache()
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
        
        # 상태 결정 (온도분석 페이지와 동일한 로직)
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
    
    # 테이블 스타일 설정 (온도분석 페이지와 동일)
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
            'fontWeight': '600',
            'color': '#111827',
            'textAlign': 'center',
            'paddingLeft': '16px'
        }
    ]
    
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
        return [
            "프로젝트가 선택되지 않았습니다. ",
            html.A("홈으로 돌아가기", href="/", className="alert-link")
        ]
    
    project_name = project_info.get("name", "알 수 없는 프로젝트")
    return f"📁 현재 프로젝트: {project_name}"

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
    # FRD 파일 목록 가져오기
    frd_files = get_frd_files(concrete_pk)
    
    # 기본 슬라이더 설정
    slider_min, slider_max, slider_marks, slider_value = 0, 5, {}, 0
    
    # FRD 파일이 있으면 시간 정보 설정
    if frd_files:
        # 시간 파싱
        times = []
        for f in frd_files:
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
            
            # 슬라이더 마크 설정
            marks = {}
            seen_dates = set()
            for i, dt in enumerate(times):
                date_str = dt.strftime("%m/%d")
                if date_str not in seen_dates:
                    marks[i] = date_str
                    seen_dates.add(date_str)
            slider_marks = marks
    
    # FRD 파일 목록 표시
    frd_file_list = []
    all_stress_data = {}
    initial_time_info = ""  # 오류 방지: 항상 초기화
    
    if not frd_files:
        frd_file_list = html.Div([
            dbc.Alert("FRD 파일이 없습니다.", color="warning", className="mb-3")
        ], className="mb-4")
        initial_time_info = "FRD 파일이 없습니다."
    else:
        # 지연 로딩: 첫 번째 파일만 먼저 로드
        if frd_files:
            first_file = frd_files[0]
            filename = os.path.basename(first_file)
            
            # 첫 번째 FRD 파일에서 응력 데이터 읽기
            stress_data = read_frd_stress_data(first_file)
            if stress_data:
                all_stress_data[filename] = stress_data
                
                frd_file_list.append(
                    dbc.Card([
                        dbc.CardBody([
                            html.H6(f"📄 {filename}", className="mb-2"),
                            html.Small(f"시간 스텝: {len(stress_data['times'])}개", className="text-muted"),
                            html.Br(),
                            html.Small(f"노드 수: {len(stress_data['nodes'])}개", className="text-muted")
                        ])
                    ], className="mb-2")
                )
        
        # 나머지 파일들은 백그라운드에서 로드 (지연 로딩)
        if len(frd_files) > 1:
            frd_file_list.append(
                html.Div([
                    html.Small(f"📁 총 {len(frd_files)}개 파일 (나머지는 필요시 로드)", className="text-muted")
                ], className="mt-2")
            )
        
        frd_file_list = html.Div(frd_file_list)
    
            # 3D 시각화 생성
        stress_3d_figure = create_3d_stress_figure(all_stress_data)
        
        # 초기 시간 정보와 물성치 정보 생성 (첫 번째 파일 기준)
        initial_time_info = ""
        if frd_files:
            try:
                first_filename = os.path.basename(frd_files[0])
                time_str = first_filename.split(".")[0]
                dt = datetime.strptime(time_str, "%Y%m%d%H")
                formatted_time = dt.strftime("%Y년 %m월 %d일 %H시")
                
                # 물성치 정보 가져오기 (동일한 시간의 INP 파일에서)
                material_info = ""
                try:
                    inp_dir = f"inp/{concrete_pk}"
                    inp_file_path = f"{inp_dir}/{first_filename.split('.')[0]}.inp"
                    if os.path.exists(inp_file_path):
                        material_info = parse_material_info_from_inp_cached(inp_file_path)
                except:
                    material_info = ""
                
                # 센서 정보 가져오기
                sensor_info = ""
                try:
                    sensor_positions = get_sensor_positions(concrete_pk)
                    if sensor_positions:
                        sensor_count = len(sensor_positions)
                        sensor_info = f"센서: {sensor_count}개"
                except:
                    sensor_info = ""
                
                # 초기 응력 통계 계산
                if all_stress_data and first_filename in all_stress_data:
                    first_data = all_stress_data[first_filename]
                    if first_data['stress_values']:
                        stress_values = list(first_data['stress_values'][0].values())
                        stress_values_gpa = np.array(stress_values) / 1e9
                        current_min = float(np.nanmin(stress_values_gpa))
                        current_max = float(np.nanmax(stress_values_gpa))
                        current_avg = float(np.nanmean(stress_values_gpa))
                        
                        initial_time_info = html.Div([
                            html.Div([
                                # 시간 정보와 응력 통계를 한 줄에 표시
                                html.Div([
                                    html.I(className="fas fa-clock", style={"color": "#3b82f6", "fontSize": "14px"}),
                                    html.Span(formatted_time, style={
                                        "fontWeight": "600",
                                        "color": "#1f2937",
                                        "fontSize": "14px",
                                        "marginLeft": "8px",
                                        "marginRight": "16px"
                                    }),
                                    html.Span(f"최저: {current_min:.0f}GPa", style={
                                        "color": "#6b7280",
                                        "fontSize": "12px",
                                        "fontWeight": "500",
                                        "marginRight": "12px"
                                    }),
                                    html.Span(f"최고: {current_max:.0f}GPa", style={
                                        "color": "#6b7280",
                                        "fontSize": "12px",
                                        "fontWeight": "500",
                                        "marginRight": "12px"
                                    }),
                                    html.Span(f"평균: {current_avg:.0f}GPa", style={
                                        "color": "#6b7280",
                                        "fontSize": "12px",
                                        "fontWeight": "500"
                                    })
                                ], style={
                                    "display": "flex",
                                    "alignItems": "center",
                                    "justifyContent": "center",
                                    "marginBottom": "8px" if (material_info and material_info != "물성치 정보 없음") or sensor_info else "0",
                                    "marginTop": "12px"
                                }),
                                
                                # 물성치 정보와 센서 정보를 한 줄에 표시
                                html.Div([
                                    # 물성치 정보 (있는 경우만)
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
                                        for prop in material_info.split(", ") if material_info and material_info != "물성치 정보 없음"]
                                    ], style={"display": "inline"}) if material_info and material_info != "물성치 정보 없음" else html.Div(),
                                    
                                    # 센서 정보 (있는 경우만)
                                    html.Div([
                                        html.I(className="fas fa-microchip", style={"color": "#10b981", "fontSize": "14px"}),
                                        html.Span(sensor_info, style={
                                            "color": "#111827",
                                            "fontSize": "12px",
                                            "fontWeight": "500",
                                            "marginLeft": "4px"
                                        })
                                    ], style={"display": "inline"}) if sensor_info else html.Div()
                                ], style={
                                    "display": "flex",
                                    "alignItems": "center",
                                    "justifyContent": "center",
                                    "gap": "16px",
                                    "flexWrap": "wrap",
                                    "marginBottom": "12px"
                                }) if (material_info and material_info != "물성치 정보 없음") or sensor_info else html.Div()
                                
                            ], style={
                                "backgroundColor": "#f8fafc",
                                "padding": "12px 16px",
                                "borderRadius": "8px",
                                "border": "1px solid #e2e8f0",
                                "boxShadow": "0 1px 2px rgba(0,0,0,0.05)",
                                "height": "65px",
                                "display": "flex",
                                "flexDirection": "column",
                                "justifyContent": "center",
                                "alignItems": "center"
                            })
                        ])
            except:
                initial_time_info = "시간 정보를 불러올 수 없습니다."
        else:
            initial_time_info = "FRD 파일이 없습니다."
        
        # 응력 성분 선택 드롭다운
        stress_component_dropdown = dbc.Select(
            id="stress-component-selector",
            options=[
                {"label": "von Mises 응력", "value": "von_mises"},
                {"label": "SXX (X방향 정응력)", "value": "SXX"},
                {"label": "SYY (Y방향 정응력)", "value": "SYY"},
                {"label": "SZZ (Z방향 정응력)", "value": "SZZ"},
                {"label": "SXY (XY면 전단응력)", "value": "SXY"},
                {"label": "SYZ (YZ면 전단응력)", "value": "SYZ"},
                {"label": "SZX (ZX면 전단응력)", "value": "SZX"},
            ],
            value="von_mises",
            style={
                "width": "200px",
                "marginBottom": "12px"
            }
        )
    
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
                    id="time-slider-stress",
                    min=slider_min,
                    max=slider_max,
                    step=1,
                    value=slider_value,
                    marks=slider_marks,
                    tooltip={"placement": "bottom", "always_visible": True},
                    updatemode='drag',
                    persistence=False
                ),
                # 재생/정지/배속 버튼 추가
                html.Div([
                    # 재생/정지 버튼 (아이콘만)
                    dbc.Button(
                        "▶",
                        id="btn-play-stress",
                        color="success",
                        size="sm",
                        style={
                            "borderRadius": "50%",
                            "width": "32px",
                            "height": "32px",
                            "padding": "0",
                            "marginRight": "8px",
                            "display": "flex",
                            "alignItems": "center",
                            "justifyContent": "center",
                            "fontSize": "14px",
                            "fontWeight": "bold"
                        }
                    ),
                    dbc.Button(
                        "⏸",
                        id="btn-pause-stress",
                        color="warning",
                        size="sm",
                        style={
                            "borderRadius": "50%",
                            "width": "32px",
                            "height": "32px",
                            "padding": "0",
                            "marginRight": "8px",
                            "display": "flex",
                            "alignItems": "center",
                            "justifyContent": "center",
                            "fontSize": "14px",
                            "fontWeight": "bold"
                        }
                    ),
                    # 배속 설정 드롭다운
                    dbc.DropdownMenu([
                        dbc.DropdownMenuItem("1x", id="speed-1x-stress", n_clicks=0),
                        dbc.DropdownMenuItem("2x", id="speed-2x-stress", n_clicks=0),
                        dbc.DropdownMenuItem("4x", id="speed-4x-stress", n_clicks=0),
                        dbc.DropdownMenuItem("8x", id="speed-8x-stress", n_clicks=0),
                    ], 
                    label="⚡",
                    id="speed-dropdown-stress",
                    size="sm",
                    style={
                        "width": "32px",
                        "height": "32px",
                        "padding": "0",
                        "display": "flex",
                        "alignItems": "center",
                        "justifyContent": "center"
                    },
                    toggle_style={
                        "borderRadius": "50%",
                        "width": "32px",
                        "height": "32px",
                        "padding": "0",
                        "backgroundColor": "#6c757d",
                        "border": "none",
                        "fontSize": "14px",
                        "fontWeight": "bold"
                    }
                    ),
                ], style={
                    "display": "flex",
                    "alignItems": "center",
                    "justifyContent": "center",
                    "marginTop": "12px"
                }),
                # 재생 상태 표시용 Store
                dcc.Store(id="play-state-stress", data={"playing": False}),
                # 배속 상태 표시용 Store
                dcc.Store(id="speed-state-stress", data={"speed": 1}),
                # 자동 재생용 Interval
                dcc.Interval(
                    id="play-interval-stress",
                    interval=1000,  # 1초마다 (기본값)
                    n_intervals=0,
                    disabled=True
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
            # 왼쪽: 현재 시간/응력 정보
            dbc.Col([
                html.Div(
                    initial_time_info, 
                    id="viewer-3d-stress-time-info", 
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
                    dcc.Loading(
                        id="loading-btn-save-3d-stress-image",
                        type="circle",
                        children=[
                            dbc.Button(
                                [html.I(className="fas fa-camera me-1"), "이미지 저장"],
                                id="btn-save-3d-stress-image",
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
                            )
                        ]
                    ),
                    dcc.Loading(
                        id="loading-btn-save-current-frd",
                        type="circle",
                        children=[
                            dbc.Button(
                                [html.I(className="fas fa-file-download me-1"), "FRD 파일 저장"],
                                id="btn-save-current-frd",
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
                            )
                        ]
                    ),
                ], style={"display": "flex", "justifyContent": "center", "alignItems": "center", "height": "65px"})
            ], md=4, style={
                "height": "65px"
            }),
        ], className="mb-3 align-items-stretch h-100", style={"minHeight": "65px"}),
        
        # 3D 뷰어 (노션 스타일)
        html.Div([
            html.Div([
                # 응력 성분 선택 및 응력바 통일 설정
                html.Div([
                    # 제목과 응력 성분 선택을 한 줄에 배치
                    html.Div([
                        html.H6("🎯 입체 응력 Viewer", style={
                            "fontWeight": "600",
                            "color": "#374151",
                            "fontSize": "16px",
                            "margin": "0",
                            "display": "inline-block",
                            "marginRight": "20px"
                        }),
                        html.Div([
                            stress_component_dropdown,
                        ], style={
                            "display": "inline-block",
                            "verticalAlign": "top"
                        }),
                    ], style={
                        "marginBottom": "16px",
                        "display": "flex",
                        "alignItems": "center"
                    }),
                    
                    # 응력바 통일 토글 스위치
                    html.Div([
                        html.Label("전체 응력바 통일", style={
                            "fontWeight": "500",
                            "color": "#374151",
                            "marginBottom": "8px",
                            "fontSize": "13px",
                            "display": "inline-block",
                            "marginRight": "8px"
                        }),
                        dbc.Switch(
                            id="btn-unified-stress-colorbar",
                            label="",
                            value=False,
                            className="mb-0",
                            style={
                                "display": "inline-block",
                                "marginBottom": "12px",
                                "marginTop": "-5px"
                            }
                        ),
                        dbc.Tooltip(
                            "모든 그래프의 응력바 범위를 통일합니다",
                            target="btn-unified-stress-colorbar",
                            placement="top"
                        )
                    ], style={
                        "display": "flex",
                        "alignItems": "center",
                        "marginBottom": "12px"
                    }),
                ]),
                dcc.Graph(
                    id="viewer-3d-stress-display",
                    style={
                        "height": "65vh", 
                        "borderRadius": "8px",
                        "overflow": "hidden"
                    },
                    config={"scrollZoom": True},
                    figure=stress_3d_figure,
                ),
            ], style={
                "padding": "20px",
                "backgroundColor": "white",
                "borderRadius": "12px",
                "border": "1px solid #e5e7eb",
                "boxShadow": "0 1px 3px rgba(0,0,0,0.1)"
            })
        ]),
        
        # 숨겨진 컴포넌트들
        html.Div([
            dcc.Store(id="stress-data-store", data=all_stress_data),
            dcc.Store(id="current-stress-time-store", data=None),
            dcc.Store(id="current-stress-file-title-store", data=None),
            dcc.Store(id="unified-stress-colorbar-state", data=False),
            dcc.Download(id="download-3d-stress-image"),
            dcc.Download(id="download-current-frd"),
            # 삭제 확인 다이얼로그
            dcc.ConfirmDialog(
                id="confirm-del-stress", 
                message="선택한 콘크리트를 정말 삭제하시겠습니까?\n\n※ 관련 FRD 파일도 함께 삭제됩니다."
            ),
        ], style={"display": "none"})
    ])

def create_3d_stress_figure(stress_data, selected_component="von_mises"):
    """3D 응력 시각화를 생성합니다."""
    if not stress_data:
        return go.Figure().add_annotation(
            text="응력 데이터가 없습니다.",
            xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False
        )
    
    # 첫 번째 파일의 첫 번째 시간 스텝 데이터 사용
    first_file = list(stress_data.keys())[0]
    first_data = stress_data[first_file]
    
    if not first_data['coordinates'] or not first_data['stress_values']:
        return go.Figure().add_annotation(
            text="유효한 응력 데이터가 없습니다.",
            xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False
        )
    
    # 좌표와 응력 값 추출
    coords = np.array(first_data['coordinates'])
    
    # 선택된 응력 성분에 따라 값 추출
    if selected_component == "von_mises":
        stress_values = list(first_data['stress_values'][0].values())
        title_suffix = " (von Mises)"
    else:
        # 특정 응력 성분 선택
        if selected_component in first_data.get('stress_components', {}):
            stress_values = list(first_data['stress_components'][selected_component].values())
            title_suffix = f" ({selected_component})"
        else:
            # fallback to von Mises
            stress_values = list(first_data['stress_values'][0].values())
            title_suffix = " (von Mises)"
    
    # 단위 변환: Pa → GPa (데이터 검증 전에 미리 정의)
    stress_values_gpa = np.array(stress_values) / 1e9
    
    # 데이터 검증: 좌표와 응력 값의 개수가 일치하는지 확인
    if len(coords) != len(stress_values):
        print(f"데이터 불일치: 좌표 {len(coords)}개, 응력 값 {len(stress_values)}개")
        # 산점도로 대체
        fig = go.Figure(data=[
            go.Scatter3d(
                x=coords[:, 0],
                y=coords[:, 1],
                z=coords[:, 2],
                mode='markers',
                marker=dict(
                    size=5,
                    color=stress_values_gpa[:len(coords)] if len(stress_values_gpa) > len(coords) else stress_values_gpa,
                    colorscale=[[0, 'blue'], [1, 'red']],
                    colorbar=dict(title="Stress (GPa)", thickness=10),
                    showscale=True
                ),
                text=[f"노드 {i+1}<br>응력: {val:.4f} GPa" for i, val in enumerate(stress_values_gpa[:len(coords)] if len(stress_values_gpa) > len(coords) else stress_values_gpa)],
                hoverinfo='text'
            )
        ])
        fig.update_layout(
            title="3D 응력 분포 (산점도 - 데이터 불일치)",
            scene=dict(
                aspectmode='data',
                bgcolor='white',
                xaxis=dict(showgrid=True, gridcolor='lightgray', showline=True, linecolor='black'),
                yaxis=dict(showgrid=True, gridcolor='lightgray', showline=True, linecolor='black'),
                zaxis=dict(showgrid=True, gridcolor='lightgray', showline=True, linecolor='black'),
            ),
            margin=dict(l=0, r=0, t=30, b=0),
            height=500
        )
        return fig
    
    stress_min, stress_max = np.nanmin(stress_values_gpa), np.nanmax(stress_values_gpa)

    # 온도분석 페이지와 동일한 방식으로 등응력면(Volume) 생성
    fig = go.Figure(data=go.Volume(
        x=coords[:, 0],
        y=coords[:, 1],
        z=coords[:, 2],
        value=stress_values_gpa,
        opacity=0.1,
        surface_count=15,
        colorscale=[[0, 'blue'], [1, 'red']],
        colorbar=dict(title='Stress (GPa)', thickness=10),
        cmin=stress_min,
        cmax=stress_max,
        showscale=True,
        hoverinfo='skip',
        name='응력 볼륨'
    ))
    
    fig.update_layout(
        title="",
        uirevision='constant',
        scene=dict(
            aspectmode='data',
            bgcolor='white',
            xaxis=dict(showgrid=True, gridcolor='lightgray', showline=True, linecolor='black'),
            yaxis=dict(showgrid=True, gridcolor='lightgray', showline=True, linecolor='black'),
            zaxis=dict(showgrid=True, gridcolor='lightgray', showline=True, linecolor='black'),
        ),
        margin=dict(l=0, r=0, t=30, b=0),
        height=500
    )
    return fig

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

# ───────────────────── 추가 콜백 함수들 ─────────────────────

@callback(
    Output("viewer-3d-stress-display", "figure"),
    Output("viewer-3d-stress-time-info", "children"),
    Input("time-slider-stress", "value"),
    Input("btn-unified-stress-colorbar", "value"),
    Input("stress-component-selector", "value"),
    State("tbl-concrete-stress", "selected_rows"),
    State("tbl-concrete-stress", "data"),
    State("unified-stress-colorbar-state", "data"),
    prevent_initial_call=True,
)
def update_3d_stress_viewer(time_idx, unified_colorbar, selected_component, selected_rows, tbl_data, unified_state):
    """3D 응력 시각화를 업데이트합니다."""
    if not selected_rows or not tbl_data:
        return go.Figure().add_annotation(
            text="콘크리트를 선택하세요.",
            xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False
        ), "콘크리트를 선택하세요."
    
    row = pd.DataFrame(tbl_data).iloc[selected_rows[0]]
    concrete_pk = row["concrete_pk"]
    concrete_name = row["name"]
    
    # FRD 파일 목록 가져오기
    frd_files = get_frd_files(concrete_pk)
    if not frd_files:
        return go.Figure().add_annotation(
            text="FRD 파일이 없습니다.",
            xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False
        ), "FRD 파일이 없습니다."
    
    # 전체 응력바 통일 상태 확인
    use_unified_colorbar = unified_colorbar or (isinstance(unified_state, dict) and unified_state.get("unified", False))
    
    # 미리 계산된 전체 응력 범위 사용
    global_stress_min = None
    global_stress_max = None
    
    if use_unified_colorbar:
        # 미리 계산된 전체 범위 가져오기
        global_ranges = _global_stress_ranges.get(concrete_pk, {})
        if selected_component in global_ranges:
            global_stress_min = global_ranges[selected_component]['min']
            global_stress_max = global_ranges[selected_component]['max']
        else:
            # 캐시에 없으면 즉시 계산
            global_ranges = calculate_global_stress_ranges(concrete_pk)
            if selected_component in global_ranges:
                global_stress_min = global_ranges[selected_component]['min']
                global_stress_max = global_ranges[selected_component]['max']
    
    # 선택된 시간에 해당하는 FRD 파일
    if time_idx is not None and time_idx < len(frd_files):
        selected_file = frd_files[time_idx]
        filename = os.path.basename(selected_file)
        
        # FRD 파일에서 응력 데이터 읽기
        stress_data = read_frd_stress_data(selected_file)
        
        if not stress_data or not stress_data['coordinates'] or not stress_data['stress_values']:
            return go.Figure().add_annotation(
                text="유효한 응력 데이터가 없습니다.",
                xref="paper", yref="paper",
                x=0.5, y=0.5, showarrow=False
            ), "유효한 응력 데이터가 없습니다."
        
        # 좌표와 응력 값 추출
        coords = np.array(stress_data['coordinates'])
        
        # 선택된 응력 성분에 따라 값 추출 (노드 ID 순서 보장)
        if selected_component == "von_mises":
            # von Mises 응력: 노드 ID 순서대로 추출
            stress_values = [stress_data['stress_values'][0][node_id] for node_id in stress_data['nodes']]
            component_name = "von Mises 응력"
        else:
            # 특정 응력 성분 선택
            if selected_component in stress_data.get('stress_components', {}):
                stress_values = [stress_data['stress_components'][selected_component][node_id] for node_id in stress_data['nodes']]
                component_name = f"{selected_component} 응력"
            else:
                # fallback to von Mises
                stress_values = [stress_data['stress_values'][0][node_id] for node_id in stress_data['nodes']]
                component_name = "von Mises 응력"
        
        # 데이터 검증: 좌표와 응력 값의 개수가 일치하는지 확인
        if len(coords) != len(stress_values):
            # 산점도로 대체
            fig = go.Figure(data=[
                go.Scatter3d(
                    x=coords[:, 0],
                    y=coords[:, 1],
                    z=coords[:, 2],
                    mode='markers',
                    marker=dict(
                        size=5,
                        color=[v/1000 for v in (stress_values[:len(coords)] if len(stress_values) > len(coords) else stress_values)],
                        colorscale=[[0, 'blue'], [1, 'red']],
                        colorbar=dict(title="Stress (GPa)", thickness=10),
                        showscale=True
                    ),
                    text=[f"노드 {i+1}<br>응력: {val/1000:.4f} GPa" for i, val in enumerate(stress_values[:len(coords)] if len(stress_values) > len(coords) else stress_values)],
                    hoverinfo='text'
                )
            ])
            fig.update_layout(
                title="3D 응력 분포 (산점도 - 데이터 불일치)",
                scene=dict(
                    aspectmode='data',
                    bgcolor='white',
                    xaxis=dict(showgrid=True, gridcolor='lightgray', showline=True, linecolor='black'),
                    yaxis=dict(showgrid=True, gridcolor='lightgray', showline=True, linecolor='black'),
                    zaxis=dict(showgrid=True, gridcolor='lightgray', showline=True, linecolor='black'),
                ),
                margin=dict(l=0, r=0, t=30, b=0),
                height=500
            )
            return fig, "콘크리트를 선택하세요."
        
        # 시간 정보 계산
        try:
            time_str = filename.split(".")[0]
            dt = datetime.strptime(time_str, "%Y%m%d%H")
            formatted_time = dt.strftime("%Y년 %m월 %d일 %H시")
        except:
            formatted_time = filename
        
        # 물성치 정보 가져오기 (동일한 시간의 INP 파일에서)
        material_info = ""
        try:
            inp_dir = f"inp/{concrete_pk}"
            inp_file_path = f"{inp_dir}/{filename.split('.')[0]}.inp"
            if os.path.exists(inp_file_path):
                material_info = parse_material_info_from_inp_cached(inp_file_path)
        except:
            material_info = ""
        
        # 센서 정보 가져오기
        sensor_info = ""
        try:
            sensor_positions = get_sensor_positions(concrete_pk)
            if sensor_positions:
                sensor_count = len(sensor_positions)
                sensor_info = f"센서: {sensor_count}개"
        except:
            sensor_info = ""
        
        # 단위 변환: Pa → GPa
        stress_values_gpa = np.array(stress_values) / 1e9
        
        # 응력 범위 설정 (통일 여부에 따라)
        if use_unified_colorbar and global_stress_min is not None and global_stress_max is not None:
            stress_min, stress_max = global_stress_min, global_stress_max
        else:
            stress_min, stress_max = np.nanmin(stress_values_gpa), np.nanmax(stress_values_gpa)
        
        # 응력 통계 계산 (GPa 단위)
        if stress_values:
            current_min = float(np.nanmin(stress_values_gpa))
            current_max = float(np.nanmax(stress_values_gpa))
            current_avg = float(np.nanmean(stress_values_gpa))
            time_info = html.Div([
                # 통합 정보 카드 (노션 스타일)
                html.Div([
                    # 시간 정보와 응력 통계를 한 줄에 표시
                    html.Div([
                        html.I(className="fas fa-clock", style={"color": "#3b82f6", "fontSize": "14px"}),
                        html.Span(formatted_time, style={
                            "fontWeight": "600",
                            "color": "#1f2937",
                            "fontSize": "14px",
                            "marginLeft": "8px",
                            "marginRight": "16px"
                        }),
                        html.Span(f"최저: {current_min:.0f}GPa", style={
                            "color": "#6b7280",
                            "fontSize": "12px",
                            "fontWeight": "500",
                            "marginRight": "12px"
                        }),
                        html.Span(f"최고: {current_max:.0f}GPa", style={
                            "color": "#6b7280",
                            "fontSize": "12px",
                            "fontWeight": "500",
                            "marginRight": "12px"
                        }),
                        html.Span(f"평균: {current_avg:.0f}GPa", style={
                            "color": "#6b7280",
                            "fontSize": "12px",
                            "fontWeight": "500"
                        })
                    ], style={
                        "display": "flex",
                        "alignItems": "center",
                        "justifyContent": "center",
                        "marginBottom": "8px" if (material_info and material_info != "물성치 정보 없음") or sensor_info else "0",
                        "marginTop": "12px"
                    }),
                    
                    # 물성치 정보와 센서 정보를 한 줄에 표시
                    html.Div([
                        # 물성치 정보 (있는 경우만)
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
                            for prop in material_info.split(", ") if material_info and material_info != "물성치 정보 없음"]
                        ], style={"display": "inline"}) if material_info and material_info != "물성치 정보 없음" else html.Div(),
                        
                        # 센서 정보 (있는 경우만)
                        html.Div([
                            html.I(className="fas fa-microchip", style={"color": "#10b981", "fontSize": "14px"}),
                            html.Span(sensor_info, style={
                                "color": "#111827",
                                "fontSize": "12px",
                                "fontWeight": "500",
                                "marginLeft": "4px"
                            })
                        ], style={"display": "inline"}) if sensor_info else html.Div()
                    ], style={
                        "display": "flex",
                        "alignItems": "center",
                        "justifyContent": "center",
                        "gap": "16px",
                        "flexWrap": "wrap",
                        "marginBottom": "12px"
                    }) if (material_info and material_info != "물성치 정보 없음") or sensor_info else html.Div()
                    
                ], style={
                    "backgroundColor": "#f8fafc",
                    "padding": "12px 16px",
                    "borderRadius": "8px",
                    "border": "1px solid #e2e8f0",
                    "boxShadow": "0 1px 2px rgba(0,0,0,0.05)",
                    "height": "65px",
                    "display": "flex",
                    "flexDirection": "column",
                    "justifyContent": "center",
                    "alignItems": "center"
                })
            ])
        else:
            time_info = formatted_time
        
        # 좌표 정규화 (모델링 비율 문제 해결)
        coords_normalized = coords.copy()
        
        # 각 축별로 정규화
        for axis in range(3):
            axis_min, axis_max = coords[:, axis].min(), coords[:, axis].max()
            if axis_max > axis_min:
                coords_normalized[:, axis] = (coords[:, axis] - axis_min) / (axis_max - axis_min)
        
        # 3D 시각화 생성 (Volume 또는 Scatter3d 선택)
        # Volume이 보이지 않는 경우를 대비해 Scatter3d도 준비
        try:
            # 먼저 Volume으로 시도
            fig = go.Figure(data=go.Volume(
                x=coords_normalized[:, 0], 
                y=coords_normalized[:, 1], 
                z=coords_normalized[:, 2], 
                value=stress_values_gpa,
                opacity=0.1, 
                surface_count=15, 
                colorscale=[[0, 'blue'], [1, 'red']],
                colorbar=dict(title=f'{component_name} (GPa)', thickness=10),
                cmin=stress_min, 
                cmax=stress_max,
                showscale=True,
                hoverinfo='skip',
                name=f'{component_name} 볼륨'
            ))
        except Exception:
            # Volume이 실패하면 Scatter3d로 대체
            fig = go.Figure(data=go.Scatter3d(
                x=coords_normalized[:, 0],
                y=coords_normalized[:, 1],
                z=coords_normalized[:, 2],
                mode='markers',
                marker=dict(
                    size=3,
                    color=stress_values_gpa,
                    colorscale=[[0, 'blue'], [1, 'red']],
                    colorbar=dict(title=f'{component_name} (GPa)', thickness=10),
                    cmin=stress_min,
                    cmax=stress_max,
                    showscale=True
                ),
                text=[f"노드 {i+1}<br>{component_name}: {val:.4f} GPa" for i, val in enumerate(stress_values_gpa)],
                hoverinfo='text',
                name=f'{component_name} 산점도'
            ))
        
        fig.update_layout(
            uirevision='constant',
            scene=dict(
                aspectmode='data',
                bgcolor='white',
                xaxis=dict(showgrid=True, gridcolor='lightgray', showline=True, linecolor='black'),
                yaxis=dict(showgrid=True, gridcolor='lightgray', showline=True, linecolor='black'),
                zaxis=dict(showgrid=True, gridcolor='lightgray', showline=True, linecolor='black'),
            ),
            margin=dict(l=0, r=0, t=0, b=0)
        )
        
        # 콘크리트 외곽선 추가 (정규화된 좌표에 맞게)
        try:
            dims = ast.literal_eval(row["dims"]) if isinstance(row["dims"], str) else row["dims"]
            poly_nodes = np.array(dims["nodes"])
            poly_h = float(dims["h"])
            
            # 원본 좌표 범위
            orig_x_min, orig_x_max = coords[:, 0].min(), coords[:, 0].max()
            orig_y_min, orig_y_max = coords[:, 1].min(), coords[:, 1].max()
            orig_z_min, orig_z_max = coords[:, 2].min(), coords[:, 2].max()
            
            n = len(poly_nodes)
            x0, y0 = poly_nodes[:,0], poly_nodes[:,1]
            z0 = np.zeros(n)
            x1, y1 = x0, y0
            z1 = np.full(n, poly_h)
            
            # 외곽선 좌표도 정규화
            if orig_x_max > orig_x_min:
                x0_norm = (x0 - orig_x_min) / (orig_x_max - orig_x_min)
                x1_norm = (x1 - orig_x_min) / (orig_x_max - orig_x_min)
            else:
                x0_norm, x1_norm = x0, x1
                
            if orig_y_max > orig_y_min:
                y0_norm = (y0 - orig_y_min) / (orig_y_max - orig_y_min)
                y1_norm = (y1 - orig_y_min) / (orig_y_max - orig_y_min)
            else:
                y0_norm, y1_norm = y0, y1
                
            if orig_z_max > orig_z_min:
                z0_norm = (z0 - orig_z_min) / (orig_z_max - orig_z_min)
                z1_norm = (z1 - orig_z_min) / (orig_z_max - orig_z_min)
            else:
                z0_norm, z1_norm = z0, z1
            
            # 하단 외곽선
            fig.add_trace(go.Scatter3d(
                x=np.append(x0_norm, x0_norm[0]), y=np.append(y0_norm, y0_norm[0]), z=np.append(z0_norm, z0_norm[0]),
                mode='lines', line=dict(width=2, color='black'), showlegend=False, hoverinfo='skip'))
            
            # 상단 외곽선
            fig.add_trace(go.Scatter3d(
                x=np.append(x1_norm, x1_norm[0]), y=np.append(y1_norm, y1_norm[0]), z=np.append(z1_norm, z1_norm[0]),
                mode='lines', line=dict(width=2, color='black'), showlegend=False, hoverinfo='skip'))
            
            # 세로 연결선
            for i in range(n):
                fig.add_trace(go.Scatter3d(
                    x=[x0_norm[i], x1_norm[i]], y=[y0_norm[i], y1_norm[i]], z=[z0_norm[i], z1_norm[i]],
                    mode='lines', line=dict(width=2, color='black'), showlegend=False, hoverinfo='skip'))
        except Exception:
            pass
        
        # 센서 위치 추가 (온도분석 페이지와 동일한 방식)
        try:
            sensor_positions = get_sensor_positions(concrete_pk)
            if sensor_positions:
                sensor_xs, sensor_ys, sensor_zs, sensor_names = [], [], [], []
                
                for sensor in sensor_positions:
                    # 센서 좌표도 정규화
                    if orig_x_max > orig_x_min:
                        sensor_x_norm = (sensor["x"] - orig_x_min) / (orig_x_max - orig_x_min)
                    else:
                        sensor_x_norm = sensor["x"]
                        
                    if orig_y_max > orig_y_min:
                        sensor_y_norm = (sensor["y"] - orig_y_min) / (orig_y_max - orig_y_min)
                    else:
                        sensor_y_norm = sensor["y"]
                        
                    if orig_z_max > orig_z_min:
                        sensor_z_norm = (sensor["z"] - orig_z_min) / (orig_z_max - orig_z_min)
                    else:
                        sensor_z_norm = sensor["z"]
                    
                    sensor_xs.append(sensor_x_norm)
                    sensor_ys.append(sensor_y_norm)
                    sensor_zs.append(sensor_z_norm)
                    sensor_names.append(sensor["device_id"])
                
                # 센서 위치를 빨간 점으로 표시
                fig.add_trace(go.Scatter3d(
                    x=sensor_xs, y=sensor_ys, z=sensor_zs,
                    mode='markers',
                    marker=dict(size=6, color='red', symbol='circle'),
                    text=sensor_names,
                    hoverinfo='text',
                    name='센서',
                    showlegend=False
                ))
        except Exception as e:
            print(f"센서 위치 표기 중 오류: {e}")
            pass
        
        return fig, time_info
    
    return go.Figure().add_annotation(
        text="시간 인덱스가 유효하지 않습니다.",
        xref="paper", yref="paper",
        x=0.5, y=0.5, showarrow=False
    ), "시간 인덱스가 유효하지 않습니다."

@callback(
    Output("play-state-stress", "data"),
    Output("play-interval-stress", "disabled"),
    Output("btn-play-stress", "disabled"),
    Output("btn-pause-stress", "disabled"),
    Input("btn-play-stress", "n_clicks"),
    State("play-state-stress", "data"),
    prevent_initial_call=True,
)
def start_stress_playback(n_clicks, play_state):
    """응력 재생을 시작합니다."""
    if not play_state:
        play_state = {"playing": False}
    
    play_state["playing"] = True
    return play_state, False, True, False

@callback(
    Output("play-state-stress", "data", allow_duplicate=True),
    Output("play-interval-stress", "disabled", allow_duplicate=True),
    Output("btn-play-stress", "disabled", allow_duplicate=True),
    Output("btn-pause-stress", "disabled", allow_duplicate=True),
    Input("btn-pause-stress", "n_clicks"),
    State("play-state-stress", "data"),
    prevent_initial_call=True,
)
def stop_stress_playback(n_clicks, play_state):
    """응력 재생을 정지합니다."""
    if not play_state:
        play_state = {"playing": False}
    
    play_state["playing"] = False
    return play_state, True, False, True

@callback(
    Output("time-slider-stress", "value", allow_duplicate=True),
    Input("play-interval-stress", "n_intervals"),
    State("play-state-stress", "data"),
    State("speed-state-stress", "data"),
    State("time-slider-stress", "value"),
    State("time-slider-stress", "max"),
    prevent_initial_call=True,
)
def auto_play_stress_slider(n_intervals, play_state, speed_state, current_value, max_value):
    """자동 재생으로 슬라이더를 업데이트합니다."""
    if not play_state or not play_state.get("playing", False):
        raise PreventUpdate
    
    speed = speed_state.get("speed", 1) if speed_state else 1
    
    if current_value is None:
        current_value = 0
    
    new_value = current_value + speed
    if new_value > max_value:
        new_value = 0  # 처음으로 돌아가기
    
    return new_value

@callback(
    Output("speed-state-stress", "data"),
    Input("speed-1x-stress", "n_clicks"),
    Input("speed-2x-stress", "n_clicks"),
    Input("speed-4x-stress", "n_clicks"),
    Input("speed-8x-stress", "n_clicks"),
    prevent_initial_call=True,
)
def set_stress_speed(speed_1x, speed_2x, speed_4x, speed_8x):
    """응력 재생 속도를 설정합니다."""
    ctx = dash.callback_context
    if not ctx.triggered:
        return {"speed": 1}
    
    button_id = ctx.triggered[0]['prop_id'].split('.')[0]
    
    if button_id == "speed-1x-stress":
        return {"speed": 1}
    elif button_id == "speed-2x-stress":
        return {"speed": 2}
    elif button_id == "speed-4x-stress":
        return {"speed": 4}
    elif button_id == "speed-8x-stress":
        return {"speed": 8}
    
    return {"speed": 1}

@callback(
    Output("unified-stress-colorbar-state", "data"),
    Input("btn-unified-stress-colorbar", "value"),
    prevent_initial_call=True,
)
def toggle_unified_stress_colorbar(switch_value):
    """응력바 통일 토글을 처리합니다."""
    return switch_value if switch_value is not None else False

@callback(
    Output("download-3d-stress-image", "data"),
    Output("btn-save-3d-stress-image", "children"),
    Output("btn-save-3d-stress-image", "disabled"),
    Input("btn-save-3d-stress-image", "n_clicks"),
    State("viewer-3d-stress-display", "figure"),
    State("tbl-concrete-stress", "selected_rows"),
    State("tbl-concrete-stress", "data"),
    State("time-slider-stress", "value"),
    prevent_initial_call=True,
)
def save_3d_stress_image(n_clicks, figure, selected_rows, tbl_data, time_value):
    """3D 응력 이미지를 저장합니다."""
    if not n_clicks or not figure or not selected_rows or not tbl_data:
        return None, "이미지 저장", False
    
    try:
        row = pd.DataFrame(tbl_data).iloc[selected_rows[0]]
        concrete_name = row["name"]
        
        # 시간 정보 추가
        time_info = ""
        if time_value is not None:
            frd_files = get_frd_files(row["concrete_pk"])
            if time_value < len(frd_files):
                filename = os.path.basename(frd_files[time_value])
                try:
                    time_str = filename.split(".")[0]
                    dt = datetime.strptime(time_str, "%Y%m%d%H")
                    time_info = f"_{dt.strftime('%Y%m%d_%H시')}"
                except:
                    time_info = f"_시간{time_value}"
        
        filename = f"응력분석_{concrete_name}{time_info}.png"
        
        # 이미지 데이터 생성 (실제로는 figure를 이미지로 변환하는 로직 필요)
        # 여기서는 더미 데이터 반환
        return dcc.send_bytes(
            b"dummy_image_data", 
            filename=filename
        ), "저장 완료!", True
        
    except Exception:
        return None, "저장 실패", False

@callback(
    Output("download-current-frd", "data"),
    Output("btn-save-current-frd", "children"),
    Output("btn-save-current-frd", "disabled"),
    Input("btn-save-current-frd", "n_clicks"),
    State("tbl-concrete-stress", "selected_rows"),
    State("tbl-concrete-stress", "data"),
    State("time-slider-stress", "value"),
    prevent_initial_call=True,
)
def save_current_frd(n_clicks, selected_rows, tbl_data, time_value):
    """현재 FRD 파일을 저장합니다."""
    if not n_clicks or not selected_rows or not tbl_data:
        return None, "FRD 파일 저장", False
    
    try:
        row = pd.DataFrame(tbl_data).iloc[selected_rows[0]]
        concrete_pk = row["concrete_pk"]
        concrete_name = row["name"]
        
        frd_files = get_frd_files(concrete_pk)
        if not frd_files or time_value is None or time_value >= len(frd_files):
            return None, "파일 없음", False
        
        source_file = frd_files[time_value]
        filename = f"응력분석_{concrete_name}_{os.path.basename(source_file)}"
        
        # 파일 복사 (실제로는 파일을 읽어서 반환하는 로직 필요)
        with open(source_file, 'rb') as f:
            file_data = f.read()
        
        return dcc.send_bytes(
            file_data, 
            filename=filename
        ), "저장 완료!", True
        
    except Exception:
        return None, "저장 실패", False


# 물성치 정보 파싱 함수 (온도분석 페이지에서 가져옴)
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

@callback(
    Output("btn-concrete-analyze-stress", "disabled"),
    Output("btn-concrete-del-stress", "disabled"),
    Input("tbl-concrete-stress", "selected_rows"),
    Input("project-url", "pathname"),
    State("tbl-concrete-stress", "data"),
    prevent_initial_call=True,
)
def on_concrete_select_stress(selected_rows, pathname, tbl_data):
    """콘크리트 선택 시 버튼 상태를 업데이트하고 전체 응력 범위를 미리 계산합니다."""
    # 응력 분석 페이지에서만 실행
    if '/stress' not in pathname:
        raise PreventUpdate
    
    if not selected_rows or not tbl_data:
        return True, True
    
    # 선택된 콘크리트의 전체 응력 범위 미리 계산
    row = pd.DataFrame(tbl_data).iloc[selected_rows[0]]
    concrete_pk = row["concrete_pk"]
    
    # 백그라운드에서 전체 범위 계산 (캐시에 저장됨)
    try:
        global_ranges = calculate_global_stress_ranges(concrete_pk)
        print(f"전체 응력 범위 계산 완료 - {concrete_pk}: {len(global_ranges)}개 성분")
    except Exception as e:
        print(f"전체 응력 범위 계산 중 오류: {e}")
    
    # 선택된 콘크리트가 있으면 버튼 활성화
    return False, False

@callback(
    Output("confirm-del-stress", "displayed"),
    Input("btn-concrete-del-stress", "n_clicks"),
    prevent_initial_call=True,
)
def show_delete_confirm_stress(n_clicks):
    """삭제 확인 다이얼로그를 표시합니다."""
    if n_clicks:
        return True
    return False


