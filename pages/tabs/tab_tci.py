#!/usr/bin/env python3
"""TCI 분석 탭 모듈"""

import os
import glob
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime
import dash
from dash import (
    html, dcc, Input, Output, State,
    dash_table, callback
)
import dash_bootstrap_components as dbc
from dash.exceptions import PreventUpdate
from scipy.interpolate import griddata
import ast
import json
from urllib.parse import parse_qs, urlparse

from .utils import parse_material_info_from_inp, create_probability_curve_figure

def create_tci_tab_layout():
    """TCI 분석 탭 레이아웃을 생성합니다."""
    return html.Div([
        # TCI 설정 섹션
        html.Div([
            html.H6("⚙️ TCI 설정", style={
                "fontWeight": "600",
                "color": "#374151",
                "marginBottom": "16px",
                "fontSize": "14px"
            }),
            dbc.Row([
                dbc.Col([
                    dbc.Label("FCT 공식 유형", style={"fontWeight": "500", "color": "#374151"}),
                    dcc.Dropdown(
                        id="fct-formula-type",
                        options=[
                            {"label": "표준 공식", "value": "standard"},
                            {"label": "사용자 정의", "value": "custom"}
                        ],
                        value="standard",
                        style={"borderRadius": "6px", "border": "1px solid #d1d5db"}
                    )
                ], md=4),
                dbc.Col([
                    dbc.Label("FCT28 (MPa)", style={"fontWeight": "500", "color": "#374151"}),
                    dbc.Input(
                        id="fct28-input",
                        type="number",
                        value=3.0,
                        min=0.1,
                        max=10.0,
                        step=0.1,
                        style={"borderRadius": "6px", "border": "1px solid #d1d5db"}
                    )
                ], md=4),
                dbc.Col([
                    dbc.Label("시간", style={"fontWeight": "500", "color": "#374151"}),
                    dcc.Slider(
                        id="tci-time-slider",
                        min=0,
                        max=5,
                        step=1,
                        value=0,
                        marks={},
                        tooltip={"placement": "bottom", "always_visible": True},
                    )
                ], md=4),
            ])
        ], style={
            "padding": "16px 20px",
            "backgroundColor": "#f9fafb",
            "borderRadius": "8px",
            "border": "1px solid #e5e7eb",
            "marginBottom": "16px"
        }),
        
        # 사용자 정의 공식 입력 (조건부 표시)
        html.Div([
            html.H6("📝 사용자 정의 공식", style={
                "fontWeight": "600",
                "color": "#374151",
                "marginBottom": "16px",
                "fontSize": "14px"
            }),
            dbc.Row([
                dbc.Col([
                    dbc.Label("계수 A", style={"fontWeight": "500", "color": "#374151"}),
                    dbc.Input(
                        id="a-input",
                        type="number",
                        value=1.0,
                        step=0.1,
                        style={"borderRadius": "6px", "border": "1px solid #d1d5db"}
                    )
                ], md=6),
                dbc.Col([
                    dbc.Label("계수 B", style={"fontWeight": "500", "color": "#374151"}),
                    dbc.Input(
                        id="b-input",
                        type="number",
                        value=0.5,
                        step=0.1,
                        style={"borderRadius": "6px", "border": "1px solid #d1d5db"}
                    )
                ], md=6),
            ]),
            html.Div([
                html.H6("공식 미리보기", style={
                    "fontWeight": "600",
                    "color": "#374151",
                    "marginBottom": "8px"
                }),
                html.Div(
                    id="fct-formula-preview",
                    style={
                        "padding": "12px",
                        "backgroundColor": "#f3f4f6",
                        "borderRadius": "6px",
                        "fontFamily": "monospace",
                        "fontSize": "14px"
                    }
                )
            ], style={"marginTop": "16px"})
        ], id="ab-inputs-container", style={
            "padding": "16px 20px",
            "backgroundColor": "#f8fafc",
            "borderRadius": "8px",
            "border": "1px solid #e2e8f0",
            "marginBottom": "16px",
            "display": "none"
        }),
        
        # TCI 분석 결과
        dbc.Row([
            # TCI 확률 곡선
            dbc.Col([
                html.Div([
                    html.H6("📊 TCI 확률 곡선", style={
                        "fontWeight": "600",
                        "color": "#374151",
                        "marginBottom": "12px"
                    }),
                    dcc.Graph(
                        id="tci-probability-curve",
                        figure=create_probability_curve_figure(),
                        style={
                            "height": "400px",
                            "borderRadius": "8px",
                            "border": "1px solid #e5e7eb"
                        },
                        config={
                            'displayModeBar': True,
                            'displaylogo': False,
                            'modeBarButtonsToRemove': ['pan2d', 'lasso2d', 'select2d'],
                            'toImageButtonOptions': {
                                'format': 'png',
                                'filename': 'tci_probability_curve',
                                'height': 400,
                                'width': 600,
                                'scale': 2
                            }
                        }
                    )
                ], style={
                    "backgroundColor": "white",
                    "borderRadius": "8px",
                    "padding": "16px",
                    "marginBottom": "16px"
                })
            ], md=6),
            
            # TCI 테이블
            dbc.Col([
                html.Div([
                    html.H6("📋 TCI 분석 결과", style={
                        "fontWeight": "600",
                        "color": "#374151",
                        "marginBottom": "12px"
                    }),
                    html.Div(
                        id="tci-tci-table-container",
                        style={
                            "maxHeight": "400px",
                            "overflowY": "auto"
                        }
                    )
                ], style={
                    "backgroundColor": "white",
                    "borderRadius": "8px",
                    "padding": "16px",
                    "marginBottom": "16px"
                })
            ], md=6),
        ]),
        
        # 시간별 TCI 슬라이더
        html.Div([
            html.H6("⏰ TCI 시간 설정", style={
                "fontWeight": "600",
                "color": "#374151",
                "marginBottom": "12px"
            }),
            html.Div(
                id="tci-time-slider-container",
                style={
                    "padding": "16px 20px",
                    "backgroundColor": "#f9fafb",
                    "borderRadius": "8px",
                    "border": "1px solid #e5e7eb"
                }
            )
        ], style={"marginBottom": "16px"}),
    ])

