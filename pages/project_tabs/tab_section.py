"""
단면도 탭 모듈

X, Y, Z 단면도와 관련된 레이아웃과 콜백을 포함합니다.
"""

import dash
from dash import html, dcc, Input, Output, State, callback
import dash_bootstrap_components as dbc
from dash.exceptions import PreventUpdate
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import numpy as np
import pandas as pd

def create_section_tab():
    """단면도 탭의 레이아웃을 생성합니다."""
    return dbc.Container([
        # ────────────────────────────── 입력 컨트롤 ────────────────────────────
        dbc.Row([
            dbc.Col([
                html.H5("🎛️ 단면도 컨트롤", className="mb-3"),
                dbc.Row([
                    dbc.Col([
                        html.Label("X 단면 위치:", className="form-label"),
                        dcc.Slider(
                            id="slider-x-section",
                            min=0,
                            max=100,
                            step=1,
                            value=50,
                            marks={},
                            tooltip={"placement": "bottom", "always_visible": True}
                        )
                    ], md=4),
                    dbc.Col([
                        html.Label("Y 단면 위치:", className="form-label"),
                        dcc.Slider(
                            id="slider-y-section",
                            min=0,
                            max=100,
                            step=1,
                            value=50,
                            marks={},
                            tooltip={"placement": "bottom", "always_visible": True}
                        )
                    ], md=4),
                    dbc.Col([
                        html.Label("Z 단면 위치:", className="form-label"),
                        dcc.Slider(
                            id="slider-z-section",
                            min=0,
                            max=100,
                            step=1,
                            value=50,
                            marks={},
                            tooltip={"placement": "bottom", "always_visible": True}
                        )
                    ], md=4)
                ], className="mb-3"),
                dbc.Row([
                    dbc.Col([
                        html.Label("시간:", className="form-label"),
                        dcc.Slider(
                            id="slider-time-section",
                            min=0,
                            max=100,
                            step=1,
                            value=0,
                            marks={},
                            tooltip={"placement": "bottom", "always_visible": True}
                        )
                    ], md=12)
                ])
            ], md=12)
        ], className="mb-4"),
        
        # ────────────────────────────── 단면도 뷰어 ────────────────────────────
        dbc.Row([
            dbc.Col([
                html.H5("📐 단면도 뷰어", className="mb-3"),
                dcc.Graph(
                    id="graph-section-view",
                    style={"height": "800px"},
                    config={
                        'displayModeBar': True,
                        'displaylogo': False,
                        'modeBarButtonsToRemove': ['pan2d', 'lasso2d', 'select2d'],
                        'toImageButtonOptions': {
                            'format': 'png',
                            'filename': 'section_view',
                            'height': 800,
                            'width': 1200,
                            'scale': 2
                        }
                    }
                )
            ], md=12)
        ]),
        
        # ────────────────────────────── 정보 패널 ────────────────────────────
        dbc.Row([
            dbc.Col([
                html.H5("ℹ️ 단면 정보", className="mb-3"),
                dbc.Card([
                    dbc.CardBody([
                        html.Div(id="info-section-view", className="text-muted")
                    ])
                ])
            ], md=12)
        ], className="mt-4")
    ], fluid=True)

def register_section_callbacks():
    """단면도 탭의 콜백들을 등록합니다."""
    
    @callback(
        Output("graph-section-view", "figure"),
        Output("info-section-view", "children"),
        Input("dropdown-concrete", "value"),
        Input("slider-x-section", "value"),
        Input("slider-y-section", "value"),
        Input("slider-z-section", "value"),
        Input("slider-time-section", "value"),
        State("store-section-view", "data"),
        prevent_initial_call=True
    )
    def update_section_view(concrete_id, x_pos, y_pos, z_pos, time_value, stored_view):
        """단면도 뷰를 업데이트합니다."""
        if not concrete_id:
            return create_empty_section_view(), "콘크리트를 선택해주세요"
        
        try:
            # 콘크리트 데이터 로드
            concrete_data = load_concrete_data(concrete_id)
            if not concrete_data:
                return create_empty_section_view(), "데이터를 불러올 수 없습니다"
            
            # 단면도 생성
            fig = create_section_plots(concrete_data, x_pos, y_pos, z_pos, time_value)
            
            # 정보 업데이트
            info_text = f"X: {x_pos}%, Y: {y_pos}%, Z: {z_pos}%, 시간: {time_value}시간"
            
            return fig, info_text
            
        except Exception as e:
            return create_error_section_view(str(e)), f"오류 발생: {str(e)}"
    
    @callback(
        Output("slider-time-section", "max"),
        Output("slider-time-section", "marks"),
        Input("dropdown-concrete", "value"),
        prevent_initial_call=True
    )
    def update_time_slider_section(concrete_id):
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

