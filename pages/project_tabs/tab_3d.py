"""
3D 뷰 탭 모듈

3D 히트맵 뷰어와 관련된 레이아웃과 콜백을 포함합니다.
"""

import dash
from dash import html, dcc, Input, Output, State, callback
import dash_bootstrap_components as dbc
from dash.exceptions import PreventUpdate
import plotly.graph_objects as go
import numpy as np
import pandas as pd
import json
import os
from datetime import datetime, timedelta

def create_3d_tab():
    """3D 뷰 탭의 레이아웃을 생성합니다."""
    return dbc.Container([
        # ────────────────────────────── 입력 컨트롤 ────────────────────────────
        dbc.Row([
            dbc.Col([
                html.H5("🎛️ 3D 뷰 컨트롤", className="mb-3"),
                dbc.Row([
                    dbc.Col([
                        html.Label("시간 선택:", className="form-label"),
                        dcc.Slider(
                            id="slider-time-3d",
                            min=0,
                            max=100,
                            step=1,
                            value=0,
                            marks={},
                            tooltip={"placement": "bottom", "always_visible": True}
                        )
                    ], md=6),
                    dbc.Col([
                        html.Label("색상 범위:", className="form-label"),
                        dcc.RangeSlider(
                            id="range-color-3d",
                            min=0,
                            max=100,
                            step=1,
                            value=[0, 100],
                            marks={},
                            tooltip={"placement": "bottom", "always_visible": True}
                        )
                    ], md=6)
                ], className="mb-3"),
                dbc.Row([
                    dbc.Col([
                        html.Label("뷰 각도:", className="form-label"),
                        dcc.Slider(
                            id="slider-view-3d",
                            min=0,
                            max=360,
                            step=10,
                            value=45,
                            marks={},
                            tooltip={"placement": "bottom", "always_visible": True}
                        )
                    ], md=6),
                    dbc.Col([
                        html.Label("줌 레벨:", className="form-label"),
                        dcc.Slider(
                            id="slider-zoom-3d",
                            min=0.1,
                            max=2.0,
                            step=0.1,
                            value=1.0,
                            marks={},
                            tooltip={"placement": "bottom", "always_visible": True}
                        )
                    ], md=6)
                ])
            ], md=12)
        ], className="mb-4"),
        
        # ────────────────────────────── 3D 뷰어 ────────────────────────────
        dbc.Row([
            dbc.Col([
                html.H5("🎯 3D 히트맵 뷰어", className="mb-3"),
                dcc.Graph(
                    id="graph-3d-view",
                    style={"height": "600px"},
                    config={
                        'displayModeBar': True,
                        'displaylogo': False,
                        'modeBarButtonsToRemove': ['pan2d', 'lasso2d', 'select2d'],
                        'toImageButtonOptions': {
                            'format': 'png',
                            'filename': '3d_view',
                            'height': 600,
                            'width': 800,
                            'scale': 2
                        }
                    }
                )
            ], md=12)
        ]),
        
        # ────────────────────────────── 정보 패널 ────────────────────────────
        dbc.Row([
            dbc.Col([
                html.H5("ℹ️ 뷰 정보", className="mb-3"),
                dbc.Card([
                    dbc.CardBody([
                        html.Div(id="info-3d-view", className="text-muted")
                    ])
                ])
            ], md=12)
        ], className="mt-4")
    ], fluid=True)

