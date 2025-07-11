#!/usr/bin/env python3
# pages/sensor_data_view.py
"""Dash 페이지: 센서 데이터 확인

* 왼쪽에서 센서 리스트 선택 → 해당 센서의 데이터 그래프 표시
* 온도, 습도, SV 데이터를 시간별로 그래프로 표시
* 데이터 다운로드 기능
* 실시간 데이터 업데이트 기능
* 센서별 데이터 통계 정보 표시
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
    """사용 가능한 센서 목록을 반환하는 함수"""
    sensors_dir = "sensors"
    if not os.path.exists(sensors_dir):
        return []
    
    sensor_files = [f for f in os.listdir(sensors_dir) if f.endswith('.csv')]
    sensor_ids = [f.replace('.csv', '') for f in sensor_files]
    return sorted(sensor_ids)

def get_sensor_info(sensor_id: str) -> dict:
    """센서 정보를 반환하는 함수"""
    df = load_sensor_data(sensor_id)
    if df.empty:
        return {
            'sensor_id': sensor_id,
            'data_count': 0,
            'latest_time': None,
            'latest_temp': None,
            'latest_humidity': None,
            'latest_sv': None,
            'temp_range': (None, None),
            'humidity_range': (None, None),
            'sv_range': (None, None)
        }
    
    latest_data = df.iloc[-1]
    
    return {
        'sensor_id': sensor_id,
        'data_count': len(df),
        'latest_time': latest_data['time'],
        'latest_temp': latest_data['temperature'],
        'latest_humidity': latest_data['humidity'],
        'latest_sv': latest_data['sv'],
        'temp_range': (df['temperature'].min(), df['temperature'].max()),
        'humidity_range': (df['humidity'].min(), df['humidity'].max()),
        'sv_range': (df['sv'].min(), df['sv'].max())
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
                        html.H5("센서 목록", className="mb-0"),
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
                "사용 가능한 센서가 없습니다.",
                color="warning"
            )
        ]
    
    sensor_items = []
    for sensor_id in sensors:
        # 센서 정보 가져오기
        sensor_info = get_sensor_info(sensor_id)
        
        # 상태 배지 색상 결정
        if sensor_info['data_count'] == 0:
            status_color = "secondary"
            status_text = "데이터 없음"
        else:
            # 최신 데이터가 2시간 이내인지 확인
            if sensor_info['latest_time']:
                time_diff = (datetime.now() - sensor_info['latest_time']).total_seconds() / 3600
                if time_diff <= 2:
                    status_color = "success"
                    status_text = "활성"
                else:
                    status_color = "warning"
                    status_text = "비활성"
            else:
                status_color = "secondary"
                status_text = "알 수 없음"
        
        sensor_items.append(
            dbc.ListGroupItem([
                dbc.Row([
                    dbc.Col([
                        html.Div([
                            html.I(className="fas fa-thermometer-half me-2"),
                            html.Strong(sensor_id)
                        ]),
                        html.Small(f"데이터: {sensor_info['data_count']}개", className="text-muted")
                    ], width=8),
                    dbc.Col([
                        dbc.Badge(status_text, color=status_color, className="badge-sm")
                    ], width=4, className="text-end")
                ]),
                html.Div([
                    html.Small(f"최신: {sensor_info['latest_temp']:.1f}°C", className="text-success me-2"),
                    html.Small(f"{sensor_info['latest_humidity']:.1f}%", className="text-info me-2"),
                    html.Small(f"SV: {sensor_info['latest_sv']:.1f}", className="text-warning")
                ], className="mt-1") if sensor_info['data_count'] > 0 else None
            ],
            id={"type": "sensor-item", "index": sensor_id},
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
        sensor_id = trigger_data['index']
        return sensor_id
    except:
        raise PreventUpdate

@callback(
    Output("sensor-data-store", "data"),
    Input("selected-sensor-store", "data"),
    Input("interval-component", "n_intervals"),
    prevent_initial_call=True
)
def load_selected_sensor_data(sensor_id, n_intervals):
    """선택된 센서의 데이터를 로드하는 콜백"""
    if not sensor_id:
        raise PreventUpdate
    
    df = load_sensor_data(sensor_id)
    if df.empty:
        return None
    
    return df.to_dict('records')

@callback(
    Output("selected-sensor-info", "children"),
    Input("selected-sensor-store", "data"),
    prevent_initial_call=True
)
def update_sensor_info(sensor_id):
    """선택된 센서 정보를 표시하는 콜백"""
    if not sensor_id:
        return html.Div("센서를 선택하세요.", className="text-muted")
    
    sensor_info = get_sensor_info(sensor_id)
    if sensor_info['data_count'] == 0:
        return html.Div(f"센서 {sensor_id}의 데이터를 찾을 수 없습니다.", className="text-danger")
    
    return dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardBody([
                    html.H6("센서 ID", className="card-title"),
                    html.H4(sensor_id, className="text-primary"),
                    html.Small(f"총 {sensor_info['data_count']}개 데이터", className="text-muted")
                ])
            ])
        ], width=3),
        dbc.Col([
            dbc.Card([
                dbc.CardBody([
                    html.H6("현재 온도", className="card-title"),
                    html.H4(f"{sensor_info['latest_temp']:.1f}°C", className="text-success"),
                    html.Small(f"범위: {sensor_info['temp_range'][0]:.1f}~{sensor_info['temp_range'][1]:.1f}°C", className="text-muted")
                ])
            ])
        ], width=3),
        dbc.Col([
            dbc.Card([
                dbc.CardBody([
                    html.H6("현재 습도", className="card-title"),
                    html.H4(f"{sensor_info['latest_humidity']:.1f}%", className="text-info"),
                    html.Small(f"범위: {sensor_info['humidity_range'][0]:.1f}~{sensor_info['humidity_range'][1]:.1f}%", className="text-muted")
                ])
            ])
        ], width=3),
        dbc.Col([
            dbc.Card([
                dbc.CardBody([
                    html.H6("현재 SV", className="card-title"),
                    html.H4(f"{sensor_info['latest_sv']:.1f}", className="text-warning"),
                    html.Small(f"범위: {sensor_info['sv_range'][0]:.1f}~{sensor_info['sv_range'][1]:.1f}", className="text-muted")
                ])
            ])
        ], width=3)
    ])

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
    df['time'] = pd.to_datetime(df['time'])
    
    # 서브플롯 생성
    fig = go.Figure()
    
    # 온도 그래프
    fig.add_trace(go.Scatter(
        x=df['time'],
        y=df['temperature'],
        mode='lines+markers',
        name='온도 (°C)',
        line=dict(color='red', width=2),
        marker=dict(size=4),
        yaxis='y'
    ))
    
    # 습도 그래프 (보조 Y축)
    fig.add_trace(go.Scatter(
        x=df['time'],
        y=df['humidity'],
        mode='lines+markers',
        name='습도 (%)',
        line=dict(color='blue', width=2),
        marker=dict(size=4),
        yaxis='y2'
    ))
    
    # SV 그래프 (보조 Y축)
    fig.add_trace(go.Scatter(
        x=df['time'],
        y=df['sv'],
        mode='lines+markers',
        name='SV',
        line=dict(color='orange', width=2),
        marker=dict(size=4),
        yaxis='y3'
    ))
    
    fig.update_layout(
        title="센서 데이터 시계열 그래프",
        xaxis_title="시간",
        yaxis=dict(
            title="온도 (°C)",
            titlefont=dict(color="red"),
            tickfont=dict(color="red"),
            side="left"
        ),
        yaxis2=dict(
            title="습도 (%)",
            titlefont=dict(color="blue"),
            tickfont=dict(color="blue"),
            anchor="x",
            overlaying="y",
            side="right"
        ),
        yaxis3=dict(
            title="SV",
            titlefont=dict(color="orange"),
            tickfont=dict(color="orange"),
            anchor="x",
            overlaying="y",
            side="right",
            position=0.95
        ),
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
    df['time'] = pd.to_datetime(df['time'])
    
    # 통계 계산
    temp_stats = {
        '평균': df['temperature'].mean(),
        '최대': df['temperature'].max(),
        '최소': df['temperature'].min(),
        '표준편차': df['temperature'].std(),
        '중앙값': df['temperature'].median()
    }
    
    humidity_stats = {
        '평균': df['humidity'].mean(),
        '최대': df['humidity'].max(),
        '최소': df['humidity'].min(),
        '표준편차': df['humidity'].std(),
        '중앙값': df['humidity'].median()
    }
    
    sv_stats = {
        '평균': df['sv'].mean(),
        '최대': df['sv'].max(),
        '최소': df['sv'].min(),
        '표준편차': df['sv'].std(),
        '중앙값': df['sv'].median()
    }
    
    # 데이터 기간 정보
    data_period = f"{df['time'].min().strftime('%Y-%m-%d %H:%M')} ~ {df['time'].max().strftime('%Y-%m-%d %H:%M')}"
    
    return dbc.Row([
        dbc.Col([
            html.H6("데이터 기간", className="text-center"),
            html.P(data_period, className="text-center text-muted")
        ], width=12, className="mb-3"),
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
        ], width=4),
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
        ], width=4),
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
    ])

@callback(
    Output("download-csv", "data"),
    Input("download-csv-btn", "n_clicks"),
    State("selected-sensor-store", "data"),
    prevent_initial_call=True
)
def download_csv(n_clicks, sensor_id):
    """CSV 다운로드 콜백"""
    if not sensor_id or not n_clicks:
        raise PreventUpdate
    
    df = load_sensor_data(sensor_id)
    if df.empty:
        raise PreventUpdate
    
    # CSV 데이터 생성
    csv_string = df.to_csv(index=False, encoding='utf-8-sig')
    
    return dict(
        content=csv_string,
        filename=f"{sensor_id}_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    )

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