def create_tci_tab_content(selected_rows, tbl_data):
    """TCI 탭 콘텐츠를 생성합니다."""
    return create_tci_tab_layout()

# 콜백 함수들
@callback(
    Output("ab-inputs-container", "children"),
    Output("fct-formula-preview", "children"),
    Input("fct-formula-type", "value"),
    Input("fct28-input", "value"),
    prevent_initial_call=False
)
def update_formula_display(formula_type, fct28):
    """공식 표시를 업데이트합니다."""
    if formula_type == "custom":
        # 사용자 정의 공식 입력 필드들
        inputs = html.Div([
            html.H6("📝 사용자 정의 공식", style={
                "fontWeight": "600",
                "color": "#374151",
                "marginBottom": "16px",
                "fontSize": "14px"
            }),
            dbc.Row([
                dbc.Col([
                    dbc.Label("계수 A", style={"fontWeight": "500", "color": "#374151"}),
                    dbc.Input(
                        id="a-input",
                        type="number",
                        value=1.0,
                        step=0.1,
                        style={"borderRadius": "6px", "border": "1px solid #d1d5db"}
                    )
                ], md=6),
                dbc.Col([
                    dbc.Label("계수 B", style={"fontWeight": "500", "color": "#374151"}),
                    dbc.Input(
                        id="b-input",
                        type="number",
                        value=0.5,
                        step=0.1,
                        style={"borderRadius": "6px", "border": "1px solid #d1d5db"}
                    )
                ], md=6),
            ]),
            html.Div([
                html.H6("공식 미리보기", style={
                    "fontWeight": "600",
                    "color": "#374151",
                    "marginBottom": "8px"
                }),
                html.Div(
                    id="fct-formula-preview",
                    style={
                        "padding": "12px",
                        "backgroundColor": "#f3f4f6",
                        "borderRadius": "6px",
                        "fontFamily": "monospace",
                        "fontSize": "14px"
                    }
                )
            ], style={"marginTop": "16px"})
        ])
        
        # 공식 미리보기
        if fct28:
            formula_preview = f"FCT(t) = {fct28:.1f} × (t/28)^0.5"
        else:
            formula_preview = "FCT(t) = FCT28 × (t/28)^0.5"
        
        return inputs, formula_preview
    else:
        # 표준 공식
        if fct28:
            formula_preview = f"FCT(t) = {fct28:.1f} × (t/28)^0.5"
        else:
            formula_preview = "FCT(t) = FCT28 × (t/28)^0.5"
        
        return html.Div(), formula_preview

