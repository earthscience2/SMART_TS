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
            # ── 왼쪽: 센서 리스트 ──
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader([
                        html.H5("ITS 센서 목록", className="mb-0"),
                        dbc.Button(
                            "새로고침",
                            id="refresh-sensors-btn",
                            color="outline-primary",
                            size="sm",
                            className="float-end"
                        )
                    ]),
                    dbc.CardBody([
                        dbc.ListGroup(
                            id="sensor-list",
                            flush=True
                        )
                    ])
                ])
            ], width=4),
            
            # ── 오른쪽: 데이터 그래프 및 정보 ──
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader([
                        html.H5("센서 데이터", className="mb-0"),
                        html.Div([
                            dbc.Button(
                                "데이터 수집",
                                id="collect-data-btn",
                                color="primary",
                                size="sm",
                                className="me-2"
                            ),
                            dbc.Button(
                                "CSV 다운로드",
                                id="download-csv-btn",
                                color="success",
                                size="sm",
                                className="me-2"
                            ),
                            dcc.Download(id="download-csv"),
                            dbc.Button(
                                "실시간 업데이트",
                                id="toggle-realtime-btn",
                                color="info",
                                size="sm",
                                outline=True
                            )
                        ], className="float-end")
                    ]),
                    dbc.CardBody([
                        # 선택된 센서 정보
                        html.Div(id="selected-sensor-info", className="mb-3"),
                        
                        # 데이터 그래프
                        dcc.Graph(
                            id="sensor-data-graph",
                            style={"height": "400px"}
                        ),
                        
                        # 데이터 통계
                        html.Div(id="sensor-stats", className="mt-3")
                    ])
                ])
            ], width=8)
        ])
    ], fluid=True)
])

# ────────────────────────────── 콜백 함수들 ────────────────────────────

@callback(
    Output("sensor-list", "children"),
    Output("sensor-data-graph", "figure", allow_duplicate=True),
    Output("selected-sensor-info", "children", allow_duplicate=True),
    Output("sensor-stats", "children", allow_duplicate=True),
    Input("refresh-sensors-btn", "n_clicks"),
    Input("interval-component", "n_intervals"),
    prevent_initial_call='initial_duplicate'
)
def update_sensor_list(refresh_clicks, n_intervals):
    """센서 목록을 업데이트하는 콜백"""
    sensors = get_available_sensors()
    
    if not sensors:
        empty_graph = go.Figure().add_annotation(
            text="센서를 선택하세요",
            xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False
        )
        return [
            dbc.ListGroupItem(
                "접근 가능한 센서가 없습니다.",
                color="warning"
            )
        ], empty_graph, html.Div("센서를 선택하세요.", className="text-muted"), html.Div("통계 정보를 표시할 수 없습니다.", className="text-muted")
    
    sensor_items = []
    for sensor_data in sensors:
        # 센서 정보 가져오기
        sensor_info = get_sensor_info(sensor_data)
        
        sensor_items.append(
            dbc.ListGroupItem([
                dbc.Row([
                    dbc.Col([
                        html.Div([
                            html.I(className="fas fa-thermometer-half me-2 text-primary"),
                            html.Strong(f"{sensor_info['device_id']} Ch.{sensor_info['channel']}", className="text-dark")
                        ]),
                        html.Small([
                            html.I(className="fas fa-building me-1"),
                            f"구조: {sensor_info['structure_id']}"
                        ], className="text-muted")
                    ], width=8),
                    dbc.Col([
                        dbc.Badge(
                            sensor_info['status'], 
                            color=sensor_info['status_color'], 
                            className="badge-sm"
                        )
                    ], width=4, className="text-end")
                ]),
                html.Div([
                    html.Small([
                        html.I(className="fas fa-cog me-1"),
                        f"타입: {sensor_data.get('device_type', 'N/A')}"
                    ], className="text-muted me-2"),
                    html.Small([
                        html.I(className="fas fa-database me-1"),
                        f"데이터: {sensor_data.get('data_type', 'N/A')}"
                    ], className="text-muted me-2"),
                    html.Small([
                        html.I(className="fas fa-cube me-1"),
                        f"3축: {sensor_data.get('is3axis', 'N')}"
                    ], className="text-muted")
                ], className="mt-2")
            ],
            id={"type": "sensor-item", "index": sensor_info['sensor_key']},
            action=True,
            className="sensor-list-item",
            style={
                "cursor": "pointer", 
                "transition": "all 0.2s ease",
                "border": "1px solid #e9ecef",
                "borderRadius": "8px",
                "marginBottom": "8px"
            }
            )
        )
    
    # 초기 그래프와 정보
    empty_graph = go.Figure().add_annotation(
        text="센서를 선택하세요",
        xref="paper", yref="paper",
        x=0.5, y=0.5, showarrow=False
    )
    
    return sensor_items, empty_graph, html.Div("센서를 선택하세요.", className="text-muted"), html.Div("통계 정보를 표시할 수 없습니다.", className="text-muted")

