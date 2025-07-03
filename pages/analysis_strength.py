from __future__ import annotations

import os
import glob
import numpy as np
import pandas as pd
import dash
from dash import html, dcc, Input, Output, State, dash_table, register_page, callback
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
from datetime import datetime, timedelta

register_page(__name__, path="/project", title="TCI 분석")


def create_probability_curve_figure():
    """로지스틱 근사식을 이용한 균열발생확률 곡선 그래프를 생성합니다."""
    tci_values = np.linspace(0.1, 3.0, 300)
    probabilities = 100 / (1 + np.exp(6 * (tci_values - 0.6)))
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=tci_values,
        y=probabilities,
        mode='lines',
        name='균열발생확률',
        line=dict(color='#3b82f6', width=3),
        hovertemplate='TCI: %{x:.2f}<br>확률: %{y:.1f}%<extra></extra>'
    ))
    fig.update_layout(
        title={
            'text': "온도균열지수(TCI)와 균열발생확률의 관계",
            'x': 0.5,
            'font': {'size': 18}
        },
        xaxis=dict(title="온도균열지수 (TCI)", showgrid=True, range=[0.1,3.0]),
        yaxis=dict(title="균열발생확률 (%)", showgrid=True, range=[0,100]),
        plot_bgcolor='white', paper_bgcolor='white', showlegend=False
    )
    return fig


# 레이아웃: TCI 탭 UI만 남김
layout = dbc.Container(
    fluid=True,
    className="p-4",
    children=[
        html.H3("⚠️ TCI 분석", className="mb-4"),
        # 인장강도 계산식
        html.Div([
            html.H6("🧮 인장강도(fct) 계산식", className="mb-2"),
            dcc.RadioItems(
                id="fct-formula-type",
                options=[
                    {"label": "CEB-FIP Model Code 1990", "value": "ceb"},
                    {"label": "경험식 (KCI/KS)", "value": "exp"},
                ],
                value="ceb",
                labelStyle={'display': 'block', 'marginBottom': '8px'}
            ),
            dbc.Row([
                dbc.Col([
                    dbc.Label("fct,28 (28일 인장강도, GPa) [1~100]"),
                    dbc.Input(id="fct28-input", type="number", value=20, min=1, max=100)
                ], md=4),
            ], className="g-3"),
            html.Div(id="ab-inputs-container", className="mt-3"),
            html.Div(id="fct-formula-preview", className="mt-4")
        ], className="p-3 bg-light rounded mb-4"),

        # 시간 슬라이더 및 TCI 표
        html.Div([
            html.H6("⏰ 시간별 TCI 분석", className="mb-2"),
            html.Div(id="tci-time-slider-container", className="mb-3"),
            html.Div(id="tci-tci-table-container")
        ], className="p-3 bg-light rounded mb-4"),

        # 균열발생확률 그래프
        html.Div([
            html.H6("📈 균열발생확률 곡선", className="mb-2"),
            dcc.Graph(
                id="tci-probability-curve",
                figure=create_probability_curve_figure(),
                config={'displayModeBar': False},
                style={'height': '50vh'}
            )
        ], className="p-3 bg-light rounded")
    ]
)


