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
    Input("refresh-sensors-btn", "n_clicks"),
    Input("interval-component", "n_intervals"),
    prevent_initial_call=False
)
def update_sensor_list(refresh_clicks, n_intervals):
    """센서 목록을 업데이트하는 콜백"""
    sensors = get_available_sensors()
    
    if not sensors:
        return [
            dbc.ListGroupItem(
                "접근 가능한 센서가 없습니다.",
                color="warning"
            )
        ]
    
    sensor_items = []
    for sensor_data in sensors:
        # 센서 정보 가져오기
        sensor_info = get_sensor_info(sensor_data)
        
        sensor_items.append(
            dbc.ListGroupItem([
                dbc.Row([
                    dbc.Col([
                        html.Div([
                            html.I(className="fas fa-thermometer-half me-2"),
                            html.Strong(f"{sensor_info['device_id']} Ch.{sensor_info['channel']}")
                        ]),
                        html.Small(f"구조: {sensor_info['structure_id']}", className="text-muted")
                    ], width=8),
                    dbc.Col([
                        dbc.Badge(sensor_info['status'], color=sensor_info['status_color'], className="badge-sm")
                    ], width=4, className="text-end")
                ]),
                html.Div([
                    html.Small(f"타입: {sensor_data.get('device_type', 'N/A')}", className="text-muted me-2"),
                    html.Small(f"데이터: {sensor_data.get('data_type', 'N/A')}", className="text-muted me-2"),
                    html.Small(f"3축: {sensor_data.get('is3axis', 'N')}", className="text-muted")
                ], className="mt-1")
            ],
            id={"type": "sensor-item", "index": sensor_info['sensor_key']},
            action=True,
            className="sensor-list-item"
            )
        )
    
    return sensor_items

@callback(
    Output("selected-sensor-store", "data"),
    Input({"type": "sensor-item", "index": ALL}, "n_clicks"),
    prevent_initial_call=True
)
def select_sensor(clicks):
    """센서 선택 콜백"""
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
        return sensor_key
    except:
        raise PreventUpdate

@callback(
    Output("sensor-data-store", "data"),
    Input("selected-sensor-store", "data"),
    Input("interval-component", "n_intervals"),
    prevent_initial_call=True
)
def load_selected_sensor_data(sensor_key, n_intervals):
    """선택된 센서의 데이터를 로드하는 콜백"""
    if not sensor_key:
        raise PreventUpdate
    
    # sensor_key에서 device_id와 channel 추출
    try:
        device_id, channel_part = sensor_key.split('_Ch')
        channel = channel_part
        
        # 실제 센서 데이터 조회 (여기서는 예시 데이터 반환)
        # 실제로는 api_db.get_sensor_data() 함수를 사용해야 함
        df = api_db.get_sensor_data(device_id=device_id, channel=channel)
        
        if df.empty:
            return None
        
        return df.to_dict('records')
    except Exception as e:
        print(f"Error loading sensor data: {e}")
        return None

@callback(
    Output("selected-sensor-info", "children"),
    Input("selected-sensor-store", "data"),
    prevent_initial_call=True
)
def update_sensor_info(sensor_key):
    """선택된 센서 정보를 표시하는 콜백"""
    if not sensor_key:
        return html.Div("센서를 선택하세요.", className="text-muted")
    
    try:
        device_id, channel_part = sensor_key.split('_Ch')
        channel = channel_part
        
        # 센서 상태 확인
        result = api_db.get_latest_sensor_data_time(device_id, channel)
        
        if result["status"] == "fail":
            return html.Div(f"센서 {device_id} Ch.{channel}의 데이터를 찾을 수 없습니다.", className="text-danger")
        
        latest_time = result["time"]
        
        return dbc.Row([
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
        return html.Div(f"센서 정보를 불러올 수 없습니다: {e}", className="text-danger")

@callback(
    Output("sensor-data-graph", "figure"),
    Input("sensor-data-store", "data"),
    prevent_initial_call=True
)
def update_sensor_graph(data):
    """센서 데이터 그래프를 업데이트하는 콜백"""
    if not data:
        return go.Figure().add_annotation(
            text="데이터가 없습니다",
            xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False
        )
    
    df = pd.DataFrame(data)
    
    # 시간 컬럼이 있는지 확인
    if 'time' not in df.columns and 'timestamp' in df.columns:
        df['time'] = pd.to_datetime(df['timestamp'])
    elif 'time' not in df.columns:
        # 시간 컬럼이 없으면 인덱스 사용
        df['time'] = pd.date_range(start='2025-01-01', periods=len(df), freq='H')
    else:
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
        title="센서 데이터 시계열 그래프",
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
    
    return fig

@callback(
    Output("sensor-stats", "children"),
    Input("sensor-data-store", "data"),
    prevent_initial_call=True
)
def update_sensor_stats(data):
    """센서 데이터 통계를 업데이트하는 콜백"""
    if not data:
        return html.Div("통계 정보를 표시할 수 없습니다.", className="text-muted")
    
    df = pd.DataFrame(data)
    
    # 시간 컬럼 처리
    if 'time' not in df.columns and 'timestamp' in df.columns:
        df['time'] = pd.to_datetime(df['timestamp'])
    elif 'time' not in df.columns:
        df['time'] = pd.date_range(start='2025-01-01', periods=len(df), freq='H')
    else:
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
    
    return dbc.Row([
        dbc.Col([
            html.H6("데이터 기간", className="text-center"),
            html.P(data_period, className="text-center text-muted")
        ], width=12, className="mb-3"),
        *stats_cards
    ])

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
        df = api_db.get_sensor_data(device_id=device_id, channel=channel)
        
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