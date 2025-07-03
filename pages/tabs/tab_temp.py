#!/usr/bin/env python3
"""온도 분석 탭 모듈"""

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

def create_temp_tab_layout():
    """온도 분석 탭 레이아웃을 생성합니다."""
    return html.Div([
        # 좌표 입력 섹션
        html.Div([
            html.H6("📍 좌표 설정", style={
                "fontWeight": "600",
                "color": "#374151",
                "marginBottom": "12px",
                "fontSize": "14px"
            }),
            dbc.Row([
                dbc.Col([
                    dbc.Label("X 좌표", style={"fontWeight": "500", "color": "#374151"}),
                    dbc.Input(
                        id="temp-x-input",
                        type="number",
                        value=0,
                        style={"borderRadius": "6px", "border": "1px solid #d1d5db"}
                    )
                ], md=4),
                dbc.Col([
                    dbc.Label("Y 좌표", style={"fontWeight": "500", "color": "#374151"}),
                    dbc.Input(
                        id="temp-y-input",
                        type="number",
                        value=0,
                        style={"borderRadius": "6px", "border": "1px solid #d1d5db"}
                    )
                ], md=4),
                dbc.Col([
                    dbc.Label("Z 좌표", style={"fontWeight": "500", "color": "#374151"}),
                    dbc.Input(
                        id="temp-z-input",
                        type="number",
                        value=0,
                        style={"borderRadius": "6px", "border": "1px solid #d1d5db"}
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
        
        # 저장 옵션
        dbc.Row([
            dbc.Col([
                html.Div([
                    dbc.Button(
                        [html.I(className="fas fa-camera me-1"), "이미지 저장"],
                        id="btn-save-temp-image",
                        color="primary",
                        size="lg",
                        style={
                            "borderRadius": "8px",
                            "fontWeight": "600",
                            "boxShadow": "0 1px 2px rgba(0,0,0,0.1)",
                            "fontSize": "15px",
                            "marginRight": "8px"
                        }
                    ),
                    dbc.Button(
                        [html.I(className="fas fa-download me-1"), "데이터 저장"],
                        id="btn-save-temp-data",
                        color="secondary",
                        size="lg",
                        style={
                            "borderRadius": "8px",
                            "fontWeight": "600",
                            "boxShadow": "0 1px 2px rgba(0,0,0,0.1)",
                            "fontSize": "15px"
                        }
                    ),
                ], style={
                    "display": "flex",
                    "justifyContent": "flex-end",
                    "alignItems": "center"
                })
            ], md=12)
        ], style={"marginBottom": "16px"}),
        
        # 온도 분석 뷰어들
        dbc.Row([
            # 3D 온도 뷰어
            dbc.Col([
                html.Div([
                    dcc.Graph(
                        id="temp-viewer-3d",
                        style={
                            "height": "500px",
                            "borderRadius": "8px",
                            "border": "1px solid #e5e7eb"
                        },
                        config={
                            'displayModeBar': True,
                            'displaylogo': False,
                            'modeBarButtonsToRemove': ['pan2d', 'lasso2d', 'select2d'],
                            'toImageButtonOptions': {
                                'format': 'png',
                                'filename': 'temp_3d',
                                'height': 500,
                                'width': 800,
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
            
            # 시간별 온도 그래프
            dbc.Col([
                html.Div([
                    dcc.Graph(
                        id="temp-time-graph",
                        style={
                            "height": "500px",
                            "borderRadius": "8px",
                            "border": "1px solid #e5e7eb"
                        },
                        config={
                            'displayModeBar': True,
                            'displaylogo': False,
                            'modeBarButtonsToRemove': ['pan2d', 'lasso2d', 'select2d'],
                            'toImageButtonOptions': {
                                'format': 'png',
                                'filename': 'temp_time',
                                'height': 500,
                                'width': 800,
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
        ]),
        
        # 다운로드 컴포넌트들
        dcc.Download(id="download-temp-image"),
        dcc.Download(id="download-temp-data"),
    ])

def create_temp_tab_content(selected_rows, tbl_data):
    """온도 분석 탭 콘텐츠를 생성합니다."""
    return html.Div([
        html.H6("🌡️ 온도 분석", style={
            "fontWeight": "600",
            "color": "#374151",
            "marginBottom": "16px",
            "fontSize": "16px"
        }),
        html.Div([
            html.I(className="fas fa-info-circle fa-2x", style={"color": "#64748b", "marginBottom": "16px"}),
            html.H5("온도 분석 기능이 준비 중입니다.", style={
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

# 콜백 함수들
@callback(
    Output("temp-viewer-3d", "figure"),
    Output("temp-time-graph", "figure"),
    Input("temp-coord-store", "data"),
    Input("temp-x-input", "value"),
    Input("temp-y-input", "value"),
    Input("temp-z-input", "value"),
    State("tbl-concrete", "selected_rows"),
    State("tbl-concrete", "data"),
    prevent_initial_call=False,
)
def update_temp_tab(store_data, x, y, z, selected_rows, tbl_data):
    """온도 분석 탭을 업데이트합니다."""
    if not selected_rows or not tbl_data:
        # 기본 빈 그래프들
        fig_3d = go.Figure()
        fig_3d.update_layout(
            scene=dict(
                xaxis=dict(title="X"),
                yaxis=dict(title="Y"),
                zaxis=dict(title="Z"),
            ),
            title="콘크리트를 선택하고 좌표를 설정하세요"
        )
        
        fig_time = go.Figure()
        fig_time.update_layout(
            xaxis=dict(title="시간"),
            yaxis=dict(title="온도 (°C)"),
            title="시간별 온도 변화"
        )
        
        return fig_3d, fig_time
    
    try:
        row = pd.DataFrame(tbl_data).iloc[selected_rows[0]]
        concrete_pk = row["concrete_pk"]
        
        # INP 파일들 로드
        inp_dir = f"inp/{concrete_pk}"
        inp_files = sorted(glob.glob(f"{inp_dir}/*.inp"))
        
        if not inp_files:
            # 데이터가 없는 경우 기본 그래프
            fig_3d = go.Figure()
            fig_3d.update_layout(
                scene=dict(
                    xaxis=dict(title="X"),
                    yaxis=dict(title="Y"),
                    zaxis=dict(title="Z"),
                ),
                title="분석 데이터가 없습니다"
            )
            
            fig_time = go.Figure()
            fig_time.update_layout(
                xaxis=dict(title="시간"),
                yaxis=dict(title="온도 (°C)"),
                title="시간별 온도 변화"
            )
            
            return fig_3d, fig_time
        
        # 온도 데이터 파싱 및 시각화
        temps_over_time = []
        time_labels = []
        
        for i, inp_file in enumerate(inp_files):
            with open(inp_file, 'r') as f:
                lines = f.readlines()
            
            # 온도 데이터 추출
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
                temps_over_time.append(temps)
                time_labels.append(f"T{i}")
        
        # 3D 뷰어 생성 (간단한 예시)
        fig_3d = go.Figure()
        if temps_over_time:
            latest_temps = temps_over_time[-1]
            fig_3d.add_trace(go.Scatter3d(
                x=[x] * len(latest_temps),
                y=[y] * len(latest_temps),
                z=[z] * len(latest_temps),
                mode='markers',
                marker=dict(
                    size=8,
                    color=latest_temps,
                    colorscale='Viridis',
                    opacity=0.8
                ),
                text=[f"온도: {t:.1f}°C" for t in latest_temps],
                hovertemplate='%{text}<extra></extra>'
            ))
        
        fig_3d.update_layout(
            scene=dict(
                xaxis=dict(title="X"),
                yaxis=dict(title="Y"),
                zaxis=dict(title="Z"),
            ),
            title=f"좌표 ({x}, {y}, {z}) 주변 온도 분포"
        )
        
        # 시간별 온도 그래프 생성
        fig_time = go.Figure()
        if temps_over_time and len(temps_over_time) > 1:
            # 평균 온도 계산
            avg_temps = [np.mean(temps) if temps else 0 for temps in temps_over_time]
            
            fig_time.add_trace(go.Scatter(
                x=time_labels,
                y=avg_temps,
                mode='lines+markers',
                name='평균 온도',
                line=dict(color='#3b82f6', width=3),
                marker=dict(size=8)
            ))
        
        fig_time.update_layout(
            xaxis=dict(title="시간"),
            yaxis=dict(title="온도 (°C)"),
            title="시간별 온도 변화",
            plot_bgcolor='white',
            paper_bgcolor='white'
        )
        
        return fig_3d, fig_time
        
    except Exception as e:
        print(f"온도 분석 오류: {e}")
        # 오류 시 기본 그래프
        fig_3d = go.Figure()
        fig_3d.update_layout(
            scene=dict(
                xaxis=dict(title="X"),
                yaxis=dict(title="Y"),
                zaxis=dict(title="Z"),
            ),
            title="데이터 로딩 오류"
        )
        
        fig_time = go.Figure()
        fig_time.update_layout(
            xaxis=dict(title="시간"),
            yaxis=dict(title="온도 (°C)"),
            title="시간별 온도 변화"
        )
        
        return fig_3d, fig_time

@callback(
    Output("download-temp-image", "data"),
    Output("btn-save-temp-image", "children"),
    Output("btn-save-temp-image", "disabled"),
    Input("btn-save-temp-image", "n_clicks"),
    State("temp-viewer-3d", "figure"),
    State("temp-time-graph", "figure"),
    State("tbl-concrete", "selected_rows"),
    State("tbl-concrete", "data"),
    State("temp-x-input", "value"),
    State("temp-y-input", "value"),
    State("temp-z-input", "value"),
    prevent_initial_call=True,
)
def save_temp_image(n_clicks, fig_3d, fig_time, selected_rows, tbl_data, x, y, z):
    """온도 분석 이미지를 저장합니다."""
    if not n_clicks or not selected_rows or not tbl_data:
        return None, [html.I(className="fas fa-camera me-1"), "이미지 저장"], True
    
    try:
        # 파일명 생성
        row = pd.DataFrame(tbl_data).iloc[selected_rows[0]]
        concrete_name = row["name"]
        filename = f"{concrete_name}_temp_analysis_{x}_{y}_{z}.png"
        
        # 이미지 데이터 반환 (3D 뷰만 저장)
        if fig_3d:
            return dcc.send_bytes(
                fig_3d.to_image(format="png", width=1200, height=800, scale=2),
                filename
            ), [html.I(className="fas fa-check me-1"), "저장됨"], False
        else:
            return None, [html.I(className="fas fa-exclamation-triangle me-1"), "오류"], False
        
    except Exception as e:
        print(f"온도 분석 이미지 저장 오류: {e}")
        return None, [html.I(className="fas fa-exclamation-triangle me-1"), "오류"], False

@callback(
    Output("download-temp-data", "data"),
    Input("btn-save-temp-data", "n_clicks"),
    State("tbl-concrete", "selected_rows"),
    State("tbl-concrete", "data"),
    State("temp-x-input", "value"),
    State("temp-y-input", "value"),
    State("temp-z-input", "value"),
    prevent_initial_call=True,
)
def save_temp_data(n_clicks, selected_rows, tbl_data, x, y, z):
    """온도 분석 데이터를 저장합니다."""
    if not n_clicks or not selected_rows or not tbl_data:
        return None
    
    try:
        row = pd.DataFrame(tbl_data).iloc[selected_rows[0]]
        concrete_pk = row["concrete_pk"]
        concrete_name = row["name"]
        
        # INP 파일들 로드
        inp_dir = f"inp/{concrete_pk}"
        inp_files = sorted(glob.glob(f"{inp_dir}/*.inp"))
        
        if not inp_files:
            return None
        
        # 온도 데이터 수집
        data_rows = []
        for i, inp_file in enumerate(inp_files):
            with open(inp_file, 'r') as f:
                lines = f.readlines()
            
            # 온도 데이터 추출
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
                data_rows.append({
                    "시간": f"T{i}",
                    "최저온도": min(temps),
                    "최고온도": max(temps),
                    "평균온도": np.mean(temps),
                    "표준편차": np.std(temps)
                })
        
        # CSV 데이터 생성
        if data_rows:
            df = pd.DataFrame(data_rows)
            csv_content = df.to_csv(index=False, encoding='utf-8-sig')
            
            filename = f"{concrete_name}_temp_data_{x}_{y}_{z}.csv"
            return dcc.send_bytes(csv_content.encode('utf-8-sig'), filename)
        
        return None
        
    except Exception as e:
        print(f"온도 데이터 저장 오류: {e}")
        return None 