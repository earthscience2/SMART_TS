#!/usr/bin/env python3
"""3D 히트맵 뷰어 탭 모듈"""

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

def create_3d_tab_layout():
    """3D 탭 레이아웃을 생성합니다."""
    return html.Div([
        # 시간 컨트롤 섹션 (노션 스타일)
        html.Div([
            html.Div([
                html.H6("⏰ 시간 설정", style={
                    "fontWeight": "600",
                    "color": "#374151",
                    "marginBottom": "12px",
                    "fontSize": "14px"
                }),
                dcc.Slider(
                    id="time-slider-display",
                    min=0,
                    max=5,
                    step=1,
                    value=0,
                    marks={},
                    tooltip={"placement": "bottom", "always_visible": True},
                ),
            ], style={
                "padding": "16px 20px",
                "backgroundColor": "#f9fafb",
                "borderRadius": "8px",
                "border": "1px solid #e5e7eb",
                "marginBottom": "16px"
            })
        ]),
        
        # 현재 시간 정보 + 저장 옵션 (한 줄 배치)
        dbc.Row([
            # 왼쪽: 현재 시간/물성치 정보
            dbc.Col([
                html.Div(
                    id="viewer-3d-time-info", 
                    style={
                        "minHeight": "65px !important",
                        "height": "65px",
                        "display": "flex",
                        "flexDirection": "column",
                        "justifyContent": "flex-start"
                    }
                )
            ], md=8, style={
                "height": "65px"
            }),
            
            # 오른쪽: 저장 버튼들
            dbc.Col([
                html.Div([
                    dbc.Button(
                        [html.I(className="fas fa-camera me-1"), "이미지 저장"],
                        id="btn-save-3d-image",
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
                        [html.I(className="fas fa-download me-1"), "INP 저장"],
                        id="btn-save-current-inp",
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
                    "alignItems": "center",
                    "height": "100%"
                })
            ], md=4, style={
                "height": "65px"
            }),
        ]),
        
        # 3D 뷰어
        html.Div([
            dcc.Graph(
                id="viewer-3d-display",
                style={
                    "height": "600px",
                    "borderRadius": "8px",
                    "border": "1px solid #e5e7eb"
                },
                config={
                    'displayModeBar': True,
                    'displaylogo': False,
                    'modeBarButtonsToRemove': ['pan2d', 'lasso2d', 'select2d'],
                    'toImageButtonOptions': {
                        'format': 'png',
                        'filename': '3d_heatmap',
                        'height': 600,
                        'width': 800,
                        'scale': 2
                    }
                }
            )
        ], style={
            "marginTop": "16px",
            "backgroundColor": "white",
            "borderRadius": "8px",
            "padding": "16px"
        }),
        
        # 다운로드 컴포넌트들 (숨김)
        dcc.Download(id="download-3d-image"),
        dcc.Download(id="download-current-inp"),
    ])

# 콜백 함수들
@callback(
    Output("viewer-3d-time-info", "children"),
    Input("current-file-title-store", "data"),
    Input("tabs-main", "active_tab"),
    prevent_initial_call=True,
)
def update_viewer3d_time_info(current_file_title, active_tab):
    """3D 뷰어 시간 정보를 업데이트합니다."""
    if active_tab != "tab-3d":
        raise PreventUpdate
    
    if not current_file_title:
        return html.Div([
            html.H6("시간 정보", style={
                "fontWeight": "600",
                "color": "#374151",
                "marginBottom": "8px"
            }),
            html.P("콘크리트를 선택하고 시간을 조절하세요", style={
                "color": "#6b7280",
                "margin": "0",
                "fontSize": "14px"
            })
        ])
    
    return html.Div([
        html.H6("시간 정보", style={
            "fontWeight": "600",
            "color": "#374151",
            "marginBottom": "8px"
        }),
        html.P(current_file_title, style={
            "color": "#374151",
            "margin": "0",
            "fontSize": "14px",
            "lineHeight": "1.5"
        })
    ])

@callback(
    Output("download-3d-image", "data"),
    Output("btn-save-3d-image", "children"),
    Output("btn-save-3d-image", "disabled"),
    Input("btn-save-3d-image", "n_clicks"),
    State("viewer-3d-display", "figure"),
    State("tbl-concrete", "selected_rows"),
    State("tbl-concrete", "data"),
    State("time-slider-display", "value"),
    prevent_initial_call=True,
)
def save_3d_image(n_clicks, figure, selected_rows, tbl_data, time_value):
    """3D 이미지를 저장합니다."""
    if not n_clicks or not figure or not selected_rows or not tbl_data:
        return None, [html.I(className="fas fa-camera me-1"), "이미지 저장"], True
    
    try:
        # 파일명 생성
        row = pd.DataFrame(tbl_data).iloc[selected_rows[0]]
        concrete_name = row["name"]
        filename = f"{concrete_name}_3d_heatmap_t{time_value}.png"
        
        # 이미지 데이터 반환
        return dcc.send_bytes(
            figure.to_image(format="png", width=1200, height=800, scale=2),
            filename
        ), [html.I(className="fas fa-check me-1"), "저장됨"], False
        
    except Exception as e:
        print(f"이미지 저장 오류: {e}")
        return None, [html.I(className="fas fa-exclamation-triangle me-1"), "오류"], False

@callback(
    Output("btn-save-3d-image", "children", allow_duplicate=True),
    Output("btn-save-3d-image", "disabled", allow_duplicate=True),
    Input("tabs-main", "active_tab"),
    Input("tbl-concrete", "selected_rows"),
    prevent_initial_call=True,
)
def reset_image_save_button(active_tab, selected_rows):
    """이미지 저장 버튼을 리셋합니다."""
    return [html.I(className="fas fa-camera me-1"), "이미지 저장"], not selected_rows

@callback(
    Output("download-current-inp", "data"),
    Input("btn-save-current-inp", "n_clicks"),
    State("tbl-concrete", "selected_rows"),
    State("tbl-concrete", "data"),
    State("time-slider-display", "value"),
    prevent_initial_call=True,
)
def save_current_inp(n_clicks, selected_rows, tbl_data, time_value):
    """현재 INP 파일을 저장합니다."""
    if not n_clicks or not selected_rows or not tbl_data:
        return None
    
    try:
        row = pd.DataFrame(tbl_data).iloc[selected_rows[0]]
        concrete_pk = row["concrete_pk"]
        concrete_name = row["name"]
        
        inp_dir = f"inp/{concrete_pk}"
        inp_files = sorted(glob.glob(f"{inp_dir}/*.inp"))
        
        if not inp_files:
            return None
        
        # 현재 시간에 해당하는 파일 선택
        file_idx = min(time_value if time_value is not None else len(inp_files)-1, len(inp_files)-1)
        current_file = inp_files[file_idx]
        
        # 파일 읽기
        with open(current_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 파일명 생성
        time_str = os.path.basename(current_file).split(".")[0]
        filename = f"{concrete_name}_{time_str}.inp"
        
        return dcc.send_bytes(content.encode('utf-8'), filename)
        
    except Exception as e:
        print(f"INP 파일 저장 오류: {e}")
        return None

def create_3d_tab_content(viewer_data, current_file_title, selected_rows, tbl_data):
    """3D 탭 콘텐츠를 생성합니다."""
    # 저장된 3D 뷰 정보가 있으면 복원, 없으면 기본 빈 3D 뷰
    if viewer_data and 'figure' in viewer_data:
        fig_3d = viewer_data['figure']
        slider = viewer_data.get('slider', {})
        slider_min = slider.get('min', 0)
        slider_max = slider.get('max', 5)
        slider_marks = slider.get('marks', {})
        slider_value = slider.get('value', 0)
    else:
        # 기본 빈 3D 뷰
        fig_3d = go.Figure()
        fig_3d.update_layout(
            scene=dict(
                xaxis=dict(title="X"),
                yaxis=dict(title="Y"),
                zaxis=dict(title="Z"),
            ),
            title="콘크리트를 선택하고 시간을 조절하세요"
        )
        slider_min, slider_max, slider_marks, slider_value = 0, 5, {}, 0
    
    return html.Div([
        # 시간 컨트롤 섹션
        html.Div([
            html.Div([
                html.H6("⏰ 시간 설정", style={
                    "fontWeight": "600",
                    "color": "#374151",
                    "marginBottom": "12px",
                    "fontSize": "14px"
                }),
                dcc.Slider(
                    id="time-slider-display",
                    min=slider_min,
                    max=slider_max,
                    step=1,
                    value=slider_value,
                    marks=slider_marks,
                    tooltip={"placement": "bottom", "always_visible": True},
                ),
            ], style={
                "padding": "16px 20px",
                "backgroundColor": "#f9fafb",
                "borderRadius": "8px",
                "border": "1px solid #e5e7eb",
                "marginBottom": "16px"
            })
        ]),
        
        # 3D 뷰어
        html.Div([
            html.Div([
                html.H6("🎯 3D 히트맵 뷰어", style={
                    "fontWeight": "600",
                    "color": "#374151",
                    "marginBottom": "16px",
                    "fontSize": "16px"
                }),
                dcc.Graph(
                    id="viewer-3d-display",
                    style={
                        "height": "65vh", 
                        "borderRadius": "8px",
                        "overflow": "hidden"
                    },
                    config={"scrollZoom": True},
                    figure=fig_3d,
                ),
            ], style={
                "padding": "20px",
                "backgroundColor": "white",
                "borderRadius": "12px",
                "border": "1px solid #e5e7eb",
                "boxShadow": "0 1px 3px rgba(0,0,0,0.1)"
            })
        ]),
    ]) 