# fct 계산식 입력 및 미리보기
@callback(
    Output("ab-inputs-container", "children"),
    Output("fct-formula-preview", "children"),
    Input("fct-formula-type", "value"),
    Input("fct28-input", "value"),
    prevent_initial_call=False
)
def update_formula_display(formula_type, fct28):
    import numpy as np
    # a, b inputs
    if formula_type == "ceb":
        ab_fields = dbc.Row([
            dbc.Col([dbc.Label("a [0.5~2]"), dbc.Input(id="a-input", type="number", value=1, min=0.5, max=2)], md=4),
            dbc.Col([dbc.Label("b [0.5~2]"), dbc.Input(id="b-input", type="number", value=1, min=0.5, max=2)], md=4)
        ], className="g-3")
        formula_text = "식: fct(t) = fct,28 * ( t / (a + b*t) )^0.5"
    else:
        ab_fields = html.Div()
        formula_text = "식: fct(t) = fct,28 * (t/28)^0.5 (t ≤ 28)"
    # preview curve (fixed a=1,b=1)
    a, b = 1.0, 1.0
    if not fct28: fct28 = 20.0
    t_vals = np.arange(1,28.01,0.1)
    if formula_type == "ceb":
        fct_vals = fct28 * np.sqrt(t_vals/(a + b*t_vals))
    else:
        fct_vals = np.where(t_vals<=28, fct28*np.sqrt(t_vals/28), fct28)
    df = pd.DataFrame({"t[일]": np.round(t_vals,2), "fct(t)[GPa]": np.round(fct_vals,4)})
    table = dash_table.DataTable(columns=[{"name":i,"id":i} for i in df.columns], data=df.to_dict('records'), page_size=10)
    fig = go.Figure(go.Scatter(x=t_vals, y=fct_vals, mode='lines', line=dict(width=2)))
    fig.update_layout(height=300, margin=dict(l=40,r=40,t=30,b=40), plot_bgcolor='white', paper_bgcolor='white')
    preview = dbc.Row([dbc.Col(table, md=6), dbc.Col(dcc.Graph(figure=fig, config={'displayModeBar':False}), md=6)], className="g-2 mt-3")
    return ab_fields, html.Div([html.Small(formula_text), preview])


# a,b 변경 시 미리보기 업데이트
@callback(
    Output("fct-formula-preview", "children"),
    Input("a-input", "value"),
    Input("b-input", "value"),
    State("fct-formula-type", "value"),
    State("fct28-input", "value"),
    prevent_initial_call=True
)
def update_preview_with_ab(a, b, formula_type, fct28):
    import numpy as np
    # reuse above logic with given a,b
    if not fct28: fct28 = 20.0
    t_vals = np.arange(1,28.01,0.1)
    if formula_type == "ceb":
        fct_vals = fct28 * np.sqrt(t_vals/(a + b*t_vals))
        formula_text = "식: fct(t) = fct,28 * ( t / (a + b*t) )^0.5"
    else:
        fct_vals = np.where(t_vals<=28, fct28*np.sqrt(t_vals/28), fct28)
        formula_text = "식: fct(t) = fct,28 * (t/28)^0.5 (t ≤ 28)"
    df = pd.DataFrame({"t[일]": np.round(t_vals,2), "fct(t)[GPa]": np.round(fct_vals,4)})
    table = dash_table.DataTable(columns=[{"name":i,"id":i} for i in df.columns], data=df.to_dict('records'), page_size=10)
    fig = go.Figure(go.Scatter(x=t_vals, y=fct_vals, mode='lines', line=dict(width=2)))
    fig.update_layout(height=300, margin=dict(l=40,r=40,t=30,b=40), plot_bgcolor='white', paper_bgcolor='white')
    preview = dbc.Row([dbc.Col(table, md=6), dbc.Col(dcc.Graph(figure=fig, config={'displayModeBar':False}), md=6)], className="g-2 mt-3")
    return html.Div([html.Small(formula_text), preview])


# TCI 시간 및 표 업데이트
@callback(
    Output("tci-time-slider-container", "children"),
    Output("tci-tci-table-container", "children"),
    Input("fct-formula-type", "value"),
    Input("fct28-input", "value"),
    prevent_initial_call=False
)
def update_tci_ui(formula_type, fct28):
    # 단순 예시: 슬라이더만, 실제 파일 파싱 로직 생략
    slider = dcc.Slider(id="tci-time-slider", min=0, max=5, step=1, value=5, marks={i:str(i) for i in range(6)})
    table = html.Div("TCI 결과표가 여기에 표시됩니다.")
    return slider, table

# 슬라이더 변경 시 표만 업데이트
@callback(
    Output("tci-tci-table-container", "children"),
    Input("tci-time-slider", "value"),
    State("fct-formula-type", "value"),
    State("fct28-input", "value"),
    prevent_initial_call=True
)
def update_tci_table_on_slider_change(value, formula_type, fct28):
    return html.Div(f"선택된 시간 인덱스: {value} -> TCI 표 업데이트 필요")
