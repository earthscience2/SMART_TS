#!/usr/bin/env python3
"""단면도 뷰어 탭 모듈"""

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

def create_section_tab_layout():
    """단면도 탭 레이아웃을 생성합니다."""
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
                    id="time-slider-section",
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
        
        # 현재 시간 정보 + 저장 옵션
        dbc.Row([
            # 왼쪽: 현재 시간/물성치 정보
            dbc.Col([
                html.Div(
                    id="section-time-info", 
                    style={
                        "minHeight": "65px !important",
                        "height": "65px",
                        "display": "flex",
                        "flexDirection": "column",
                        "justifyContent": "flex-start"
                    }
                )
            ], md=8, style={"height": "65px"}),
            
            # 오른쪽: 저장 버튼들
            dbc.Col([
                html.Div([
                    dbc.Button(
                        [html.I(className="fas fa-camera me-1"), "이미지 저장"],
                        id="btn-save-section-image",
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
                        id="btn-save-section-inp",
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
            ], md=4, style={"height": "65px"}),
        ]),
        
        # 단면도 뷰어들
        dbc.Row([
            # 3D 단면도
            dbc.Col([
                html.Div([
                    dcc.Graph(
                        id="viewer-3d-section",
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
                                'filename': 'section_3d',
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
            
            # X축 단면도
            dbc.Col([
                html.Div([
                    dcc.Graph(
                        id="viewer-section-x",
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
                                'filename': 'section_x',
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
        ]),
        
        dbc.Row([
            # Y축 단면도
            dbc.Col([
                html.Div([
                    dcc.Graph(
                        id="viewer-section-y",
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
                                'filename': 'section_y',
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
            
            # Z축 단면도
            dbc.Col([
                html.Div([
                    dcc.Graph(
                        id="viewer-section-z",
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
                                'filename': 'section_z',
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
        ]),
        
        # 다운로드 컴포넌트들
        dcc.Download(id="download-section-image"),
        dcc.Download(id="download-section-inp"),
    ])

# 콜백 함수들
@callback(
    Output("section-time-info", "children"),
    Input("current-file-title-store", "data"),
    Input("tabs-main", "active_tab"),
    prevent_initial_call=True,
)
def update_section_time_info(current_file_title, active_tab):
    """단면도 시간 정보를 업데이트합니다."""
    if active_tab != "tab-section":
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
    Output("download-section-image", "data"),
    Output("btn-save-section-image", "children"),
    Output("btn-save-section-image", "disabled"),
    Input("btn-save-section-image", "n_clicks"),
    State("viewer-3d-section", "figure"),
    State("viewer-section-x", "figure"),
    State("viewer-section-y", "figure"),
    State("viewer-section-z", "figure"),
    State("tbl-concrete", "selected_rows"),
    State("tbl-concrete", "data"),
    State("time-slider-section", "value"),
    prevent_initial_call=True,
)
def save_section_image(n_clicks, fig_3d, fig_x, fig_y, fig_z, selected_rows, tbl_data, time_value):
    """단면도 이미지를 저장합니다."""
    if not n_clicks or not selected_rows or not tbl_data:
        return None, [html.I(className="fas fa-camera me-1"), "이미지 저장"], True
    
    try:
        # 파일명 생성
        row = pd.DataFrame(tbl_data).iloc[selected_rows[0]]
        concrete_name = row["name"]
        filename = f"{concrete_name}_section_views_t{time_value}.png"
        
        # 이미지 데이터 반환 (여기서는 3D 뷰만 저장)
        if fig_3d:
            return dcc.send_bytes(
                fig_3d.to_image(format="png", width=1200, height=800, scale=2),
                filename
            ), [html.I(className="fas fa-check me-1"), "저장됨"], False
        else:
            return None, [html.I(className="fas fa-exclamation-triangle me-1"), "오류"], False
        
    except Exception as e:
        print(f"단면도 이미지 저장 오류: {e}")
        return None, [html.I(className="fas fa-exclamation-triangle me-1"), "오류"], False

@callback(
    Output("download-section-inp", "data"),
    Input("btn-save-section-inp", "n_clicks"),
    State("tbl-concrete", "selected_rows"),
    State("tbl-concrete", "data"),
    State("time-slider-section", "value"),
    prevent_initial_call=True,
)
def save_section_inp(n_clicks, selected_rows, tbl_data, time_value):
    """단면도 INP 파일을 저장합니다."""
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
        filename = f"{concrete_name}_section_{time_str}.inp"
        
        return dcc.send_bytes(content.encode('utf-8'), filename)
        
    except Exception as e:
        print(f"단면도 INP 파일 저장 오류: {e}")
        return None 