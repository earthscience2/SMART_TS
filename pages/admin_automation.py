import dash
from dash import dcc, html, Input, Output, callback
import dash_bootstrap_components as dbc
from flask import request
import plotly.graph_objs as go
from plotly.subplots import make_subplots
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json

dash.register_page(__name__, path="/admin_automation")

def layout():
    """관리자 자동화 페이지 레이아웃"""
    
    return dbc.Container([
        dbc.Row([
            dbc.Col([
                html.H2("🔧 자동화 관리", className="mb-4 text-center"),
                html.Hr(),
            ])
        ]),
        
        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader([
                        html.H4("📋 자동화 작업 현황", className="mb-0")
                    ]),
                    dbc.CardBody([
                        dbc.Row([
                            dbc.Col([
                                dbc.Card([
                                    dbc.CardBody([
                                        html.H3("5", className="text-primary"),
                                        html.P("진행 중", className="text-muted mb-0")
                                    ])
                                ], className="text-center")
                            ], width=3),
                            dbc.Col([
                                dbc.Card([
                                    dbc.CardBody([
                                        html.H3("12", className="text-success"),
                                        html.P("완료", className="text-muted mb-0")
                                    ])
                                ], className="text-center")
                            ], width=3),
                            dbc.Col([
                                dbc.Card([
                                    dbc.CardBody([
                                        html.H3("2", className="text-warning"),
                                        html.P("대기 중", className="text-muted mb-0")
                                    ])
                                ], className="text-center")
                            ], width=3),
                            dbc.Col([
                                dbc.Card([
                                    dbc.CardBody([
                                        html.H3("1", className="text-danger"),
                                        html.P("오류", className="text-muted mb-0")
                                    ])
                                ], className="text-center")
                            ], width=3),
                        ])
                    ])
                ], className="mb-4")
            ])
        ]),
        
        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader([
                        html.H4("⚙️ 자동화 설정", className="mb-0")
                    ]),
                    dbc.CardBody([
                        dbc.Row([
                            dbc.Col([
                                html.Div([
                                    dbc.Label("자동 분석 주기"),
                                    dbc.Select(
                                        id="auto-analysis-interval",
                                        options=[
                                            {"label": "1시간마다", "value": "1h"},
                                            {"label": "6시간마다", "value": "6h"},
                                            {"label": "12시간마다", "value": "12h"},
                                            {"label": "1일마다", "value": "1d"},
                                        ],
                                        value="6h"
                                    )
                                ], className="mb-3")
                            ], width=6),
                            dbc.Col([
                                html.Div([
                                    dbc.Label("자동 백업 주기"),
                                    dbc.Select(
                                        id="auto-backup-interval",
                                        options=[
                                            {"label": "1일마다", "value": "1d"},
                                            {"label": "3일마다", "value": "3d"},
                                            {"label": "1주마다", "value": "1w"},
                                            {"label": "1개월마다", "value": "1m"},
                                        ],
                                        value="1d"
                                    )
                                ], className="mb-3")
                            ], width=6),
                        ]),
                        dbc.Row([
                            dbc.Col([
                                dbc.Button(
                                    "설정 저장",
                                    id="save-automation-settings",
                                    color="primary",
                                    className="mt-3"
                                )
                            ])
                        ])
                    ])
                ], className="mb-4")
            ])
        ]),
        
        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader([
                        html.H4("📊 자동화 작업 로그", className="mb-0")
                    ]),
                    dbc.CardBody([
                        html.Div(id="automation-logs-table")
                    ])
                ])
            ])
        ]),
        
        # 알림 토스트
        dbc.Toast(
            id="automation-toast",
            header="알림",
            is_open=False,
            dismissable=True,
            duration=4000,
            icon="primary",
            style={"position": "fixed", "top": 66, "right": 10, "width": 350}
        )
    ], fluid=True)

@callback(
    Output("automation-logs-table", "children"),
    Input("url", "pathname")
)
def update_automation_logs(pathname):
    """자동화 작업 로그 테이블을 업데이트합니다."""
    
    # 샘플 데이터 (실제로는 DB에서 가져와야 함)
    sample_logs = [
        {
            "timestamp": "2024-01-15 14:30:00",
            "task": "데이터 분석",
            "status": "완료",
            "duration": "2분 30초",
            "details": "프로젝트 A 분석 완료"
        },
        {
            "timestamp": "2024-01-15 13:00:00",
            "task": "백업",
            "status": "완료",
            "duration": "1분 45초",
            "details": "데이터베이스 백업 완료"
        },
        {
            "timestamp": "2024-01-15 12:30:00",
            "task": "센서 데이터 수집",
            "status": "진행 중",
            "duration": "-",
            "details": "센서 S001~S030 데이터 수집 중"
        },
        {
            "timestamp": "2024-01-15 11:00:00",
            "task": "보고서 생성",
            "status": "오류",
            "duration": "-",
            "details": "템플릿 파일을 찾을 수 없음"
        },
        {
            "timestamp": "2024-01-15 10:00:00",
            "task": "시스템 점검",
            "status": "완료",
            "duration": "30초",
            "details": "시스템 상태 정상"
        }
    ]
    
    # 상태별 색상 매핑
    status_colors = {
        "완료": "success",
        "진행 중": "primary",
        "대기 중": "warning",
        "오류": "danger"
    }
    
    # 테이블 헤더
    header = dbc.Row([
        dbc.Col("시간", width=3, className="fw-bold"),
        dbc.Col("작업", width=2, className="fw-bold"),
        dbc.Col("상태", width=2, className="fw-bold"),
        dbc.Col("소요시간", width=2, className="fw-bold"),
        dbc.Col("상세내용", width=3, className="fw-bold"),
    ], className="border-bottom pb-2 mb-2")
    
    # 테이블 행들
    rows = []
    for log in sample_logs:
        row = dbc.Row([
            dbc.Col(log["timestamp"], width=3),
            dbc.Col(log["task"], width=2),
            dbc.Col(
                dbc.Badge(
                    log["status"],
                    color=status_colors.get(log["status"], "secondary"),
                    className="text-white"
                ),
                width=2
            ),
            dbc.Col(log["duration"], width=2),
            dbc.Col(log["details"], width=3),
        ], className="border-bottom py-2")
        rows.append(row)
    
    return [header] + rows

@callback(
    Output("automation-toast", "is_open"),
    Output("automation-toast", "header"),
    Output("automation-toast", "children"),
    Output("automation-toast", "icon"),
    Input("save-automation-settings", "n_clicks"),
    prevent_initial_call=True
)
def save_automation_settings(n_clicks):
    """자동화 설정을 저장하고 알림을 표시합니다."""
    if n_clicks:
        return True, "성공", "자동화 설정이 저장되었습니다.", "success"
    return False, "", "", "primary" 