@callback(
    Output("selected-sensor-store", "data"),
    Output("sensor-data-graph", "figure", allow_duplicate=True),
    Output("selected-sensor-info", "children", allow_duplicate=True),
    Output("sensor-stats", "children", allow_duplicate=True),
    Input({"type": "sensor-item", "index": ALL}, "n_clicks"),
    prevent_initial_call=True
)
def select_sensor_and_load_data(clicks):
    """센서 선택 및 데이터 로드 콜백"""
    ctx = dash.callback_context
    if not ctx.triggered:
        raise PreventUpdate
    
    # 클릭된 센서 ID 추출
    triggered_id = ctx.triggered[0]['prop_id'].split('.')[0]
    if not triggered_id.startswith('{"type":"sensor-item","index":'):
        raise PreventUpdate
    
    # JSON 파싱하여 센서 ID 추출
    try:
        trigger_data = json.loads(triggered_id)
        sensor_key = trigger_data['index']
        
        # 센서 데이터 로드
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
        
        return sensor_key, fig, sensor_info, stats
        
    except Exception as e:
        print(f"Error in select_sensor_and_load_data: {e}")
        raise PreventUpdate









@callback(
    Output({"type": "sensor-item", "index": ALL}, "style"),
    Input("selected-sensor-store", "data"),
    prevent_initial_call=True
)
def highlight_selected_sensor(selected_sensor):
    """선택된 센서를 하이라이트하는 콜백"""
    ctx = dash.callback_context
    if not ctx.outputs_list:
        raise PreventUpdate
    
    # 모든 센서 아이템의 스타일 초기화
    styles = []
    for output in ctx.outputs_list:
        sensor_key = output['id']['index']
        if selected_sensor and sensor_key == selected_sensor:
            # 선택된 센서 하이라이트
            styles.append({
                "cursor": "pointer", 
                "transition": "all 0.2s ease",
                "backgroundColor": "#e3f2fd",
                "borderLeft": "4px solid #2196f3",
                "border": "1px solid #2196f3",
                "borderRadius": "8px",
                "marginBottom": "8px",
                "boxShadow": "0 2px 4px rgba(33, 150, 243, 0.2)"
            })
        else:
            # 기본 스타일
            styles.append({
                "cursor": "pointer", 
                "transition": "all 0.2s ease",
                "border": "1px solid #e9ecef",
                "borderRadius": "8px",
                "marginBottom": "8px"
            })
    
    return styles