@callback(
    Output("fct-formula-preview", "children", allow_duplicate=True),
    Input("a-input", "value"),
    Input("b-input", "value"),
    State("fct-formula-type", "value"),
    State("fct28-input", "value"),
    prevent_initial_call=True
)
def update_preview_with_ab(a, b, formula_type, fct28):
    """A, B 계수로 공식 미리보기를 업데이트합니다."""
    if formula_type == "custom" and fct28:
        formula_preview = f"FCT(t) = {fct28:.1f} × {a:.1f} × (t/28)^{b:.1f}"
    elif fct28:
        formula_preview = f"FCT(t) = {fct28:.1f} × (t/28)^0.5"
    else:
        formula_preview = "FCT(t) = FCT28 × (t/28)^0.5"
    
    return formula_preview

@callback(
    Output("tci-time-slider-container", "children"),
    Output("tci-tci-table-container", "children", allow_duplicate=True),
    Input("tbl-concrete", "selected_rows"),
    State("tbl-concrete", "data"),
    Input("fct-formula-type", "value"),
    Input("fct28-input", "value"),
    Input("tab-content", "children"),
    Input("tabs-main", "active_tab"),
    prevent_initial_call='initial_duplicate'
)
def update_tci_time_and_table(selected_rows, tbl_data, formula_type, fct28, tab_content, active_tab):
    """TCI 시간 슬라이더와 테이블을 업데이트합니다."""
    if active_tab != "tab-tci":
        raise PreventUpdate
    
    if not selected_rows or not tbl_data:
        return html.Div("콘크리트를 선택하세요"), html.Div("TCI 데이터가 없습니다")
    
    try:
        row = pd.DataFrame(tbl_data).iloc[selected_rows[0]]
        concrete_pk = row["concrete_pk"]
        concrete_name = row["name"]
        
        # INP 파일들 로드
        inp_dir = f"inp/{concrete_pk}"
        inp_files = sorted(glob.glob(f"{inp_dir}/*.inp"))
        
        if not inp_files:
            return html.Div("분석 데이터가 없습니다"), html.Div("TCI 계산을 위한 데이터가 없습니다")
        
        # 시간 슬라이더 생성
        time_slider = dcc.Slider(
            id="tci-time-slider",
            min=0,
            max=len(inp_files) - 1,
            step=1,
            value=0,
            marks={i: f"T{i}" for i in range(len(inp_files))},
            tooltip={"placement": "bottom", "always_visible": True},
        )
        
        # TCI 테이블 생성 (간단한 예시)
        tci_data = []
        for i, inp_file in enumerate(inp_files):
            try:
                with open(inp_file, 'r') as f:
                    lines = f.readlines()
                
                # 온도 데이터 파싱
                temp_section = False
                temps = []
                for line in lines:
                    if line.startswith('*TEMPERATURE'):
                        temp_section = True
                        continue
                    elif line.startswith('*'):
                        temp_section = False
                        continue
                    if temp_section and ',' in line:
                        parts = line.strip().split(',')
                        if len(parts) >= 2:
                            try:
                                temp = float(parts[1])
                                temps.append(temp)
                            except:
                                continue
                
                if temps and fct28:
                    # 간단한 TCI 계산 (예시)
                    avg_temp = np.mean(temps)
                    max_temp = np.max(temps)
                    
                    # FCT 계산 (간단한 예시)
                    if formula_type == "custom":
                        # 사용자 정의 공식 (실제로는 a, b 값을 가져와야 함)
                        fct = fct28 * (i + 1) ** 0.5
                    else:
                        fct = fct28 * ((i + 1) / 28) ** 0.5
                    
                    # TCI 계산 (간단한 예시)
                    tci_min = fct / (avg_temp + 273.15) if avg_temp > -273 else 0
                    tci_max = fct / (max_temp + 273.15) if max_temp > -273 else 0
                    
                    # 확률 계산
                    def crack_probability(tci):
                        return 100 / (1 + np.exp(6 * (tci - 0.6)))
                    
                    prob_min = crack_probability(tci_min)
                    prob_max = crack_probability(tci_max)
                    
                    tci_data.append({
                        "시간": f"T{i}",
                        "평균온도": f"{avg_temp:.1f}°C",
                        "최고온도": f"{max_temp:.1f}°C",
                        "FCT": f"{fct:.2f}MPa",
                        "TCI-MIN": f"{tci_min:.3f}",
                        "TCI-MAX": f"{tci_max:.3f}",
                        "TCI-MIN-P(%)": f"{prob_min:.1f}",
                        "TCI-MAX-P(%)": f"{prob_max:.1f}"
                    })
                
            except Exception as e:
                print(f"TCI 계산 오류 (T{i}): {e}")
                continue
        
        if not tci_data:
            return time_slider, html.Div("TCI 계산 결과가 없습니다")
        
        # 테이블 생성
        columns = [
            {"name": "시간", "id": "시간"},
            {"name": "평균온도", "id": "평균온도"},
            {"name": "최고온도", "id": "최고온도"},
            {"name": "FCT", "id": "FCT"},
            {"name": "TCI-MIN", "id": "TCI-MIN"},
            {"name": "TCI-MAX", "id": "TCI-MAX"},
            {"name": "TCI-MIN-P(%)", "id": "TCI-MIN-P(%)"},
            {"name": "TCI-MAX-P(%)", "id": "TCI-MAX-P(%)"}
        ]
        
        # 스타일 조건부 설정
        style_data_conditional = [
            {
                "if": {"column_id": "TCI-MIN-P(%)", "filter_query": "{TCI-MIN-P(%)} >= 50.0"},
                "backgroundColor": "#fef2f2",
                "color": "#dc2626"
            },
            {
                "if": {"column_id": "TCI-MIN-P(%)", "filter_query": "{TCI-MIN-P(%)} < 50.0"},
                "backgroundColor": "#f0fdf4",
                "color": "#16a34a"
            },
            {
                "if": {"column_id": "TCI-MAX-P(%)", "filter_query": "{TCI-MAX-P(%)} >= 50.0"},
                "backgroundColor": "#fef2f2",
                "color": "#dc2626"
            },
            {
                "if": {"column_id": "TCI-MAX-P(%)", "filter_query": "{TCI-MAX-P(%)} < 50.0"},
                "backgroundColor": "#f0fdf4",
                "color": "#16a34a"
            }
        ]
        
        tci_table = dash_table.DataTable(
            data=tci_data,
            columns=columns,
            style_table={
                "borderRadius": "8px",
                "overflow": "hidden",
                "border": "1px solid #e5e7eb"
            },
            style_header={
                "backgroundColor": "#f9fafb",
                "color": "#374151",
                "fontWeight": "600",
                "textAlign": "center",
                "border": "none"
            },
            style_cell={
                "textAlign": "center",
                "padding": "8px 4px",
                "border": "1px solid #f3f4f6",
                "fontSize": "12px"
            },
            style_data_conditional=style_data_conditional,
            style_data={
                "backgroundColor": "white",
                "color": "#374151"
            },
            page_action="none",
            style_as_list_view=True
        )
        
        return time_slider, tci_table
        
    except Exception as e:
        print(f"TCI 분석 오류: {e}")
        return html.Div("TCI 분석 오류"), html.Div(f"오류: {str(e)}")

