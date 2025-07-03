"""
수치해석 탭 모듈

수치해석 결과와 관련된 레이아웃과 콜백을 포함합니다.
"""

import dash
from dash import html, dcc, Input, Output, State, callback
import dash_bootstrap_components as dbc
from dash.exceptions import PreventUpdate
import plotly.graph_objects as go
import numpy as np
import pandas as pd

def create_analysis_tab():
    """수치해석 탭의 레이아웃을 생성합니다."""
    return dbc.Container([
        # ────────────────────────────── 입력 컨트롤 ────────────────────────────
        dbc.Row([
            dbc.Col([
                html.H5("🎛️ 수치해석 컨트롤", className="mb-3"),
                dbc.Row([
                    dbc.Col([
                        html.Label("해석 필드:", className="form-label"),
                        dcc.Dropdown(
                            id="dropdown-field-analysis",
                            options=[
                                {"label": "온도", "value": "temperature"},
                                {"label": "응력", "value": "stress"},
                                {"label": "변형", "value": "strain"}
                            ],
                            value="temperature",
                            style={"marginBottom": "10px"}
                        )
                    ], md=4),
                    dbc.Col([
                        html.Label("시간:", className="form-label"),
                        dcc.Slider(
                            id="slider-time-analysis",
                            min=0,
                            max=168,
                            step=1,
                            value=0,
                            marks={},
                            tooltip={"placement": "bottom", "always_visible": True}
                        )
                    ], md=4),
                    dbc.Col([
                        html.Label("색상 범위:", className="form-label"),
                        dcc.RangeSlider(
                            id="range-color-analysis",
                            min=0,
                            max=100,
                            step=1,
                            value=[0, 100],
                            marks={},
                            tooltip={"placement": "bottom", "always_visible": True}
                        )
                    ], md=4)
                ])
            ], md=12)
        ], className="mb-4"),
        
        # ────────────────────────────── 수치해석 결과 ────────────────────────────
        dbc.Row([
            dbc.Col([
                html.H5("🔬 수치해석 결과", className="mb-3"),
                dcc.Graph(
                    id="graph-analysis-result",
                    style={"height": "600px"},
                    config={
                        'displayModeBar': True,
                        'displaylogo': False,
                        'modeBarButtonsToRemove': ['pan2d', 'lasso2d', 'select2d'],
                        'toImageButtonOptions': {
                            'format': 'png',
                            'filename': 'analysis_result',
                            'height': 600,
                            'width': 1000,
                            'scale': 2
                        }
                    }
                )
            ], md=12)
        ]),
        
        # ────────────────────────────── 결과 정보 ────────────────────────────
        dbc.Row([
            dbc.Col([
                html.H5("📊 해석 정보", className="mb-3"),
                dbc.Card([
                    dbc.CardBody([
                        html.Div(id="info-analysis", className="text-muted")
                    ])
                ])
            ], md=12)
        ], className="mt-4")
    ], fluid=True)

def register_analysis_callbacks():
    """수치해석 탭의 콜백들을 등록합니다."""
    
    @callback(
        Output("graph-analysis-result", "figure"),
        Output("info-analysis", "children"),
        Input("dropdown-concrete", "value"),
        Input("dropdown-field-analysis", "value"),
        Input("slider-time-analysis", "value"),
        Input("range-color-analysis", "value"),
        prevent_initial_call=True
    )
    def update_analysis_result(concrete_id, field, time_value, color_range):
        """수치해석 결과를 업데이트합니다."""
        if not concrete_id:
            return create_empty_analysis_graph(), "콘크리트를 선택해주세요"
        
        try:
            # 수치해석 데이터 로드
            analysis_data = load_analysis_data(concrete_id, field, time_value)
            if not analysis_data:
                return create_empty_analysis_graph(), "데이터를 불러올 수 없습니다"
            
            # 결과 그래프 생성
            fig = create_analysis_graph(analysis_data, field, time_value, color_range)
            
            # 정보 업데이트
            info_text = f"필드: {field}, 시간: {time_value}시간, 범위: {color_range[0]} ~ {color_range[1]}"
            
            return fig, info_text
            
        except Exception as e:
            return create_error_analysis_graph(str(e)), f"오류 발생: {str(e)}"
    
    @callback(
        Output("slider-time-analysis", "max"),
        Output("slider-time-analysis", "marks"),
        Input("dropdown-concrete", "value"),
        prevent_initial_call=True
    )
    def update_time_slider_analysis(concrete_id):
        """시간 슬라이더를 업데이트합니다."""
        if not concrete_id:
            return 168, {}
        
        try:
            # 콘크리트의 최대 시간 계산
            max_time = get_max_time(concrete_id)
            marks = {i: f"{i}h" for i in range(0, max_time + 1, 24)}
            return max_time, marks
        except:
            return 168, {}

def create_empty_analysis_graph():
    """빈 수치해석 그래프를 생성합니다."""
    fig = go.Figure()
    fig.update_layout(
        title="콘크리트를 선택해주세요",
        xaxis=dict(title="X (m)"),
        yaxis=dict(title="Y (m)"),
        height=600
    )
    return fig

def create_error_analysis_graph(error_msg):
    """오류 수치해석 그래프를 생성합니다."""
    fig = go.Figure()
    fig.update_layout(
        title=f"오류: {error_msg}",
        xaxis=dict(title="X (m)"),
        yaxis=dict(title="Y (m)"),
        height=600
    )
    return fig

def create_analysis_graph(data, field, time_value, color_range):
    """수치해석 결과 그래프를 생성합니다."""
    # 실제 구현에서는 수치해석 데이터를 기반으로 그래프 생성
    # 여기서는 예시 데이터로 대체
    
    # 예시: 2D 히트맵
    x = np.linspace(0, 10, 50)
    y = np.linspace(0, 10, 50)
    X, Y = np.meshgrid(x, y)
    
    # 필드별 다른 분포 생성
    if field == "temperature":
        Z = 20 + 40 * np.exp(-((X-5)**2 + (Y-5)**2) / 10)
    elif field == "stress":
        Z = 10 + 20 * np.sin(np.pi * X / 10) * np.cos(np.pi * Y / 10)
    else:  # strain
        Z = 0.001 + 0.002 * np.exp(-((X-3)**2 + (Y-7)**2) / 5)
    
    fig = go.Figure(data=go.Heatmap(
        z=Z,
        x=x,
        y=y,
        colorscale='Viridis',
        zmin=color_range[0],
        zmax=color_range[1],
        colorbar=dict(title=f"{field} ({get_unit(field)})")
    ))
    
    fig.update_layout(
        title=f"{field} 분포 (시간: {time_value}시간)",
        xaxis=dict(title="X (m)"),
        yaxis=dict(title="Y (m)"),
        height=600
    )
    
    return fig

def load_analysis_data(concrete_id, field, time_value):
    """수치해석 데이터를 로드합니다."""
    # 실제 구현에서는 데이터베이스에서 데이터 로드
    return {
        "concrete_id": concrete_id,
        "field": field,
        "time": time_value,
        "data": "example_analysis_data"
    }

def get_unit(field):
    """필드별 단위를 반환합니다."""
    units = {
        "temperature": "°C",
        "stress": "MPa",
        "strain": "mm/mm"
    }
    return units.get(field, "")

def get_max_time(concrete_id):
    """콘크리트의 최대 시간을 반환합니다."""
    # 실제 구현에서는 데이터베이스에서 계산
    return 168  # 7일 