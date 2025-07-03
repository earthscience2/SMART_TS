"""
온도 변화 탭 모듈

시간에 따른 온도 변화 그래프와 관련된 레이아웃과 콜백을 포함합니다.
"""

import dash
from dash import html, dcc, Input, Output, State, callback
import dash_bootstrap_components as dbc
from dash.exceptions import PreventUpdate
import plotly.graph_objects as go
import numpy as np
import pandas as pd

def create_temp_tab():
    """온도 변화 탭의 레이아웃을 생성합니다."""
    return dbc.Container([
        # ────────────────────────────── 입력 컨트롤 ────────────────────────────
        dbc.Row([
            dbc.Col([
                html.H5("🎛️ 온도 변화 컨트롤", className="mb-3"),
                dbc.Row([
                    dbc.Col([
                        html.Label("센서 선택:", className="form-label"),
                        dcc.Dropdown(
                            id="dropdown-sensor-temp",
                            placeholder="센서를 선택하세요",
                            multi=True,
                            style={"marginBottom": "10px"}
                        )
                    ], md=6),
                    dbc.Col([
                        html.Label("시간 범위:", className="form-label"),
                        dcc.RangeSlider(
                            id="range-time-temp",
                            min=0,
                            max=168,
                            step=1,
                            value=[0, 168],
                            marks={},
                            tooltip={"placement": "bottom", "always_visible": True}
                        )
                    ], md=6)
                ])
            ], md=12)
        ], className="mb-4"),
        
        # ────────────────────────────── 온도 변화 그래프 ────────────────────────────
        dbc.Row([
            dbc.Col([
                html.H5("🌡️ 온도 변화 그래프", className="mb-3"),
                dcc.Graph(
                    id="graph-temp-change",
                    style={"height": "500px"},
                    config={
                        'displayModeBar': True,
                        'displaylogo': False,
                        'modeBarButtonsToRemove': ['pan2d', 'lasso2d', 'select2d'],
                        'toImageButtonOptions': {
                            'format': 'png',
                            'filename': 'temperature_change',
                            'height': 500,
                            'width': 1000,
                            'scale': 2
                        }
                    }
                )
            ], md=12)
        ]),
        
        # ────────────────────────────── 통계 정보 ────────────────────────────
        dbc.Row([
            dbc.Col([
                html.H5("📊 온도 통계", className="mb-3"),
                dbc.Card([
                    dbc.CardBody([
                        html.Div(id="stats-temp", className="text-muted")
                    ])
                ])
            ], md=12)
        ], className="mt-4")
    ], fluid=True)

def register_temp_callbacks():
    """온도 변화 탭의 콜백들을 등록합니다."""
    
    @callback(
        Output("dropdown-sensor-temp", "options"),
        Input("dropdown-concrete", "value"),
        prevent_initial_call=True
    )
    def update_sensor_dropdown(concrete_id):
        """센서 드롭다운을 업데이트합니다."""
        if not concrete_id:
            return []
        
        try:
            # 콘크리트의 센서 목록 가져오기
            sensors = get_sensors_by_concrete(concrete_id)
            options = [{"label": f"센서 {s['id']}", "value": s['id']} for s in sensors]
            return options
        except:
            return []
    
    @callback(
        Output("graph-temp-change", "figure"),
        Output("stats-temp", "children"),
        Input("dropdown-concrete", "value"),
        Input("dropdown-sensor-temp", "value"),
        Input("range-time-temp", "value"),
        prevent_initial_call=True
    )
    def update_temp_graph(concrete_id, selected_sensors, time_range):
        """온도 변화 그래프를 업데이트합니다."""
        if not concrete_id:
            return create_empty_temp_graph(), "콘크리트를 선택해주세요"
        
        try:
            # 온도 데이터 로드
            temp_data = load_temperature_data(concrete_id, selected_sensors, time_range)
            if not temp_data:
                return create_empty_temp_graph(), "데이터를 불러올 수 없습니다"
            
            # 그래프 생성
            fig = create_temperature_graph(temp_data)
            
            # 통계 계산
            stats = calculate_temperature_stats(temp_data)
            
            return fig, stats
            
        except Exception as e:
            return create_error_temp_graph(str(e)), f"오류 발생: {str(e)}"

def create_empty_temp_graph():
    """빈 온도 그래프를 생성합니다."""
    fig = go.Figure()
    fig.update_layout(
        title="콘크리트를 선택해주세요",
        xaxis=dict(title="시간 (시간)"),
        yaxis=dict(title="온도 (°C)"),
        height=500
    )
    return fig

def create_error_temp_graph(error_msg):
    """오류 온도 그래프를 생성합니다."""
    fig = go.Figure()
    fig.update_layout(
        title=f"오류: {error_msg}",
        xaxis=dict(title="시간 (시간)"),
        yaxis=dict(title="온도 (°C)"),
        height=500
    )
    return fig

def create_temperature_graph(data):
    """온도 변화 그래프를 생성합니다."""
    fig = go.Figure()
    
    # 각 센서별 온도 곡선 추가
    for sensor_id, sensor_data in data.items():
        fig.add_trace(go.Scatter(
            x=sensor_data['time'],
            y=sensor_data['temperature'],
            mode='lines',
            name=f'센서 {sensor_id}',
            line=dict(width=2)
        ))
    
    fig.update_layout(
        title="시간에 따른 온도 변화",
        xaxis=dict(title="시간 (시간)"),
        yaxis=dict(title="온도 (°C)"),
        height=500,
        showlegend=True
    )
    
    return fig

def load_temperature_data(concrete_id, sensor_ids, time_range):
    """온도 데이터를 로드합니다."""
    # 실제 구현에서는 데이터베이스에서 데이터 로드
    # 여기서는 예시 데이터로 대체
    
    if not sensor_ids:
        return {}
    
    data = {}
    time_points = np.linspace(time_range[0], time_range[1], 100)
    
    for sensor_id in sensor_ids:
        # 예시 온도 곡선 (가우시안 + 사인파)
        base_temp = 20
        peak_temp = 60
        peak_time = 48  # 48시간에 최고 온도
        
        temperature = base_temp + peak_temp * np.exp(-((time_points - peak_time) ** 2) / (2 * 24 ** 2))
        temperature += 5 * np.sin(2 * np.pi * time_points / 24)  # 일일 변동
        
        data[sensor_id] = {
            'time': time_points,
            'temperature': temperature
        }
    
    return data

def calculate_temperature_stats(data):
    """온도 통계를 계산합니다."""
    if not data:
        return "데이터가 없습니다"
    
    all_temps = []
    for sensor_data in data.values():
        all_temps.extend(sensor_data['temperature'])
    
    if not all_temps:
        return "온도 데이터가 없습니다"
    
    stats = {
        'min': min(all_temps),
        'max': max(all_temps),
        'mean': np.mean(all_temps),
        'std': np.std(all_temps)
    }
    
    return f"""
    최저 온도: {stats['min']:.1f}°C<br>
    최고 온도: {stats['max']:.1f}°C<br>
    평균 온도: {stats['mean']:.1f}°C<br>
    표준편차: {stats['std']:.1f}°C
    """

def get_sensors_by_concrete(concrete_id):
    """콘크리트의 센서 목록을 가져옵니다."""
    # 실제 구현에서는 데이터베이스에서 가져오기
    return [{'id': i} for i in range(1, 11)]  # 예시: 10개 센서 