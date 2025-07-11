#!/usr/bin/env python3
# pages/sensor_data_view.py
"""Dash 페이지: 센서 데이터 확인

* 왼쪽에서 센서 리스트 선택 → 해당 센서의 데이터 그래프 표시
* 온도 데이터를 시간별로 그래프로 표시
* 데이터 다운로드 기능
* 실시간 데이터 업데이트 기능
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
            ], width=3),
            
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
            ], width=9)
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
        sensor_items.append(
            dbc.ListGroupItem(
                [
                    html.I(className="fas fa-thermometer-half me-2"),
                    sensor_id
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
    import json
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
    
    df = load_sensor_data(sensor_id)
    if df.empty:
        return html.Div(f"센서 {sensor_id}의 데이터를 찾을 수 없습니다.", className="text-danger")
    
    # 최신 데이터 정보
    latest_data = df.iloc[-1]
    
    return dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardBody([
                    html.H6("센서 ID", className="card-title"),
                    html.H4(sensor_id, className="text-primary")
                ])
            ])
        ], width=3),
        dbc.Col([
            dbc.Card([
                dbc.CardBody([
                    html.H6("현재 온도", className="card-title"),
                    html.H4(f"{latest_data['temperature']:.1f}°C", className="text-success")
                ])
            ])
        ], width=3),
        dbc.Col([
            dbc.Card([
                dbc.CardBody([
                    html.H6("현재 습도", className="card-title"),
                    html.H4(f"{latest_data['humidity']:.1f}%", className="text-info")
                ])
            ])
        ], width=3),
        dbc.Col([
            dbc.Card([
                dbc.CardBody([
                    html.H6("현재 SV", className="card-title"),
                    html.H4(f"{latest_data['sv']:.1f}", className="text-warning")
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
    
    # 온도 그래프
    fig = go.Figure()
    
    fig.add_trace(go.Scatter(
        x=df['time'],
        y=df['temperature'],
        mode='lines+markers',
        name='온도',
        line=dict(color='red', width=2),
        marker=dict(size=4)
    ))
    
    fig.update_layout(
        title="센서 온도 데이터",
        xaxis_title="시간",
        yaxis_title="온도 (°C)",
        hovermode='x unified',
        showlegend=True,
        template="plotly_white"
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
        '표준편차': df['temperature'].std()
    }
    
    humidity_stats = {
        '평균': df['humidity'].mean(),
        '최대': df['humidity'].max(),
        '최소': df['humidity'].min(),
        '표준편차': df['humidity'].std()
    }
    
    return dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardHeader("온도 통계"),
                dbc.CardBody([
                    html.P(f"평균: {temp_stats['평균']:.1f}°C"),
                    html.P(f"최대: {temp_stats['최대']:.1f}°C"),
                    html.P(f"최소: {temp_stats['최소']:.1f}°C"),
                    html.P(f"표준편차: {temp_stats['표준편차']:.2f}°C")
                ])
            ])
        ], width=6),
        dbc.Col([
            dbc.Card([
                dbc.CardHeader("습도 통계"),
                dbc.CardBody([
                    html.P(f"평균: {humidity_stats['평균']:.1f}%"),
                    html.P(f"최대: {humidity_stats['최대']:.1f}%"),
                    html.P(f"최소: {humidity_stats['최소']:.1f}%"),
                    html.P(f"표준편차: {humidity_stats['표준편차']:.2f}%")
                ])
            ])
        ], width=6)
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