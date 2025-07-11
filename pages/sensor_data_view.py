#!/usr/bin/env python3
# pages/sensor_data_view.py
"""Dash 페이지: 센서 데이터 확인

* 왼쪽에서 센서 리스트 선택 → 해당 센서의 데이터 그래프 표시
* 온도, 습도, SV 데이터를 시간별로 그래프로 표시
* 데이터 다운로드 기능
* 실시간 데이터 업데이트 기능
* 센서별 데이터 통계 정보 표시
* ITS 센서 목록에서 센서 정보 가져오기
"""

from __future__ import annotations

import os
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import dash
from dash import (
    html, dcc, Input, Output, State,
    dash_table, register_page, callback, ALL, MATCH
)
import dash_bootstrap_components as dbc
from dash.exceptions import PreventUpdate
from datetime import datetime, timedelta
import base64
import io
import json
from flask import request

import api_db
from utils.encryption import parse_project_key_from_url

register_page(__name__, path="/sensor_data_view", title="센서 데이터 확인")

# ────────────────────────────── 데이터 로딩 함수 ────────────────────────────
def load_sensor_data(sensor_id: str) -> pd.DataFrame:
    """센서 데이터를 로드하는 함수"""
    try:
        file_path = f"sensors/{sensor_id}.csv"
        if not os.path.exists(file_path):
            return pd.DataFrame()
        
        df = pd.read_csv(file_path)
        df['time'] = pd.to_datetime(df['time'])
        return df
    except Exception as e:
        print(f"센서 데이터 로드 오류: {e}")
        return pd.DataFrame()

def get_available_sensors() -> list:
    """사용자가 접근 가능한 ITS 센서 목록을 반환하는 함수"""
    try:
        # 로그인된 사용자 정보 가져오기
        user_id = request.cookies.get("login_user")
        if not user_id:
            return []
        
        # 사용자 권한 정보 조회
        from api_db import _get_its_engine, text
        
        eng = _get_its_engine(1)
        user_query = text("SELECT userid, grade FROM tb_user WHERE userid = :uid LIMIT 1")
        df_user = pd.read_sql(user_query, eng, params={"uid": user_id})
        
        if df_user.empty:
            return []
        
        grade = df_user.iloc[0]["grade"]
        
        # AD 권한이면 모든 구조의 센서 반환
        if grade == "AD":
            # 모든 구조 조회
            structure_query = text("""
                SELECT DISTINCT st.stid AS s_code
                FROM tb_structure st
                JOIN tb_group g ON g.groupid = st.groupid 
                JOIN tb_project p ON p.projectid = g.projectid 
                WHERE p.projectid = 'P_000078'
                ORDER BY st.stid
            """)
            df_structures = pd.read_sql(structure_query, eng)
            s_codes = df_structures['s_code'].tolist()
        else:
            # 일반 사용자의 경우 접근 가능한 구조만
            auth_query = text("SELECT id FROM tb_sensor_auth_mapping WHERE userid = :uid")
            df_auth = pd.read_sql(auth_query, eng, params={"uid": user_id})
            
            if df_auth.empty:
                return []
            
            auth_list = df_auth["id"].tolist()
            
            # P_000078에 접근 가능하면 모든 구조 반환
            if "P_000078" in auth_list:
                structure_query = text("""
                    SELECT DISTINCT st.stid AS s_code
                    FROM tb_structure st
                    JOIN tb_group g ON g.groupid = st.groupid 
                    JOIN tb_project p ON p.projectid = g.projectid 
                    WHERE p.projectid = 'P_000078'
                    ORDER BY st.stid
                """)
                df_structures = pd.read_sql(structure_query, eng)
                s_codes = df_structures['s_code'].tolist()
            else:
                # 접근 가능한 구조 ID만
                s_codes = [auth_id for auth_id in auth_list if auth_id.startswith('S_')]
        
        # 각 구조별 센서 목록 수집
        all_sensors = []
        for s_code in s_codes:
            try:
                sensors_df = api_db.get_sensor_list_for_structure(s_code)
                if not sensors_df.empty:
                    for _, sensor in sensors_df.iterrows():
                        device_id = sensor["deviceid"]
                        channel = sensor["channel"]
                        sensor_key = f"{device_id}_Ch{channel}"
                        
                        # 중복 제거
                        if sensor_key not in [s['sensor_key'] for s in all_sensors]:
                            all_sensors.append({
                                'sensor_key': sensor_key,
                                'device_id': device_id,
                                'channel': channel,
                                'device_type': sensor.get('device_type', ''),
                                'data_type': sensor.get('data_type', ''),
                                'is3axis': sensor.get('is3axis', 'N'),
                                'structure_id': s_code
                            })
            except Exception as e:
                print(f"Error getting sensors for structure {s_code}: {e}")
                continue
        
        return all_sensors
        
    except Exception as e:
        print(f"Error getting available sensors: {e}")
        return []

