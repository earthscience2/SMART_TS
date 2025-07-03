#!/usr/bin/env python3
"""분석 도구 탭 모듈"""

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

from .utils import parse_material_info_from_inp

def create_analysis_tab_layout():
    """분석 도구 탭 레이아웃을 생성합니다."""
    return html.Div([
        # 분석 컨트롤 섹션
        html.Div([
            html.H6("🔧 분석 설정", style={
                "fontWeight": "600",
                "color": "#374151",
                "marginBottom": "16px",
                "fontSize": "14px"
            }),
            dbc.Row([
                dbc.Col([
                    dbc.Label("분석 필드", style={"fontWeight": "500", "color": "#374151"}),
                    dcc.Dropdown(
                        id="analysis-field-dropdown",
                        options=[
                            {"label": "온도", "value": "temperature"},
                            {"label": "응력", "value": "stress"},
                            {"label": "변형", "value": "strain"}
                        ],
                        value="temperature",
                        style={"borderRadius": "6px", "border": "1px solid #d1d5db"}
                    )
                ], md=4),
                dbc.Col([
                    dbc.Label("색상 팔레트", style={"fontWeight": "500", "color": "#374151"}),
                    dcc.Dropdown(
                        id="analysis-preset-dropdown",
                        options=[
                            {"label": "무지개", "value": "rainbow"},
                            {"label": "파란색", "value": "blues"},
                            {"label": "빨간색", "value": "reds"},
                            {"label": "녹색", "value": "greens"}
                        ],
                        value="rainbow",
                        style={"borderRadius": "6px", "border": "1px solid #d1d5db"}
                    )
                ], md=4),
                dbc.Col([
                    dbc.Label("시간", style={"fontWeight": "500", "color": "#374151"}),
                    dcc.Slider(
                        id="analysis-time-slider",
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
        
        # 슬라이스 컨트롤 섹션
        html.Div([
            html.H6("✂️ 슬라이스 설정", style={
                "fontWeight": "600",
                "color": "#374151",
                "marginBottom": "16px",
                "fontSize": "14px"
            }),
            dbc.Row([
                dbc.Col([
                    dbc.Checklist(
                        id="slice-enable",
                        options=[{"label": "슬라이스 활성화", "value": "enabled"}],
                        value=[],
                        style={"marginBottom": "12px"}
                    )
                ], md=3),
                dbc.Col([
                    dbc.Label("슬라이스 축", style={"fontWeight": "500", "color": "#374151"}),
                    dcc.Dropdown(
                        id="slice-axis",
                        options=[
                            {"label": "X축", "value": "X"},
                            {"label": "Y축", "value": "Y"},
                            {"label": "Z축", "value": "Z"}
                        ],
                        value="Z",
                        style={"borderRadius": "6px", "border": "1px solid #d1d5db"}
                    )
                ], md=3),
                dbc.Col([
                    dbc.Label("슬라이스 위치", style={"fontWeight": "500", "color": "#374151"}),
                    dcc.Slider(
                        id="slice-slider",
                        min=0,
                        max=1,
                        step=0.01,
                        value=0.5,
                        marks={},
                        tooltip={"placement": "bottom", "always_visible": True},
                    )
                ], md=6),
            ])
        ], style={
            "padding": "16px 20px",
            "backgroundColor": "#f9fafb",
            "borderRadius": "8px",
            "border": "1px solid #e5e7eb",
            "marginBottom": "16px"
        }),
        
        # 현재 파일 정보
        html.Div([
            html.H6("📄 현재 파일", style={
                "fontWeight": "600",
                "color": "#374151",
                "marginBottom": "8px"
            }),
            html.Div(
                id="analysis-current-file-label",
                style={
                    "color": "#6b7280",
                    "fontSize": "14px"
                }
            )
        ], style={
            "padding": "16px 20px",
            "backgroundColor": "#f8fafc",
            "borderRadius": "8px",
            "border": "1px solid #e2e8f0",
            "marginBottom": "16px"
        }),
        
        # 3D 분석 뷰어
        html.Div([
            html.Div(
                id="analysis-3d-viewer",
                style={
                    "height": "600px",
                    "borderRadius": "8px",
                    "border": "1px solid #e5e7eb",
                    "backgroundColor": "white"
                }
            )
        ], style={
            "backgroundColor": "white",
            "borderRadius": "8px",
            "padding": "16px"
        }),
    ])

# 콜백 함수들
@callback(
    Output("analysis-3d-viewer", "children"),
    Output("analysis-current-file-label", "children"),
    Output("slice-slider", "min"),
    Output("slice-slider", "max"),
    Input("analysis-field-dropdown", "value"),
    Input("analysis-preset-dropdown", "value"),
    Input("analysis-time-slider", "value"),
    Input("slice-enable", "value"),
    Input("slice-axis", "value"),
    Input("slice-slider", "value"),
    State("tbl-concrete", "selected_rows"),
    State("tbl-concrete", "data"),
    prevent_initial_call=False,
)
def update_analysis_3d_view(field_name, preset, time_idx, slice_enable, slice_axis, slice_slider, selected_rows, tbl_data):
    """분석 3D 뷰를 업데이트합니다."""
    if not selected_rows or not tbl_data:
        return html.Div([
            html.H4("분석 뷰어", style={"textAlign": "center", "color": "#6b7280"}),
            html.P("콘크리트를 선택하세요", style={"textAlign": "center", "color": "#9ca3af"})
        ]), "파일을 선택하세요", 0, 1
    
    try:
        row = pd.DataFrame(tbl_data).iloc[selected_rows[0]]
        concrete_pk = row["concrete_pk"]
        concrete_name = row["name"]
        
        # INP 파일들 로드
        inp_dir = f"inp/{concrete_pk}"
        inp_files = sorted(glob.glob(f"{inp_dir}/*.inp"))
        
        if not inp_files:
            return html.Div([
                html.H4("분석 뷰어", style={"textAlign": "center", "color": "#6b7280"}),
                html.P("분석 데이터가 없습니다", style={"textAlign": "center", "color": "#9ca3af"})
            ]), "분석 데이터 없음", 0, 1
        
        # 현재 시간에 해당하는 파일 선택
        file_idx = min(time_idx if time_idx is not None else len(inp_files)-1, len(inp_files)-1)
        current_file = inp_files[file_idx]
        
        # 파일명에서 시간 정보 추출
        time_str = os.path.basename(current_file).split(".")[0]
        try:
            dt = datetime.strptime(time_str, "%Y%m%d%H")
            formatted_time = dt.strftime("%Y년 %m월 %d일 %H시")
        except:
            formatted_time = time_str
        
        # 파일 내용 읽기
        with open(current_file, 'r') as f:
            lines = f.readlines()
        
        # 물성치 정보 추출
        material_info = parse_material_info_from_inp(lines)
        
        # 3D 뷰어 생성 (간단한 예시)
        fig = go.Figure()
        
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
        
        if temps:
            # 간단한 3D 산점도 생성
            x_coords = np.random.uniform(0, 10, len(temps))
            y_coords = np.random.uniform(0, 10, len(temps))
            z_coords = np.random.uniform(0, 5, len(temps))
            
            fig.add_trace(go.Scatter3d(
                x=x_coords,
                y=y_coords,
                z=z_coords,
                mode='markers',
                marker=dict(
                    size=6,
                    color=temps,
                    colorscale=preset,
                    opacity=0.8,
                    colorbar=dict(title=f"{field_name} 값")
                ),
                text=[f"온도: {t:.1f}°C" for t in temps],
                hovertemplate='%{text}<extra></extra>'
            ))
        
        fig.update_layout(
            scene=dict(
                xaxis=dict(title="X"),
                yaxis=dict(title="Y"),
                zaxis=dict(title="Z"),
            ),
            title=f"{concrete_name} - {field_name} 분석 ({formatted_time})",
            showlegend=False
        )
        
        # 슬라이스 정보
        slice_info = ""
        if slice_enable and "enabled" in slice_enable:
            slice_info = f" | 슬라이스: {slice_axis}축 {slice_slider:.2f}"
        
        current_file_info = f"{formatted_time} | {material_info}{slice_info}"
        
        return dcc.Graph(
            figure=fig,
            style={"height": "100%"},
            config={
                'displayModeBar': True,
                'displaylogo': False,
                'modeBarButtonsToRemove': ['pan2d', 'lasso2d', 'select2d'],
                'toImageButtonOptions': {
                    'format': 'png',
                    'filename': f'analysis_{field_name}',
                    'height': 600,
                    'width': 800,
                    'scale': 2
                }
            }
        ), current_file_info, 0, 1
        
    except Exception as e:
        print(f"분석 뷰어 오류: {e}")
        return html.Div([
            html.H4("분석 뷰어", style={"textAlign": "center", "color": "#6b7280"}),
            html.P("데이터 로딩 오류", style={"textAlign": "center", "color": "#9ca3af"})
        ]), "오류 발생", 0, 1

@callback(
    Output("slice-slider", "style"),
    Input("slice-enable", "value"),
    prevent_initial_call=True,
)
def toggle_slice_detail_controls(slice_enable):
    """슬라이스 상세 컨트롤을 토글합니다."""
    if slice_enable and "enabled" in slice_enable:
        return {"display": "block"}
    else:
        return {"display": "none"}

def create_analysis_tab_content(selected_rows, tbl_data):
    """분석 도구 탭 콘텐츠를 생성합니다."""
    return html.Div([
        html.H6("🔧 분석 도구", style={
            "fontWeight": "600",
            "color": "#374151",
            "marginBottom": "16px",
            "fontSize": "16px"
        }),
        html.Div([
            html.I(className="fas fa-info-circle fa-2x", style={"color": "#64748b", "marginBottom": "16px"}),
            html.H5("분석 도구 기능이 준비 중입니다.", style={
                "color": "#475569",
                "fontWeight": "500",
                "lineHeight": "1.6",
                "margin": "0"
            })
        ], style={
            "textAlign": "center",
            "padding": "60px 40px",
            "backgroundColor": "#f8fafc",
            "borderRadius": "12px",
            "border": "1px solid #e2e8f0",
            "marginTop": "60px"
        })
    ]) 