#!/usr/bin/env python3
# pages/tci_analysis.py
"""TCI (Temperature Cracking Index) 분석 페이지

온도 균열 지수 분석 및 시각화 기능을 제공합니다.
"""

import os
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from dash import (
    html, dcc, Input, Output, State,
    dash_table, register_page, callback
)
import dash_bootstrap_components as dbc
from dash.exceptions import PreventUpdate
import api_db

register_page(__name__, path="/tci-analysis")

# 레이아웃
layout = dbc.Container(
    fluid=True,
    className="px-4 py-3",
    style={"backgroundColor": "#f7f9fc", "minHeight": "100vh"},
    children=[
        dcc.Location(id="tci-url", refresh=False),
        
        # 알림
        dbc.Alert(
            id="tci-alert",
            is_open=False,
            duration=3000,
            color="danger",
            style={"borderRadius": "8px", "border": "none"}
        ),
        
        # 메인 콘텐츠
        html.Div([
            # 헤더
            html.Div([
                html.H4("⚠️ TCI (Temperature Cracking Index) 분석", style={
                    "fontWeight": "600",
                    "color": "#1f2937",
                    "marginBottom": "8px"
                }),
                html.P("온도 균열 지수를 통한 콘크리트 균열 위험도 평가", style={
                    "color": "#6b7280",
                    "fontSize": "16px",
                    "margin": "0"
                })
            ], style={
                "padding": "24px",
                "backgroundColor": "white",
                "borderRadius": "12px",
                "boxShadow": "0 1px 3px rgba(0,0,0,0.1)",
                "border": "1px solid #e2e8f0",
                "marginBottom": "24px"
            }),
            
            # 콘크리트 선택 섹션
            html.Div([
                html.H6("🏗️ 콘크리트 선택", style={
                    "fontWeight": "600",
                    "color": "#374151",
                    "marginBottom": "16px",
                    "fontSize": "16px"
                }),
                dcc.Dropdown(
                    id="tci-concrete-dropdown",
                    placeholder="분석할 콘크리트를 선택하세요",
                    style={"fontSize": "14px"}
                ),
            ], style={
                "padding": "20px",
                "backgroundColor": "white",
                "borderRadius": "12px",
                "border": "1px solid #e5e7eb",
                "boxShadow": "0 1px 3px rgba(0,0,0,0.1)",
                "marginBottom": "24px"
            }),
            
            # TCI 분석 결과 섹션
            html.Div(id="tci-results-container", style={"display": "none"})
        ])
    ]
)

# 콘크리트 목록 로드 콜백
@callback(
    Output("tci-concrete-dropdown", "options"),
    Output("tci-concrete-dropdown", "value"),
    Input("tci-url", "search"),
    prevent_initial_call=False,
)
def load_concrete_options(search):
    """URL에서 프로젝트 정보를 추출하고 해당 프로젝트의 콘크리트 목록을 로드합니다."""
    from urllib.parse import parse_qs
    
    project_pk = None
    if search:
        try:
            qs = parse_qs(search.lstrip('?'))
            project_pk = qs.get('page', [None])[0]
        except Exception:
            pass
    
    if not project_pk:
        return [], None
    
    try:
        # 해당 프로젝트의 콘크리트 데이터 로드
        df_conc = api_db.get_concrete_data(project_pk=project_pk)
        if df_conc.empty:
            return [], None
        
        # 드롭다운 옵션 생성
        options = []
        for _, row in df_conc.iterrows():
            options.append({
                "label": f"{row['name']} (ID: {row['concrete_pk']})",
                "value": row['concrete_pk']
            })
        
        return options, None
        
    except Exception as e:
        print(f"콘크리트 목록 로딩 오류: {e}")
        return [], None