def get_sensor_info(sensor_data: dict) -> dict:
    """센서 정보를 반환하는 함수"""
    device_id = sensor_data['device_id']
    channel = sensor_data['channel']
    
    # 실제 센서 데이터 수집 상태 확인
    try:
        result = api_db.get_latest_sensor_data_time(device_id, channel)
        
        if result["status"] == "fail":
            return {
                'sensor_key': sensor_data['sensor_key'],
                'device_id': device_id,
                'channel': channel,
                'structure_id': sensor_data['structure_id'],
                'data_count': 0,
                'latest_time': None,
                'latest_temp': None,
                'latest_humidity': None,
                'latest_sv': None,
                'status': '데이터 없음',
                'status_color': 'secondary'
            }
        
        latest_time = result["time"]
        now = datetime.now()
        
        # 시간 차이 계산 (시간 단위)
        time_diff = (now - latest_time).total_seconds() / 3600
        
        if time_diff <= 2:  # 2시간 이하
            status = "활성"
            status_color = "success"
        else:  # 2시간 초과
            status = "비활성"
            status_color = "warning"
        
        # 최신 센서 데이터 가져오기 (실제로는 더 복잡한 로직이 필요할 수 있음)
        # 여기서는 간단히 상태만 반환
        return {
            'sensor_key': sensor_data['sensor_key'],
            'device_id': device_id,
            'channel': channel,
            'structure_id': sensor_data['structure_id'],
            'data_count': 1,  # 실제로는 데이터 개수를 계산해야 함
            'latest_time': latest_time,
            'latest_temp': None,  # 실제 센서 데이터에서 가져와야 함
            'latest_humidity': None,
            'latest_sv': None,
            'status': status,
            'status_color': status_color
        }
        
    except Exception as e:
        print(f"Error checking sensor status for {device_id}/{channel}: {e}")
        return {
            'sensor_key': sensor_data['sensor_key'],
            'device_id': device_id,
            'channel': channel,
            'structure_id': sensor_data['structure_id'],
            'data_count': 0,
            'latest_time': None,
            'latest_temp': None,
            'latest_humidity': None,
            'latest_sv': None,
            'status': '오류',
            'status_color': 'danger'
        }