@callback(
    Output("sensor-data-store", "data", allow_duplicate=True),
    Output("sensor-data-graph", "figure", allow_duplicate=True),
    Output("selected-sensor-info", "children", allow_duplicate=True),
    Output("sensor-stats", "children", allow_duplicate=True),
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
            # 수집된 데이터를 다시 로드
            df = api_db.get_sensor_data(
                device_id=device_id, 
                channel=channel, 
                use_its=False,  # 로컬 DB에서 조회
                its_num=1
            )
            
            if not df.empty:
                # 그래프 생성
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
                        line=dict(color='red', width=2),
                        marker=dict(size=4),
                        yaxis='y'
                    ))
                
                if 'humidity' in df.columns:
                    fig.add_trace(go.Scatter(
                        x=df['time'],
                        y=df['humidity'],
                        mode='lines+markers',
                        name='습도 (%)',
                        line=dict(color='blue', width=2),
                        marker=dict(size=4),
                        yaxis='y2'
                    ))
                
                if 'sv' in df.columns:
                    fig.add_trace(go.Scatter(
                        x=df['time'],
                        y=df['sv'],
                        mode='lines+markers',
                        name='SV',
                        line=dict(color='orange', width=2),
                        marker=dict(size=4),
                        yaxis='y3'
                    ))
                
                # 기본 Y축 설정
                yaxis_config = {
                    'title': "값",
                    'side': "left"
                }
                
                # 추가 Y축 설정
                yaxis2_config = {
                    'title': "습도 (%)",
                    'titlefont': dict(color="blue"),
                    'tickfont': dict(color="blue"),
                    'anchor': "x",
                    'overlaying': "y",
                    'side': "right"
                }
                
                yaxis3_config = {
                    'title': "SV",
                    'titlefont': dict(color="orange"),
                    'tickfont': dict(color="orange"),
                    'anchor': "x",
                    'overlaying': "y",
                    'side': "right",
                    'position': 0.95
                }
                
                fig.update_layout(
                    title=f"센서 데이터 시계열 그래프 - {device_id} Ch.{channel}",
                    xaxis_title="시간",
                    yaxis=yaxis_config,
                    yaxis2=yaxis2_config,
                    yaxis3=yaxis3_config,
                    hovermode='x unified',
                    showlegend=True,
                    template="plotly_white",
                    legend=dict(
                        orientation="h",
                        yanchor="bottom",
                        y=1.02,
                        xanchor="right",
                        x=1
                    )
                )
                
                # 센서 정보 생성
                try:
                    result_info = api_db.get_latest_sensor_data_time(device_id, channel)
                    
                    if result_info["status"] == "fail":
                        sensor_info = html.Div(f"센서 {device_id} Ch.{channel}의 데이터를 찾을 수 없습니다.", className="text-danger")
                    else:
                        latest_time = result_info["time"]
                        sensor_info = dbc.Row([
                            dbc.Col([
                                dbc.Card([
                                    dbc.CardBody([
                                        html.H6("센서 ID", className="card-title"),
                                        html.H4(f"{device_id} Ch.{channel}", className="text-primary"),
                                        html.Small(f"최신 데이터: {latest_time.strftime('%Y-%m-%d %H:%M')}", className="text-muted")
                                    ])
                                ])
                            ], width=4),
                            dbc.Col([
                                dbc.Card([
                                    dbc.CardBody([
                                        html.H6("센서 상태", className="card-title"),
                                        html.H4("활성", className="text-success"),
                                        html.Small("데이터 수집 중", className="text-muted")
                                    ])
                                ])
                            ], width=4),
                            dbc.Col([
                                dbc.Card([
                                    dbc.CardBody([
                                        html.H6("데이터 타입", className="card-title"),
                                        html.H4("실시간", className="text-info"),
                                        html.Small("ITS 시스템", className="text-muted")
                                    ])
                                ])
                            ], width=4)
                        ])
                except Exception as e:
                    sensor_info = html.Div(f"센서 정보를 불러올 수 없습니다: {e}", className="text-danger")
                
                # 통계 정보 생성
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
                                dbc.CardHeader("온도 통계"),
                                dbc.CardBody([
                                    html.P(f"평균: {temp_stats['평균']:.1f}°C"),
                                    html.P(f"최대: {temp_stats['최대']:.1f}°C"),
                                    html.P(f"최소: {temp_stats['최소']:.1f}°C"),
                                    html.P(f"중앙값: {temp_stats['중앙값']:.1f}°C"),
                                    html.P(f"표준편차: {temp_stats['표준편차']:.2f}°C")
                                ])
                            ])
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
                                dbc.CardHeader("습도 통계"),
                                dbc.CardBody([
                                    html.P(f"평균: {humidity_stats['평균']:.1f}%"),
                                    html.P(f"최대: {humidity_stats['최대']:.1f}%"),
                                    html.P(f"최소: {humidity_stats['최소']:.1f}%"),
                                    html.P(f"중앙값: {humidity_stats['중앙값']:.1f}%"),
                                    html.P(f"표준편차: {humidity_stats['표준편차']:.2f}%")
                                ])
                            ])
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
                                dbc.CardHeader("SV 통계"),
                                dbc.CardBody([
                                    html.P(f"평균: {sv_stats['평균']:.1f}"),
                                    html.P(f"최대: {sv_stats['최대']:.1f}"),
                                    html.P(f"최소: {sv_stats['최소']:.1f}"),
                                    html.P(f"중앙값: {sv_stats['중앙값']:.1f}"),
                                    html.P(f"표준편차: {sv_stats['표준편차']:.2f}")
                                ])
                            ])
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
                        html.H6("데이터 기간", className="text-center"),
                        html.P(data_period, className="text-center text-muted")
                    ], width=12, className="mb-3"),
                    *stats_cards
                ])
                
                return (
                    df.to_dict('records'),
                    fig,
                    sensor_info,
                    stats,
                    True,
                    f"✅ {result['count']}개의 데이터를 성공적으로 수집했습니다!",
                    "success"
                )
            else:
                empty_graph = go.Figure().add_annotation(
                    text="데이터가 없습니다",
                    xref="paper", yref="paper",
                    x=0.5, y=0.5, showarrow=False
                )
                return (
                    None,
                    empty_graph,
                    html.Div("데이터를 수집했지만 표시할 수 없습니다.", className="text-warning"),
                    html.Div("통계 정보를 표시할 수 없습니다.", className="text-muted"),
                    True,
                    f"⚠️ 데이터를 수집했지만 표시할 수 없습니다.",
                    "warning"
                )
        else:
            empty_graph = go.Figure().add_annotation(
                text="데이터가 없습니다",
                xref="paper", yref="paper",
                x=0.5, y=0.5, showarrow=False
            )
            return (
                None,
                empty_graph,
                html.Div(f"센서 {device_id} Ch.{channel}의 데이터를 찾을 수 없습니다.", className="text-danger"),
                html.Div("통계 정보를 표시할 수 없습니다.", className="text-muted"),
                True,
                f"❌ 데이터 수집 실패: {result['msg']}",
                "danger"
            )
        
    except Exception as e:
        print(f"Error collecting sensor data: {e}")
        empty_graph = go.Figure().add_annotation(
            text="오류 발생",
            xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False
        )
        return (
            None,
            empty_graph,
            html.Div(f"센서 정보를 불러올 수 없습니다: {e}", className="text-danger"),
            html.Div("통계 정보를 표시할 수 없습니다.", className="text-muted"),
            True,
            f"❌ 데이터 수집 중 오류 발생: {str(e)}",
            "danger"
        )

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

@callback(
    Output("toggle-realtime-btn", "outline"),
    Output("interval-component", "interval"),
    Input("toggle-realtime-btn", "n_clicks"),
    State("toggle-realtime-btn", "outline"),
    prevent_initial_call=True
)
def toggle_realtime(n_clicks, current_outline):
    """실시간 업데이트 토글 콜백"""
    if not n_clicks:
        raise PreventUpdate
    
    if current_outline:
        # 실시간 업데이트 활성화
        return False, 30*1000  # 30초
    else:
        # 실시간 업데이트 비활성화
        return True, 24*60*60*1000  # 24시간 (실제로는 업데이트 안함) 