def register_3d_callbacks():
    """3D 뷰 탭의 콜백들을 등록합니다."""
    
    @callback(
        Output("graph-3d-view", "figure"),
        Output("info-3d-view", "children"),
        Input("dropdown-concrete", "value"),
        Input("slider-time-3d", "value"),
        Input("range-color-3d", "value"),
        Input("slider-view-3d", "value"),
        Input("slider-zoom-3d", "value"),
        State("store-3d-view", "data"),
        prevent_initial_call=True
    )
    def update_3d_view(concrete_id, time_value, color_range, view_angle, zoom_level, stored_view):
        """3D 뷰를 업데이트합니다."""
        if not concrete_id:
            # 빈 3D 뷰 반환
            fig = go.Figure()
            fig.update_layout(
                title="콘크리트를 선택해주세요",
                scene=dict(
                    xaxis=dict(title="X"),
                    yaxis=dict(title="Y"),
                    zaxis=dict(title="Z")
                ),
                height=600
            )
            return fig, "콘크리트를 선택해주세요"
        
        try:
            # 콘크리트 데이터 로드
            concrete_data = load_concrete_data(concrete_id)
            if not concrete_data:
                return create_empty_3d_view(), "데이터를 불러올 수 없습니다"
            
            # 3D 히트맵 생성
            fig = create_3d_heatmap(concrete_data, time_value, color_range, view_angle, zoom_level)
            
            # 정보 업데이트
            info_text = f"시간: {time_value}시간, 온도 범위: {color_range[0]}°C ~ {color_range[1]}°C"
            
            return fig, info_text
            
        except Exception as e:
            return create_error_3d_view(str(e)), f"오류 발생: {str(e)}"
    
    @callback(
        Output("slider-time-3d", "max"),
        Output("slider-time-3d", "marks"),
        Input("dropdown-concrete", "value"),
        prevent_initial_call=True
    )
    def update_time_slider(concrete_id):
        """시간 슬라이더를 업데이트합니다."""
        if not concrete_id:
            return 100, {}
        
        try:
            # 콘크리트의 최대 시간 계산
            max_time = get_max_time(concrete_id)
            marks = {i: f"{i}h" for i in range(0, max_time + 1, 24)}
            return max_time, marks
        except:
            return 100, {}
    
    @callback(
        Output("range-color-3d", "min"),
        Output("range-color-3d", "max"),
        Output("range-color-3d", "value"),
        Input("dropdown-concrete", "value"),
        prevent_initial_call=True
    )
    def update_color_range(concrete_id):
        """색상 범위를 업데이트합니다."""
        if not concrete_id:
            return 0, 100, [0, 100]
        
        try:
            # 온도 범위 계산
            temp_min, temp_max = get_temperature_range(concrete_id)
            return temp_min, temp_max, [temp_min, temp_max]
        except:
            return 0, 100, [0, 100]

def create_empty_3d_view():
    """빈 3D 뷰를 생성합니다."""
    fig = go.Figure()
    fig.update_layout(
        title="콘크리트를 선택해주세요",
        scene=dict(
            xaxis=dict(title="X (m)"),
            yaxis=dict(title="Y (m)"),
            zaxis=dict(title="Z (m)")
        ),
        height=600,
        showlegend=False
    )
    return fig

def create_error_3d_view(error_msg):
    """오류 3D 뷰를 생성합니다."""
    fig = go.Figure()
    fig.update_layout(
        title=f"오류: {error_msg}",
        scene=dict(
            xaxis=dict(title="X (m)"),
            yaxis=dict(title="Y (m)"),
            zaxis=dict(title="Z (m)")
        ),
        height=600,
        showlegend=False
    )
    return fig

def create_3d_heatmap(data, time_value, color_range, view_angle, zoom_level):
    """3D 히트맵을 생성합니다."""
    # 실제 구현에서는 콘크리트 데이터를 기반으로 3D 히트맵 생성
    # 여기서는 예시 데이터로 대체
    
    # 예시: 간단한 3D 박스
    x = np.linspace(0, 10, 20)
    y = np.linspace(0, 10, 20)
    z = np.linspace(0, 5, 10)
    
    X, Y, Z = np.meshgrid(x, y, z)
    
    # 온도 분포 (예시)
    temperature = 20 + 30 * np.exp(-((X-5)**2 + (Y-5)**2 + (Z-2.5)**2) / 10)
    
    fig = go.Figure(data=go.Volume(
        x=X.flatten(),
        y=Y.flatten(),
        z=Z.flatten(),
        value=temperature.flatten(),
        opacity=0.3,
        colorscale='Viridis',
        colorbar=dict(title="온도 (°C)")
    ))
    
    fig.update_layout(
        title=f"3D 온도 분포 (시간: {time_value}시간)",
        scene=dict(
            xaxis=dict(title="X (m)"),
            yaxis=dict(title="Y (m)"),
            zaxis=dict(title="Z (m)"),
            camera=dict(
                eye=dict(x=zoom_level * np.cos(np.radians(view_angle)), 
                        y=zoom_level * np.sin(np.radians(view_angle)), 
                        z=zoom_level)
            )
        ),
        height=600
    )
    
    return fig

def load_concrete_data(concrete_id):
    """콘크리트 데이터를 로드합니다."""
    # 실제 구현에서는 데이터베이스에서 데이터 로드
    # 여기서는 예시 데이터 반환
    return {
        "id": concrete_id,
        "name": f"콘크리트_{concrete_id}",
        "data": "example_data"
    }

def get_max_time(concrete_id):
    """콘크리트의 최대 시간을 반환합니다."""
    # 실제 구현에서는 데이터베이스에서 계산
    return 168  # 7일

def get_temperature_range(concrete_id):
    """온도 범위를 반환합니다."""
    # 실제 구현에서는 데이터베이스에서 계산
    return 0, 80 