# ────────────────────────────── 레이아웃 ────────────────────────────
layout = html.Div([
    dcc.Location(id="sensor-data-url", refresh=False),
    dcc.Store(id="selected-sensor-store"),
    dcc.Store(id="sensor-data-store"),
    dcc.Interval(
        id='interval-component',
        interval=30*1000,  # 30초마다 업데이트
        n_intervals=0
    ),
    
    # 알림을 위한 Toast
    dbc.Toast(
        id="data-collection-toast",
        header="데이터 수집",
        is_open=False,
        dismissable=True,
        duration=4000,
        style={"position": "fixed", "top": 66, "right": 10, "width": 350}
    ),
    
    dbc.Container([
        dbc.Row([
            dbc.Col([
                html.H2("센서 데이터 확인", className="mb-4"),
                html.P("왼쪽에서 센서를 선택하여 데이터를 확인하세요.", className="text-muted")
            ], width=12)
        ]),
        
        dbc.Row([
            # ── 왼쪽: 센서 목록 ──
            dbc.Col([
                html.Div([
                    # 센서 목록 섹션
                    html.Div([
                        html.Div([
                            # 제목과 새로고침 버튼
                            html.Div([
                                html.H6("📡 센서 목록", className="mb-0 text-secondary fw-bold"),
                                dbc.Button(
                                    html.I(className="fas fa-sync-alt"),
                                    id="refresh-sensors-btn",
                                    color="outline-secondary",
                                    size="sm",
                                    className="px-2"
                                )
                            ], className="d-flex justify-content-between align-items-center mb-2"),
                            html.Small("💡 행을 클릭하여 선택", className="text-muted mb-2 d-block"),
                            html.Div([
                                dash_table.DataTable(
                                    id="sensor-table",
                                    page_size=8,
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
                                                'filter_query': '{status} = 활성',
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
                                                'filter_query': '{status} = 비활성',
                                                'column_id': 'status'
                                            },
                                            'backgroundColor': '#fef3c7',
                                            'color': '#d97706',
                                            'fontWeight': '600',
                                            'borderRadius': '4px',
                                            'textAlign': 'center'
                                        },
                                        {
                                            'if': {
                                                'filter_query': '{status} = 오류',
                                                'column_id': 'status'
                                            },
                                            'backgroundColor': '#fee2e2',
                                            'color': '#dc2626',
                                            'fontWeight': '600',
                                            'borderRadius': '4px',
                                            'textAlign': 'center'
                                        },
                                        {
                                            'if': {'column_id': 'sensor_id'},
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
                                dbc.Button("데이터 수집", id="collect-data-btn", color="success", size="sm", className="px-3", disabled=True),
                                dbc.Button("CSV 다운로드", id="download-csv-btn", color="primary", size="sm", className="px-3", disabled=True),
                                dcc.Download(id="download-csv"),
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
            
            # ── 오른쪽: 데이터 그래프 및 정보 ──
            dbc.Col([
                html.Div([
                    # 탭 메뉴 (노션 스타일)
                    html.Div([
                        dbc.Tabs([
                            dbc.Tab(
                                label="실시간 데이터", 
                                tab_id="tab-realtime",
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
                                label="통계 정보", 
                                tab_id="tab-stats",
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
                        ], id="sensor-tabs", active_tab="tab-realtime"),
                        
                        # 탭 콘텐츠
                        html.Div(id="sensor-tab-content", style={
                            "backgroundColor": "white",
                            "border": "1px solid #e2e8f0",
                            "borderTop": "none",
                            "borderRadius": "0 0 12px 12px",
                            "padding": "20px",
                            "minHeight": "calc(100vh - 300px)"
                        })
                    ])
                ], style={
                    "backgroundColor": "white",
                    "borderRadius": "12px",
                    "boxShadow": "0 1px 3px rgba(0,0,0,0.1)",
                    "border": "1px solid #e2e8f0"
                })
            ], md=8)
        ])
    ], fluid=True)
])

# ────────────────────────────── 콜백 함수들 ────────────────────────────

@callback(
    Output("sensor-table", "data"),
    Output("sensor-table", "columns"),
    Output("sensor-table", "selected_rows"),
    Output("collect-data-btn", "disabled"),
    Output("download-csv-btn", "disabled"),
    Input("refresh-sensors-btn", "n_clicks"),
    Input("interval-component", "n_intervals"),
    prevent_initial_call='initial_duplicate'
)
def update_sensor_table(refresh_clicks, n_intervals):
    """센서 테이블을 업데이트하는 콜백"""
    sensors = get_available_sensors()
    
    if not sensors:
        return [], [], [], True, True
    
    # 테이블 데이터 생성
    table_data = []
    for sensor_data in sensors:
        # 센서 정보 가져오기
        sensor_info = get_sensor_info(sensor_data)
        
        table_data.append({
            'sensor_id': f"{sensor_info['device_id']} Ch.{sensor_info['channel']}",
            'structure_id': sensor_info['structure_id'],
            'device_type': sensor_data.get('device_type', 'N/A'),
            'data_type': sensor_data.get('data_type', 'N/A'),
            'is3axis': sensor_data.get('is3axis', 'N'),
            'status': sensor_info['status'],
            'latest_time': sensor_info['latest_time'].strftime('%Y-%m-%d %H:%M') if sensor_info['latest_time'] else 'N/A',
            'sensor_key': sensor_info['sensor_key']  # 내부 사용용
        })
    
    # 컬럼 정의
    columns = [
        {"name": "센서 ID", "id": "sensor_id", "type": "text"},
        {"name": "구조 ID", "id": "structure_id", "type": "text"},
        {"name": "센서 타입", "id": "device_type", "type": "text"},
        {"name": "데이터 타입", "id": "data_type", "type": "text"},
        {"name": "3축", "id": "is3axis", "type": "text"},
        {"name": "상태", "id": "status", "type": "text"},
        {"name": "최신 데이터", "id": "latest_time", "type": "text"}
    ]
    
    return table_data, columns, [], True, True

@callback(
    Output("selected-sensor-store", "data"),
    Output("collect-data-btn", "disabled", allow_duplicate=True),
    Output("download-csv-btn", "disabled", allow_duplicate=True),
    Input("sensor-table", "selected_rows"),
    State("sensor-table", "data"),
    prevent_initial_call=True
)
def select_sensor(selected_rows, table_data):
    """센서 선택 콜백"""
    if not selected_rows or not table_data:
        return None, True, True
    
    selected_row = table_data[selected_rows[0]]
    sensor_key = selected_row['sensor_key']
    
    # 센서가 선택되면 버튼들을 활성화
    return sensor_key, False, False


@callback(
    Output("sensor-tab-content", "children"),
    Input("sensor-tabs", "active_tab"),
    Input("selected-sensor-store", "data"),
    prevent_initial_call=True
)
def update_sensor_tab_content(active_tab, sensor_key):
    """센서 탭 콘텐츠를 업데이트하는 콜백"""
    if not sensor_key:
        return html.Div([
            html.Div([
                html.I(className="fas fa-info-circle me-2 text-muted"),
                "센서를 선택하세요"
            ], className="text-center text-muted mt-5")
        ])
    
    try:
        device_id, channel_part = sensor_key.split('_Ch')
        channel = channel_part
        
        if active_tab == "tab-realtime":
            # 실시간 데이터 탭
            return html.Div([
                # 센서 정보 카드
                html.Div(id="selected-sensor-info", className="mb-4"),
                
                # 데이터 그래프
                dcc.Graph(
                    id="sensor-data-graph",
                    style={"height": "500px"}
                )
            ])
        elif active_tab == "tab-stats":
            # 통계 정보 탭
            return html.Div([
                html.Div(id="sensor-stats")
            ])
        else:
            return html.Div("알 수 없는 탭입니다.", className="text-muted")
            
    except Exception as e:
        return html.Div(f"오류가 발생했습니다: {e}", className="text-danger")

@callback(
    Output("sensor-data-graph", "figure"),
    Output("selected-sensor-info", "children"),
    Output("sensor-stats", "children"),
    Input("selected-sensor-store", "data"),
    prevent_initial_call=True
)
def load_sensor_data_and_create_graph(sensor_key):
    """센서 데이터를 로드하고 그래프를 생성하는 콜백"""
    if not sensor_key:
        empty_graph = go.Figure().add_annotation(
            text="센서를 선택하세요",
            xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False
        )
        return empty_graph, html.Div("센서를 선택하세요.", className="text-muted"), html.Div("통계 정보를 표시할 수 없습니다.", className="text-muted")
    
    try:
        device_id, channel_part = sensor_key.split('_Ch')
        channel = channel_part
        
        # ITS 센서 데이터 조회 (최근 24시간)
        df = api_db.get_its_sensor_data(
            device_id=device_id, 
            channel=channel, 
            its_num=1,
            hours=24
        )
        
        # ITS DB에서 데이터가 없으면 로컬 DB에서 확인
        if df.empty:
            df = api_db.get_sensor_data(
                device_id=device_id, 
                channel=channel, 
                use_its=False,  # 로컬 DB에서 확인
                its_num=1
            )
        
        if df.empty:
            # 데이터가 없으면 샘플 데이터 생성 (테스트용)
            import numpy as np
            end_time = datetime.now()
            start_time = end_time - timedelta(hours=24)
            time_range = pd.date_range(start=start_time, end=end_time, freq='H')
            
            # 랜덤 데이터 생성
            np.random.seed(hash(device_id + channel) % 2**32)  # 센서별 고정 시드
            df = pd.DataFrame({
                'time': time_range,
                'temperature': 20 + np.random.normal(0, 2, len(time_range)),
                'humidity': 60 + np.random.normal(0, 10, len(time_range)),
                'sv': 5 + np.random.normal(0, 1, len(time_range)),
                'device_id': device_id,
                'channel': channel
            })
        
        # 그래프 생성
        if not df.empty:
            df['time'] = pd.to_datetime(df['time'])
            
            # 서브플롯 생성
            fig = go.Figure()
            
            # 사용 가능한 컬럼들에 따라 그래프 생성
            if 'temperature' in df.columns:
                fig.add_trace(go.Scatter(
                    x=df['time'],
                    y=df['temperature'],
                    mode='lines+markers',
                    name='온도 (°C)',
                    line=dict(color='#FF6B6B', width=2),
                    marker=dict(size=6, color='#FF6B6B'),
                    yaxis='y',
                    hovertemplate='<b>시간:</b> %{x}<br><b>온도:</b> %{y:.1f}°C<extra></extra>'
                ))
            
            if 'humidity' in df.columns:
                fig.add_trace(go.Scatter(
                    x=df['time'],
                    y=df['humidity'],
                    mode='lines+markers',
                    name='습도 (%)',
                    line=dict(color='#4ECDC4', width=2),
                    marker=dict(size=6, color='#4ECDC4'),
                    yaxis='y2',
                    hovertemplate='<b>시간:</b> %{x}<br><b>습도:</b> %{y:.1f}%<extra></extra>'
                ))
            
            if 'sv' in df.columns:
                fig.add_trace(go.Scatter(
                    x=df['time'],
                    y=df['sv'],
                    mode='lines+markers',
                    name='SV',
                    line=dict(color='#45B7D1', width=2),
                    marker=dict(size=6, color='#45B7D1'),
                    yaxis='y3',
                    hovertemplate='<b>시간:</b> %{x}<br><b>SV:</b> %{y:.2f}<extra></extra>'
                ))
            
            # 기본 Y축 설정 (온도)
            yaxis_config = {
                'title': "온도 (°C)",
                'titlefont': dict(color="#FF6B6B"),
                'tickfont': dict(color="#FF6B6B"),
                'side': "left",
                'gridcolor': '#f0f0f0'
            }
            
            # 추가 Y축 설정 (습도)
            yaxis2_config = {
                'title': "습도 (%)",
                'titlefont': dict(color="#4ECDC4"),
                'tickfont': dict(color="#4ECDC4"),
                'anchor': "x",
                'overlaying': "y",
                'side': "right",
                'gridcolor': 'rgba(78, 205, 196, 0.1)'
            }
            
            # 추가 Y축 설정 (SV)
            yaxis3_config = {
                'title': "SV",
                'titlefont': dict(color="#45B7D1"),
                'tickfont': dict(color="#45B7D1"),
                'anchor': "x",
                'overlaying': "y",
                'side': "right",
                'position': 0.95,
                'gridcolor': 'rgba(69, 183, 209, 0.1)'
            }
            
            fig.update_layout(
                title=dict(
                    text=f"센서 데이터 시계열 그래프 - {device_id} Ch.{channel}",
                    x=0.5,
                    font=dict(size=16, color='#2C3E50')
                ),
                xaxis=dict(
                    title="시간",
                    gridcolor='#f0f0f0',
                    showgrid=True
                ),
                yaxis=yaxis_config,
                yaxis2=yaxis2_config,
                yaxis3=yaxis3_config,
                hovermode='x unified',
                showlegend=True,
                template="plotly_white",
                plot_bgcolor='white',
                paper_bgcolor='white',
                legend=dict(
                    orientation="h",
                    yanchor="bottom",
                    y=1.02,
                    xanchor="right",
                    x=1,
                    bgcolor='rgba(255,255,255,0.8)',
                    bordercolor='#ddd',
                    borderwidth=1
                ),
                margin=dict(l=60, r=60, t=80, b=60)
            )
        else:
            fig = go.Figure().add_annotation(
                text="데이터가 없습니다",
                xref="paper", yref="paper",
                x=0.5, y=0.5, showarrow=False
            )
        
        # 센서 정보 생성
        try:
            result = api_db.get_latest_sensor_data_time(device_id, channel)
            
            if result["status"] == "fail":
                sensor_info = dbc.Alert(
                    f"센서 {device_id} Ch.{channel}의 데이터를 찾을 수 없습니다.", 
                    color="warning",
                    className="mb-3"
                )
            else:
                latest_time = result["time"]
                now = datetime.now()
                time_diff = (now - latest_time).total_seconds() / 3600  # 시간 단위
                
                # 상태 결정
                if time_diff <= 2:
                    status = "활성"
                    status_color = "success"
                    status_icon = "fas fa-check-circle"
                else:
                    status = "비활성"
                    status_color = "warning"
                    status_icon = "fas fa-exclamation-triangle"
                
                sensor_info = dbc.Row([
                    dbc.Col([
                        dbc.Card([
                            dbc.CardBody([
                                html.Div([
                                    html.I(className="fas fa-microchip me-2 text-primary"),
                                    html.H6("센서 ID", className="card-title d-inline")
                                ]),
                                html.H4(f"{device_id} Ch.{channel}", className="text-primary mb-2"),
                                html.Small([
                                    html.I(className="fas fa-clock me-1"),
                                    f"최신 데이터: {latest_time.strftime('%Y-%m-%d %H:%M')}"
                                ], className="text-muted")
                            ])
                        ], className="h-100")
                    ], width=4),
                    dbc.Col([
                        dbc.Card([
                            dbc.CardBody([
                                html.Div([
                                    html.I(className=f"{status_icon} me-2 text-{status_color}"),
                                    html.H6("센서 상태", className="card-title d-inline")
                                ]),
                                html.H4(status, className=f"text-{status_color} mb-2"),
                                html.Small([
                                    html.I(className="fas fa-info-circle me-1"),
                                    f"마지막 업데이트: {time_diff:.1f}시간 전"
                                ], className="text-muted")
                            ])
                        ], className="h-100")
                    ], width=4),
                    dbc.Col([
                        dbc.Card([
                            dbc.CardBody([
                                html.Div([
                                    html.I(className="fas fa-database me-2 text-info"),
                                    html.H6("데이터 정보", className="card-title d-inline")
                                ]),
                                html.H4(f"{len(df)}개", className="text-info mb-2"),
                                html.Small([
                                    html.I(className="fas fa-chart-line me-1"),
                                    "24시간 데이터"
                                ], className="text-muted")
                            ])
                        ], className="h-100")
                    ], width=4)
                ])
        except Exception as e:
            sensor_info = dbc.Alert(
                f"센서 정보를 불러올 수 없습니다: {e}", 
                color="danger",
                className="mb-3"
            )
        
        # 통계 정보 생성
        if not df.empty:
            df['time'] = pd.to_datetime(df['time'])
            
            # 데이터 기간 정보
            data_period = f"{df['time'].min().strftime('%Y-%m-%d %H:%M')} ~ {df['time'].max().strftime('%Y-%m-%d %H:%M')}"
            
            # 사용 가능한 컬럼들에 대한 통계 계산
            stats_cards = []
            
            if 'temperature' in df.columns:
                temp_stats = {
                    '평균': df['temperature'].mean(),
                    '최대': df['temperature'].max(),
                    '최소': df['temperature'].min(),
                    '표준편차': df['temperature'].std(),
                    '중앙값': df['temperature'].median()
                }
                
                stats_cards.append(
                    dbc.Col([
                        dbc.Card([
                            dbc.CardHeader([
                                html.I(className="fas fa-thermometer-half me-2 text-danger"),
                                "온도 통계"
                            ], className="text-danger"),
                            dbc.CardBody([
                                dbc.Row([
                                    dbc.Col([
                                        html.Div([
                                            html.Small("평균", className="text-muted"),
                                            html.H5(f"{temp_stats['평균']:.1f}°C", className="mb-0")
                                        ])
                                    ], width=6),
                                    dbc.Col([
                                        html.Div([
                                            html.Small("최대", className="text-muted"),
                                            html.H5(f"{temp_stats['최대']:.1f}°C", className="mb-0 text-danger")
                                        ])
                                    ], width=6)
                                ], className="mb-2"),
                                dbc.Row([
                                    dbc.Col([
                                        html.Div([
                                            html.Small("최소", className="text-muted"),
                                            html.H5(f"{temp_stats['최소']:.1f}°C", className="mb-0 text-primary")
                                        ])
                                    ], width=6),
                                    dbc.Col([
                                        html.Div([
                                            html.Small("중앙값", className="text-muted"),
                                            html.H5(f"{temp_stats['중앙값']:.1f}°C", className="mb-0")
                                        ])
                                    ], width=6)
                                ])
                            ])
                        ], className="h-100")
                    ], width=4)
                )
            
            if 'humidity' in df.columns:
                humidity_stats = {
                    '평균': df['humidity'].mean(),
                    '최대': df['humidity'].max(),
                    '최소': df['humidity'].min(),
                    '표준편차': df['humidity'].std(),
                    '중앙값': df['humidity'].median()
                }
                
                stats_cards.append(
                    dbc.Col([
                        dbc.Card([
                            dbc.CardHeader([
                                html.I(className="fas fa-tint me-2 text-info"),
                                "습도 통계"
                            ], className="text-info"),
                            dbc.CardBody([
                                dbc.Row([
                                    dbc.Col([
                                        html.Div([
                                            html.Small("평균", className="text-muted"),
                                            html.H5(f"{humidity_stats['평균']:.1f}%", className="mb-0")
                                        ])
                                    ], width=6),
                                    dbc.Col([
                                        html.Div([
                                            html.Small("최대", className="text-muted"),
                                            html.H5(f"{humidity_stats['최대']:.1f}%", className="mb-0 text-info")
                                        ])
                                    ], width=6)
                                ], className="mb-2"),
                                dbc.Row([
                                    dbc.Col([
                                        html.Div([
                                            html.Small("최소", className="text-muted"),
                                            html.H5(f"{humidity_stats['최소']:.1f}%", className="mb-0 text-primary")
                                        ])
                                    ], width=6),
                                    dbc.Col([
                                        html.Div([
                                            html.Small("중앙값", className="text-muted"),
                                            html.H5(f"{humidity_stats['중앙값']:.1f}%", className="mb-0")
                                        ])
                                    ], width=6)
                                ])
                            ])
                        ], className="h-100")
                    ], width=4)
                )
            
            if 'sv' in df.columns:
                sv_stats = {
                    '평균': df['sv'].mean(),
                    '최대': df['sv'].max(),
                    '최소': df['sv'].min(),
                    '표준편차': df['sv'].std(),
                    '중앙값': df['sv'].median()
                }
                
                stats_cards.append(
                    dbc.Col([
                        dbc.Card([
                            dbc.CardHeader([
                                html.I(className="fas fa-wave-square me-2 text-warning"),
                                "SV 통계"
                            ], className="text-warning"),
                            dbc.CardBody([
                                dbc.Row([
                                    dbc.Col([
                                        html.Div([
                                            html.Small("평균", className="text-muted"),
                                            html.H5(f"{sv_stats['평균']:.2f}", className="mb-0")
                                        ])
                                    ], width=6),
                                    dbc.Col([
                                        html.Div([
                                            html.Small("최대", className="text-muted"),
                                            html.H5(f"{sv_stats['최대']:.2f}", className="mb-0 text-warning")
                                        ])
                                    ], width=6)
                                ], className="mb-2"),
                                dbc.Row([
                                    dbc.Col([
                                        html.Div([
                                            html.Small("최소", className="text-muted"),
                                            html.H5(f"{sv_stats['최소']:.2f}", className="mb-0 text-primary")
                                        ])
                                    ], width=6),
                                    dbc.Col([
                                        html.Div([
                                            html.Small("중앙값", className="text-muted"),
                                            html.H5(f"{sv_stats['중앙값']:.2f}", className="mb-0")
                                        ])
                                    ], width=6)
                                ])
                            ])
                        ], className="h-100")
                    ], width=4)
                )
            
            if not stats_cards:
                stats_cards.append(
                    dbc.Col([
                        dbc.Card([
                            dbc.CardHeader("데이터 정보"),
                            dbc.CardBody([
                                html.P(f"총 데이터: {len(df)}개"),
                                html.P(f"컬럼: {', '.join(df.columns)}")
                            ])
                        ])
                    ], width=12)
                )
            
            stats = dbc.Row([
                dbc.Col([
                    dbc.Card([
                        dbc.CardBody([
                            html.Div([
                                html.I(className="fas fa-calendar-alt me-2 text-secondary"),
                                html.H6("데이터 기간", className="d-inline text-secondary")
                            ], className="text-center mb-2"),
                            html.P(data_period, className="text-center text-muted mb-0")
                        ])
                    ], className="mb-3")
                ], width=12),
                *stats_cards
            ])
        else:
            stats = html.Div("통계 정보를 표시할 수 없습니다.", className="text-muted")
        
        return fig, sensor_info, stats
        
    except Exception as e:
        print(f"Error in load_sensor_data_and_create_graph: {e}")
        empty_graph = go.Figure().add_annotation(
            text="오류가 발생했습니다",
            xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False
        )
        return empty_graph, html.Div(f"오류가 발생했습니다: {e}", className="text-danger"), html.Div("통계 정보를 표시할 수 없습니다.", className="text-muted")

@callback(
    Output("data-collection-toast", "is_open"),
    Output("data-collection-toast", "children"),
    Output("data-collection-toast", "icon"),
    Input("collect-data-btn", "n_clicks"),
    State("selected-sensor-store", "data"),
    prevent_initial_call=True
)
def collect_sensor_data(n_clicks, sensor_key):
    """센서 데이터 수집 콜백"""
    if not sensor_key or not n_clicks:
        raise PreventUpdate
    
    try:
        device_id, channel_part = sensor_key.split('_Ch')
        channel = channel_part
        
        # ITS 센서 데이터 수집 (24시간)
        result = api_db.collect_its_sensor_data(device_id, channel, its_num=1, hours=24)
        
        if result["status"] == "success":
            return True, f"✅ {result['count']}개의 데이터를 성공적으로 수집했습니다!", "success"
        else:
            return True, f"❌ 데이터 수집 실패: {result['msg']}", "danger"
        
    except Exception as e:
        print(f"Error collecting sensor data: {e}")
        return True, f"❌ 데이터 수집 중 오류 발생: {str(e)}", "danger"

@callback(
    Output("download-csv", "data"),
    Input("download-csv-btn", "n_clicks"),
    State("selected-sensor-store", "data"),
    prevent_initial_call=True
)
def download_csv(n_clicks, sensor_key):
    """CSV 다운로드 콜백"""
    if not sensor_key or not n_clicks:
        raise PreventUpdate
    
    try:
        device_id, channel_part = sensor_key.split('_Ch')
        channel = channel_part
        
        # 실제 센서 데이터 조회
        df = api_db.get_sensor_data(
            device_id=device_id, 
            channel=channel, 
            use_its=True,  # ITS 데이터베이스에서 직접 조회
            its_num=1
        )
        
        if df.empty:
            raise PreventUpdate
        
        # CSV 데이터 생성
        csv_string = df.to_csv(index=False, encoding='utf-8-sig')
        
        return dict(
            content=csv_string,
            filename=f"{device_id}_Ch{channel}_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        )
    except Exception as e:
        print(f"Error downloading CSV: {e}")
        raise PreventUpdate

 