@callback(
    Output("tci-tci-table-container", "children", allow_duplicate=True),
    Input("tci-time-slider", "value"),
    State("tbl-concrete", "selected_rows"),
    State("tbl-concrete", "data"),
    State("fct-formula-type", "value"),
    State("fct28-input", "value"),
    prevent_initial_call=True
)
def update_tci_table_on_slider_change(slider_value, selected_rows, tbl_data, formula_type, fct28):
    """슬라이더 변경 시 TCI 테이블을 업데이트합니다."""
    if not selected_rows or not tbl_data:
        return html.Div("콘크리트를 선택하세요")
    
    try:
        row = pd.DataFrame(tbl_data).iloc[selected_rows[0]]
        concrete_pk = row["concrete_pk"]
        
        # INP 파일들 로드
        inp_dir = f"inp/{concrete_pk}"
        inp_files = sorted(glob.glob(f"{inp_dir}/*.inp"))
        
        if not inp_files or slider_value >= len(inp_files):
            return html.Div("데이터가 없습니다")
        
        # 선택된 시간의 파일 처리
        inp_file = inp_files[slider_value]
        
        with open(inp_file, 'r') as f:
            lines = f.readlines()
        
        # 온도 데이터 파싱
        temp_section = False
        temps = []
        for line in lines:
            if line.startswith('*TEMPERATURE'):
                temp_section = True
                continue
            elif line.startswith('*'):
                temp_section = False
                continue
            if temp_section and ',' in line:
                parts = line.strip().split(',')
                if len(parts) >= 2:
                    try:
                        temp = float(parts[1])
                        temps.append(temp)
                    except:
                        continue
        
        if not temps or not fct28:
            return html.Div("온도 데이터가 없습니다")
        
        # TCI 계산
        avg_temp = np.mean(temps)
        max_temp = np.max(temps)
        
        # FCT 계산
        if formula_type == "custom":
            fct = fct28 * (slider_value + 1) ** 0.5
        else:
            fct = fct28 * ((slider_value + 1) / 28) ** 0.5
        
        # TCI 계산
        tci_min = fct / (avg_temp + 273.15) if avg_temp > -273 else 0
        tci_max = fct / (max_temp + 273.15) if max_temp > -273 else 0
        
        # 확률 계산
        def crack_probability(tci):
            return 100 / (1 + np.exp(6 * (tci - 0.6)))
        
        prob_min = crack_probability(tci_min)
        prob_max = crack_probability(tci_max)
        
        # 단일 행 테이블 생성
        tci_data = [{
            "시간": f"T{slider_value}",
            "평균온도": f"{avg_temp:.1f}°C",
            "최고온도": f"{max_temp:.1f}°C",
            "FCT": f"{fct:.2f}MPa",
            "TCI-MIN": f"{tci_min:.3f}",
            "TCI-MAX": f"{tci_max:.3f}",
            "TCI-MIN-P(%)": f"{prob_min:.1f}",
            "TCI-MAX-P(%)": f"{prob_max:.1f}"
        }]
        
        columns = [
            {"name": "시간", "id": "시간"},
            {"name": "평균온도", "id": "평균온도"},
            {"name": "최고온도", "id": "최고온도"},
            {"name": "FCT", "id": "FCT"},
            {"name": "TCI-MIN", "id": "TCI-MIN"},
            {"name": "TCI-MAX", "id": "TCI-MAX"},
            {"name": "TCI-MIN-P(%)", "id": "TCI-MIN-P(%)"},
            {"name": "TCI-MAX-P(%)", "id": "TCI-MAX-P(%)"}
        ]
        
        # 스타일 조건부 설정
        style_data_conditional = [
            {
                "if": {"column_id": "TCI-MIN-P(%)", "filter_query": "{TCI-MIN-P(%)} >= 50.0"},
                "backgroundColor": "#fef2f2",
                "color": "#dc2626"
            },
            {
                "if": {"column_id": "TCI-MIN-P(%)", "filter_query": "{TCI-MIN-P(%)} < 50.0"},
                "backgroundColor": "#f0fdf4",
                "color": "#16a34a"
            },
            {
                "if": {"column_id": "TCI-MAX-P(%)", "filter_query": "{TCI-MAX-P(%)} >= 50.0"},
                "backgroundColor": "#fef2f2",
                "color": "#dc2626"
            },
            {
                "if": {"column_id": "TCI-MAX-P(%)", "filter_query": "{TCI-MAX-P(%)} < 50.0"},
                "backgroundColor": "#f0fdf4",
                "color": "#16a34a"
            }
        ]
        
        tci_table = dash_table.DataTable(
            data=tci_data,
            columns=columns,
            style_table={
                "borderRadius": "8px",
                "overflow": "hidden",
                "border": "1px solid #e5e7eb"
            },
            style_header={
                "backgroundColor": "#f9fafb",
                "color": "#374151",
                "fontWeight": "600",
                "textAlign": "center",
                "border": "none"
            },
            style_cell={
                "textAlign": "center",
                "padding": "8px 4px",
                "border": "1px solid #f3f4f6",
                "fontSize": "12px"
            },
            style_data_conditional=style_data_conditional,
            style_data={
                "backgroundColor": "white",
                "color": "#374151"
            },
            page_action="none",
            style_as_list_view=True
        )
        
        return tci_table
        
    except Exception as e:
        print(f"TCI 테이블 업데이트 오류: {e}")
        return html.Div(f"오류: {str(e)}") 