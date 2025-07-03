"""
TCI 분석 탭 모듈

온도균열지수(TCI) 분석과 관련된 레이아웃과 콜백을 포함합니다.
"""

import dash
from dash import html, dcc, Input, Output, State, callback
import dash_bootstrap_components as dbc
from dash.exceptions import PreventUpdate
import plotly.graph_objects as go
import numpy as np
import pandas as pd

def create_tci_tab():
    """TCI 분석 탭의 레이아웃을 생성합니다."""
    return dbc.Container([
        # ────────────────────────────── 입력 컨트롤 ────────────────────────────
        dbc.Row([
            dbc.Col([
                html.H5("🎛️ TCI 분석 컨트롤", className="mb-3"),
                dbc.Row([
                    dbc.Col([
                        html.Label("분석 시간:", className="form-label"),
                        dcc.Slider(
                            id="slider-time-tci",
                            min=0,
                            max=168,
                            step=1,
                            value=0,
                            marks={},
                            tooltip={"placement": "bottom", "always_visible": True}
                        )
                    ], md=6),
                    dbc.Col([
                        html.Label("TCI 임계값:", className="form-label"),
                        dcc.Slider(
                            id="slider-threshold-tci",
                            min=0.1,
                            max=1.0,
                            step=0.1,
                            value=0.5,
                            marks={},
                            tooltip={"placement": "bottom", "always_visible": True}
                        )
                    ], md=6)
                ])
            ], md=12)
        ], className="mb-4"),
        
        # ────────────────────────────── TCI 분석 결과 ────────────────────────────
        dbc.Row([
            dbc.Col([
                html.H5("📊 TCI 분석 결과", className="mb-3"),
                dcc.Graph(
                    id="graph-tci-result",
                    style={"height": "500px"},
                    config={
                        'displayModeBar': True,
                        'displaylogo': False,
                        'modeBarButtonsToRemove': ['pan2d', 'lasso2d', 'select2d'],
                        'toImageButtonOptions': {
                            'format': 'png',
                            'filename': 'tci_analysis',
                            'height': 500,
                            'width': 1000,
                            'scale': 2
                        }
                    }
                )
            ], md=12)
        ]),
        
        # ────────────────────────────── 위험도 평가 ────────────────────────────
        dbc.Row([
            dbc.Col([
                html.H5("⚠️ 위험도 평가", className="mb-3"),
                dbc.Card([
                    dbc.CardBody([
                        html.Div(id="risk-assessment", className="text-muted")
                    ])
                ])
            ], md=6),
            dbc.Col([
                html.H5("📈 TCI 확률 곡선", className="mb-3"),
                dcc.Graph(
                    id="graph-tci-probability",
                    style={"height": "300px"},
                    config={
                        'displayModeBar': False,
                        'displaylogo': False
                    }
                )
            ], md=6)
        ], className="mt-4")
    ], fluid=True)

def register_tci_callbacks():
    """TCI 분석 탭의 콜백들을 등록합니다."""
    
    @callback(
        Output("graph-tci-result", "figure"),
        Output("risk-assessment", "children"),
        Input("dropdown-concrete", "value"),
        Input("slider-time-tci", "value"),
        Input("slider-threshold-tci", "value"),
        prevent_initial_call=True
    )
    def update_tci_analysis(concrete_id, time_value, threshold):
        """TCI 분석 결과를 업데이트합니다."""
        if not concrete_id:
            return create_empty_tci_graph(), "콘크리트를 선택해주세요"
        
        try:
            # TCI 데이터 로드
            tci_data = load_tci_data(concrete_id, time_value)
            if not tci_data:
                return create_empty_tci_graph(), "데이터를 불러올 수 없습니다"
            
            # TCI 분석 그래프 생성
            fig = create_tci_analysis_graph(tci_data, threshold)
            
            # 위험도 평가
            risk_text = calculate_risk_assessment(tci_data, threshold)
            
            return fig, risk_text
            
        except Exception as e:
            return create_error_tci_graph(str(e)), f"오류 발생: {str(e)}"
    
    @callback(
        Output("graph-tci-probability", "figure"),
        Input("slider-threshold-tci", "value"),
        prevent_initial_call=True
    )
    def update_tci_probability(threshold):
        """TCI 확률 곡선을 업데이트합니다."""
        try:
            fig = create_tci_probability_curve(threshold)
            return fig
        except Exception as e:
            return create_empty_probability_graph()
    
    @callback(
        Output("slider-time-tci", "max"),
        Output("slider-time-tci", "marks"),
        Input("dropdown-concrete", "value"),
        prevent_initial_call=True
    )
    def update_time_slider_tci(concrete_id):
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