def create_empty_section_view():
    """빈 단면도 뷰를 생성합니다."""
    fig = make_subplots(
        rows=2, cols=2,
        subplot_titles=('3D 뷰', 'X 단면도', 'Y 단면도', 'Z 단면도'),
        specs=[[{"type": "scene"}, {"type": "xy"}],
               [{"type": "xy"}, {"type": "xy"}]]
    )
    
    fig.update_layout(
        title="콘크리트를 선택해주세요",
        height=800,
        showlegend=False
    )
    
    return fig

def create_error_section_view(error_msg):
    """오류 단면도 뷰를 생성합니다."""
    fig = make_subplots(
        rows=2, cols=2,
        subplot_titles=('3D 뷰', 'X 단면도', 'Y 단면도', 'Z 단면도'),
        specs=[[{"type": "scene"}, {"type": "xy"}],
               [{"type": "xy"}, {"type": "xy"}]]
    )
    
    fig.update_layout(
        title=f"오류: {error_msg}",
        height=800,
        showlegend=False
    )
    
    return fig

def create_section_plots(data, x_pos, y_pos, z_pos, time_value):
    """단면도 플롯들을 생성합니다."""
    # 실제 구현에서는 콘크리트 데이터를 기반으로 단면도 생성
    # 여기서는 예시 데이터로 대체
    
    fig = make_subplots(
        rows=2, cols=2,
        subplot_titles=('3D 뷰', 'X 단면도', 'Y 단면도', 'Z 단면도'),
        specs=[[{"type": "scene"}, {"type": "xy"}],
               [{"type": "xy"}, {"type": "xy"}]]
    )
    
    # 3D 뷰 추가
    x = np.linspace(0, 10, 20)
    y = np.linspace(0, 10, 20)
    z = np.linspace(0, 5, 10)
    
    X, Y, Z = np.meshgrid(x, y, z)
    temperature = 20 + 30 * np.exp(-((X-5)**2 + (Y-5)**2 + (Z-2.5)**2) / 10)
    
    fig.add_trace(
        go.Volume(
            x=X.flatten(),
            y=Y.flatten(),
            z=Z.flatten(),
            value=temperature.flatten(),
            opacity=0.3,
            colorscale='Viridis',
            name="3D 뷰"
        ),
        row=1, col=1
    )
    
    # X 단면도 (Y-Z 평면)
    y_section = np.linspace(0, 10, 50)
    z_section = np.linspace(0, 5, 25)
    Y_section, Z_section = np.meshgrid(y_section, z_section)
    temp_x_section = 20 + 30 * np.exp(-((x_pos/10-5)**2 + (Y_section-5)**2 + (Z_section-2.5)**2) / 10)
    
    fig.add_trace(
        go.Heatmap(
            z=temp_x_section,
            x=y_section,
            y=z_section,
            colorscale='Viridis',
            name="X 단면도"
        ),
        row=1, col=2
    )
    
    # Y 단면도 (X-Z 평면)
    x_section = np.linspace(0, 10, 50)
    z_section = np.linspace(0, 5, 25)
    X_section, Z_section = np.meshgrid(x_section, z_section)
    temp_y_section = 20 + 30 * np.exp(-((X_section-5)**2 + (y_pos/10-5)**2 + (Z_section-2.5)**2) / 10)
    
    fig.add_trace(
        go.Heatmap(
            z=temp_y_section,
            x=x_section,
            y=z_section,
            colorscale='Viridis',
            name="Y 단면도"
        ),
        row=2, col=1
    )
    
    # Z 단면도 (X-Y 평면)
    x_section = np.linspace(0, 10, 50)
    y_section = np.linspace(0, 10, 50)
    X_section, Y_section = np.meshgrid(x_section, y_section)
    temp_z_section = 20 + 30 * np.exp(-((X_section-5)**2 + (Y_section-5)**2 + (z_pos/5-2.5)**2) / 10)
    
    fig.add_trace(
        go.Heatmap(
            z=temp_z_section,
            x=x_section,
            y=y_section,
            colorscale='Viridis',
            name="Z 단면도"
        ),
        row=2, col=2
    )
    
    # 레이아웃 업데이트
    fig.update_layout(
        title=f"단면도 뷰 (시간: {time_value}시간)",
        height=800,
        showlegend=False
    )
    
    # 축 레이블 업데이트
    fig.update_xaxes(title_text="Y (m)", row=1, col=2)
    fig.update_yaxes(title_text="Z (m)", row=1, col=2)
    fig.update_xaxes(title_text="X (m)", row=2, col=1)
    fig.update_yaxes(title_text="Z (m)", row=2, col=1)
    fig.update_xaxes(title_text="X (m)", row=2, col=2)
    fig.update_yaxes(title_text="Y (m)", row=2, col=2)
    
    return fig

def load_concrete_data(concrete_id):
    """콘크리트 데이터를 로드합니다."""
    # 실제 구현에서는 데이터베이스에서 데이터 로드
    return {
        "id": concrete_id,
        "name": f"콘크리트_{concrete_id}",
        "data": "example_data"
    }

def get_max_time(concrete_id):
    """콘크리트의 최대 시간을 반환합니다."""
    # 실제 구현에서는 데이터베이스에서 계산
    return 168  # 7일 