# TCI 분석 결과 표시 콜백
@callback(
    Output("tci-results-container", "children"),
    Output("tci-results-container", "style"),
    Input("tci-concrete-dropdown", "value"),
    prevent_initial_call=True,
)
def display_tci_results(concrete_pk):
    """선택된 콘크리트의 TCI 분석 결과를 표시합니다."""
    if not concrete_pk:
        return [], {"display": "none"}
    
    # TCI 관련 파일 경로 확인
    tci_html_path = f"source/tci_heatmap_risk_only.html"
    tci_csv_path = f"source/tci_node_summary_fixed.csv"
    
    # TCI 파일 존재 여부 확인
    tci_files_exist = os.path.exists(tci_html_path) and os.path.exists(tci_csv_path)
    
    if not tci_files_exist:
        return html.Div([
            html.Div([
                html.I(className="fas fa-exclamation-triangle fa-2x", style={"color": "#f59e0b", "marginBottom": "16px"}),
                html.H5("TCI 분석 파일이 없습니다", style={
                    "color": "#374151",
                    "fontWeight": "500",
                    "lineHeight": "1.6",
                    "margin": "0"
                }),
                html.P("TCI 분석을 실행하려면 먼저 수치해석을 완료해야 합니다.", style={
                    "color": "#6b7280",
                    "fontSize": "14px",
                    "marginTop": "8px"
                })
            ], style={
                "textAlign": "center",
                "padding": "60px 40px",
                "backgroundColor": "#f8fafc",
                "borderRadius": "12px",
                "border": "1px solid #e2e8f0"
            })
        ]), {"display": "block"}
    
    # TCI CSV 데이터 로드
    try:
        df_tci = pd.read_csv(tci_csv_path)
        
        # 위험도별 색상 매핑
        def get_risk_color(risk_level):
            if risk_level == "높음":
                return "#dc2626"
            elif risk_level == "보통":
                return "#d97706"
            else:
                return "#059669"
        
        # 테이블 스타일 설정
        style_data_conditional = [
            {
                'if': {'filter_query': '{위험도} = "높음"'},
                'backgroundColor': '#fef2f2',
                'color': '#dc2626',
                'fontWeight': 'bold'
            },
            {
                'if': {'filter_query': '{위험도} = "보통"'},
                'backgroundColor': '#fffbeb',
                'color': '#d97706',
                'fontWeight': 'bold'
            },
            {
                'if': {'filter_query': '{위험도} = "낮음"'},
                'backgroundColor': '#f0fdf4',
                'color': '#059669',
                'fontWeight': 'bold'
            }
        ]
        
        return html.Div([
            # TCI 분석 개요
            html.Div([
                html.Div([
                    html.H6("📊 TCI (Temperature Cracking Index) 분석 결과", style={
                        "fontWeight": "600",
                        "color": "#374151",
                        "marginBottom": "12px",
                        "fontSize": "16px"
                    }),
                    html.P("온도 균열 지수(TCI)는 콘크리트의 온도 응력과 인장 강도를 고려하여 균열 발생 위험도를 평가하는 지표입니다.", style={
                        "color": "#6b7280",
                        "fontSize": "14px",
                        "lineHeight": "1.6",
                        "margin": "0"
                    }),
                    html.Div([
                        html.Span("🔴 높음", style={"color": "#dc2626", "fontWeight": "500", "marginRight": "16px"}),
                        html.Span("🟡 보통", style={"color": "#d97706", "fontWeight": "500", "marginRight": "16px"}),
                        html.Span("🟢 낮음", style={"color": "#059669", "fontWeight": "500"})
                    ], style={"marginTop": "12px"})
                ], style={
                    "padding": "20px",
                    "backgroundColor": "white",
                    "borderRadius": "12px",
                    "border": "1px solid #e5e7eb",
                    "boxShadow": "0 1px 3px rgba(0,0,0,0.1)",
                    "marginBottom": "20px"
                })
            ]),
            
            # TCI 히트맵 뷰어
            html.Div([
                html.Div([
                    html.H6("🌡️ TCI 히트맵", style={
                        "fontWeight": "600",
                        "color": "#374151",
                        "marginBottom": "16px",
                        "fontSize": "16px"
                    }),
                    html.Iframe(
                        src=f"/assets/{tci_html_path}",
                        style={
                            "width": "100%",
                            "height": "60vh",
                            "border": "none",
                            "borderRadius": "8px"
                        }
                    ),
                ], style={
                    "padding": "20px",
                    "backgroundColor": "white",
                    "borderRadius": "12px",
                    "border": "1px solid #e5e7eb",
                    "boxShadow": "0 1px 3px rgba(0,0,0,0.1)",
                    "marginBottom": "20px"
                })
            ]),
            
            # TCI 노드별 요약 테이블
            html.Div([
                html.Div([
                    html.H6("📋 TCI 노드별 요약", style={
                        "fontWeight": "600",
                        "color": "#374151",
                        "marginBottom": "16px",
                        "fontSize": "16px"
                    }),
                    dash_table.DataTable(
                        id="tci-summary-table",
                        data=df_tci.to_dict('records'),
                        columns=[{"name": col, "id": col} for col in df_tci.columns],
                        page_size=10,
                        sort_action="native",
                        sort_mode="single",
                        style_table={
                            "overflowY": "auto", 
                            "maxHeight": "400px",
                            "borderRadius": "8px",
                            "border": "1px solid #e2e8f0"
                        },
                        style_cell={
                            "whiteSpace": "nowrap", 
                            "textAlign": "center",
                            "padding": "12px 8px",
                            "fontSize": "13px",
                            "fontFamily": "-apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui",
                            "border": "1px solid #f1f5f9"
                        },
                        style_header={
                            "backgroundColor": "#f8fafc", 
                            "fontWeight": "600",
                            "color": "#475569",
                            "border": "1px solid #e2e8f0",
                            "textAlign": "center"
                        },
                        style_data_conditional=style_data_conditional
                    ),
                ], style={
                    "padding": "20px",
                    "backgroundColor": "white",
                    "borderRadius": "12px",
                    "border": "1px solid #e5e7eb",
                    "boxShadow": "0 1px 3px rgba(0,0,0,0.1)"
                })
            ]),
        ]), {"display": "block"}
        
    except Exception as e:
        print(f"TCI 데이터 로딩 오류: {e}")
        return html.Div([
            html.Div([
                html.I(className="fas fa-exclamation-triangle fa-2x", style={"color": "#dc2626", "marginBottom": "16px"}),
                html.H5("TCI 데이터 로딩 실패", style={
                    "color": "#374151",
                    "fontWeight": "500",
                    "lineHeight": "1.6",
                    "margin": "0"
                }),
                html.P(f"오류: {str(e)}", style={
                    "color": "#6b7280",
                    "fontSize": "14px",
                    "marginTop": "8px"
                })
            ], style={
                "textAlign": "center",
                "padding": "60px 40px",
                "backgroundColor": "#f8fafc",
                "borderRadius": "12px",
                "border": "1px solid #e2e8f0"
            })
        ]), {"display": "block"} 