def create_empty_tci_graph():
    """빈 TCI 그래프를 생성합니다."""
    fig = go.Figure()
    fig.update_layout(
        title="콘크리트를 선택해주세요",
        xaxis=dict(title="X (m)"),
        yaxis=dict(title="Y (m)"),
        height=500
    )
    return fig

def create_error_tci_graph(error_msg):
    """오류 TCI 그래프를 생성합니다."""
    fig = go.Figure()
    fig.update_layout(
        title=f"오류: {error_msg}",
        xaxis=dict(title="X (m)"),
        yaxis=dict(title="Y (m)"),
        height=500
    )
    return fig

def create_tci_analysis_graph(data, threshold):
    """TCI 분석 그래프를 생성합니다."""
    # 실제 구현에서는 TCI 데이터를 기반으로 그래프 생성
    # 여기서는 예시 데이터로 대체
    
    # 예시: 2D TCI 분포
    x = np.linspace(0, 10, 50)
    y = np.linspace(0, 10, 50)
    X, Y = np.meshgrid(x, y)
    
    # TCI 분포 (예시)
    tci_values = 0.3 + 0.6 * np.exp(-((X-5)**2 + (Y-5)**2) / 10)
    
    fig = go.Figure(data=go.Heatmap(
        z=tci_values,
        x=x,
        y=y,
        colorscale='RdYlGn_r',  # 빨강(위험) - 노랑 - 초록(안전)
        zmin=0,
        zmax=1,
        colorbar=dict(title="TCI 값")
    ))
    
    # 임계값 기준선 추가
    fig.add_hline(y=threshold, line_dash="dash", line_color="red", 
                  annotation_text=f"임계값: {threshold}")
    
    fig.update_layout(
        title=f"TCI 분포 (시간: {data.get('time', 0)}시간)",
        xaxis=dict(title="X (m)"),
        yaxis=dict(title="Y (m)"),
        height=500
    )
    
    return fig

def create_tci_probability_curve(threshold):
    """TCI 확률 곡선을 생성합니다."""
    # TCI 값 범위
    tci_values = np.linspace(0.1, 1.0, 100)
    
    # 로지스틱 확률 함수
    probability = 100 / (1 + np.exp(54 * (tci_values - 0.4925)))
    
    fig = go.Figure()
    
    # 확률 곡선
    fig.add_trace(go.Scatter(
        x=tci_values,
        y=probability,
        mode='lines',
        name='균열발생확률',
        line=dict(color='blue', width=2)
    ))
    
    # 임계값 기준선
    threshold_prob = 100 / (1 + np.exp(54 * (threshold - 0.4925)))
    fig.add_vline(x=threshold, line_dash="dash", line_color="red",
                  annotation_text=f"임계값: {threshold:.1f}")
    fig.add_hline(y=threshold_prob, line_dash="dash", line_color="orange",
                  annotation_text=f"확률: {threshold_prob:.1f}%")
    
    fig.update_layout(
        title="TCI와 균열발생확률의 관계",
        xaxis=dict(title="TCI 값"),
        yaxis=dict(title="균열발생확률 (%)"),
        height=300,
        showlegend=False
    )
    
    return fig

def create_empty_probability_graph():
    """빈 확률 그래프를 생성합니다."""
    fig = go.Figure()
    fig.update_layout(
        title="TCI 확률 곡선",
        xaxis=dict(title="TCI 값"),
        yaxis=dict(title="균열발생확률 (%)"),
        height=300
    )
    return fig

def load_tci_data(concrete_id, time_value):
    """TCI 데이터를 로드합니다."""
    # 실제 구현에서는 데이터베이스에서 데이터 로드
    return {
        "concrete_id": concrete_id,
        "time": time_value,
        "tci_values": "example_tci_data"
    }

def calculate_risk_assessment(data, threshold):
    """위험도 평가를 계산합니다."""
    # 실제 구현에서는 TCI 데이터를 기반으로 위험도 계산
    # 여기서는 예시 계산
    
    # 예시: 임계값 대비 위험도
    if threshold <= 0.4:
        risk_level = "🔴 매우 위험"
        risk_desc = "균열 발생 확률이 매우 높습니다."
    elif threshold <= 0.5:
        risk_level = "🟠 위험"
        risk_desc = "균열 발생 확률이 높습니다."
    elif threshold <= 0.7:
        risk_level = "🟡 주의"
        risk_desc = "균열 발생 가능성이 있습니다."
    else:
        risk_level = "🟢 안전"
        risk_desc = "균열 발생 확률이 낮습니다."
    
    return f"""
    <strong>위험도: {risk_level}</strong><br>
    {risk_desc}<br>
    TCI 임계값: {threshold:.1f}<br>
    분석 시간: {data.get('time', 0)}시간
    """

def get_max_time(concrete_id):
    """콘크리트의 최대 시간을 반환합니다."""
    # 실제 구현에서는 데이터베이스에서 계산
    return 168  # 7일 